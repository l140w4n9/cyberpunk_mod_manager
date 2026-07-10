# -*- coding: utf-8 -*-
"""模组安装工作流：下载、本地回退、依赖安装。"""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from ..config import config
from ..installer import Installer, get_uninstall_plan
from ..models import Mod, ModStatus
from ..nexus.client import NexusAPIError, NexusClient
from ..nexus.dependencies import (
    collect_dependencies,
    get_dependency_infos,
    missing_dependencies,
    sync_dependencies,
)
from ..storage.db import get_session


def error_json(message: str, **extra) -> str:
    return json.dumps({"error": message, **extra}, ensure_ascii=False)


def is_error(result: str) -> bool:
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return True
    return isinstance(data, dict) and bool(data.get("error"))


def find_local_archive(mod_id: int) -> Path | None:
    """在 downloads 目录查找与 mod_id 匹配的本地压缩包。"""
    downloads = config.downloads_dir
    if not downloads.exists():
        return None

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod and mod.local_path:
            candidate = downloads / mod.local_path
            if candidate.is_file():
                return candidate

    patterns = [
        f"{mod_id}*.zip",
        f"{mod_id}*.7z",
        f"*{mod_id}*.zip",
    ]
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(downloads.glob(pattern))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def register_local_archive(mod_id: int, archive_path: Path) -> str:
    """登记本地压缩包路径到库存。"""
    rel = str(archive_path.relative_to(config.downloads_dir))
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            mod = Mod(nexus_mod_id=mod_id, name=f"Mod {mod_id}")
            session.add(mod)
            session.commit()
            session.refresh(mod)
        mod.local_path = rel
        mod.file_name = archive_path.name
        mod.status = ModStatus.DOWNLOADED
        session.add(mod)
        session.commit()
    return rel


async def ensure_mod_in_inventory(mod_id: int) -> int | None:
    """确保模组在库存中，返回内部 id。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None:
            return mod.id
    async with NexusClient() as client:
        details = await client.get_mod_details(mod_id)
    with get_session() as session:
        mod = Mod(
            nexus_mod_id=mod_id,
            name=details.name,
            version=details.version,
            author=details.author,
            description=details.summary or details.description,
            mod_page_url=details.mod_page_url,
            thumbnail_url=details.picture_url,
        )
        session.add(mod)
        session.commit()
        session.refresh(mod)
        internal_id = mod.id
    dep_items = await collect_dependencies(
        mod_id, mod.description, details.summary
    )
    sync_dependencies(internal_id, dep_items)
    return internal_id


async def refresh_dependencies(mod_id: int) -> list[dict]:
    """刷新模组依赖信息。"""
    internal_id = await ensure_mod_in_inventory(mod_id)
    if internal_id is None:
        return []
    async with NexusClient() as client:
        details = await client.get_mod_details(mod_id)
    dep_items = await collect_dependencies(
        mod_id, details.description, details.summary
    )
    sync_dependencies(internal_id, dep_items)
    return [d.to_dict() for d in get_dependency_infos(mod_id)]


def install_from_archive(mod_id: int, archive_path: Path) -> str:
    """从本地压缩包安装。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return error_json(f"Mod {mod_id} not in inventory")
        internal_id = mod.id

    if not archive_path.exists():
        return error_json(f"Archive not found: {archive_path}")

    register_local_archive(mod_id, archive_path)
    installer = Installer()
    result = installer.install(internal_id, archive_path)
    plan = get_uninstall_plan(internal_id)
    return json.dumps(
        {
            "mod_id": mod_id,
            "internal_id": internal_id,
            "source": "local",
            "local_path": str(archive_path),
            "added_files_count": len(result.added_files),
            "skipped": result.skipped,
            "uninstall_plan_preview": plan.to_dict() if plan else None,
        },
        ensure_ascii=False,
    )


async def download_mod(mod_id: int) -> str:
    """通过 Nexus API 下载模组。"""
    try:
        async with NexusClient() as client:
            mod_file = await client.pick_primary_file(mod_id)
            if mod_file is None:
                return error_json(f"No file found for mod {mod_id}")
            local_path = await client.download_file(
                mod_id, mod_file.file_id, config.downloads_dir,
                file_name=mod_file.file_name,
            )
    except NexusAPIError as exc:
        return error_json(
            str(exc),
            status_code=exc.status_code,
            premium_only=exc.is_premium_only,
        )
    except Exception as exc:
        return error_json(f"Download failed: {exc}")

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None:
            mod.nexus_file_id = mod_file.file_id
            mod.file_name = mod_file.file_name or local_path.name
            mod.local_path = str(local_path.relative_to(config.downloads_dir))
            mod.status = ModStatus.DOWNLOADED
            session.add(mod)
            session.commit()

    return json.dumps(
        {
            "mod_id": mod_id,
            "file_id": mod_file.file_id,
            "file_name": mod_file.file_name,
            "local_path": str(local_path),
            "source": "api",
        },
        ensure_ascii=False,
    )


async def install_mod(
    mod_id: int,
    *,
    allow_local_fallback: bool = True,
    skip_download: bool = False,
) -> str:
    """下载（或本地回退）并安装模组。"""
    await ensure_mod_in_inventory(mod_id)

    used_local = False
    if not skip_download:
        dl_result = await download_mod(mod_id)
        if is_error(dl_result):
            data = json.loads(dl_result)
            if data.get("premium_only") and allow_local_fallback:
                local = find_local_archive(mod_id)
                if local is not None:
                    register_local_archive(mod_id, local)
                    used_local = True
                else:
                    return error_json(
                        "该模组需 Nexus Premium 才能 API 下载。"
                        f"请手动下载后放入 {config.downloads_dir}，"
                        f"文件名包含 {mod_id}（如 {mod_id}_xxx.zip），再重试安装。",
                        premium_only=True,
                        mod_id=mod_id,
                        downloads_dir=str(config.downloads_dir),
                    )
            else:
                return dl_result

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return error_json(f"Mod {mod_id} not in inventory")
        local_rel = mod.local_path

    if not local_rel:
        return error_json(f"No local archive for mod {mod_id}")

    archive_path = config.downloads_dir / local_rel
    result = install_from_archive(mod_id, archive_path)
    if is_error(result):
        return result

    data = json.loads(result)
    if used_local:
        data["used_local_fallback"] = True
        data["premium_only"] = True
    return json.dumps(data, ensure_ascii=False)


async def install_mod_with_dependencies(
    mod_id: int,
    *,
    install_dependencies: bool = True,
    allow_local_fallback: bool = True,
) -> str:
    """安装模组及其缺失的前置依赖。"""
    await refresh_dependencies(mod_id)
    installed_deps: list[dict] = []
    failed_deps: list[dict] = []

    if install_dependencies:
        for dep in missing_dependencies(mod_id):
            dep_result = await install_mod(
                dep.nexus_mod_id,
                allow_local_fallback=allow_local_fallback,
            )
            if is_error(dep_result):
                failed_deps.append(
                    {
                        "nexus_mod_id": dep.nexus_mod_id,
                        "name": dep.name,
                        "error": json.loads(dep_result).get("error"),
                    }
                )
            else:
                installed_deps.append(
                    {
                        "nexus_mod_id": dep.nexus_mod_id,
                        "name": dep.name,
                        "result": json.loads(dep_result),
                    }
                )

    main_result = await install_mod(
        mod_id, allow_local_fallback=allow_local_fallback
    )
    if is_error(main_result):
        payload = json.loads(main_result)
        payload["dependencies_installed"] = installed_deps
        payload["dependencies_failed"] = failed_deps
        payload["dependencies"] = [d.to_dict() for d in get_dependency_infos(mod_id)]
        return json.dumps(payload, ensure_ascii=False)

    payload = json.loads(main_result)
    payload["dependencies_installed"] = installed_deps
    payload["dependencies_failed"] = failed_deps
    payload["dependencies"] = [d.to_dict() for d in get_dependency_infos(mod_id)]
    return json.dumps(payload, ensure_ascii=False)


def check_dependencies_report(mod_id: int) -> str:
    """返回依赖检查报告。"""
    deps = get_dependency_infos(mod_id)
    missing = [d for d in deps if not d.installed]
    return json.dumps(
        {
            "mod_id": mod_id,
            "dependencies": [d.to_dict() for d in deps],
            "missing_count": len(missing),
            "all_satisfied": len(missing) == 0,
            "missing": [d.to_dict() for d in missing],
        },
        ensure_ascii=False,
    )
