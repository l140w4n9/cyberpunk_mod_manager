# -*- coding: utf-8 -*-
"""模组安装工作流：下载、本地回退、依赖安装。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from ..config import config
from ..installer import Installer, get_uninstall_plan
from ..models import Mod, ModStatus
from ..nexus.client import NexusAPIError, NexusClient
from ..nexus.dependencies import (
    collect_dependencies,
    get_dependency_infos,
    get_dependent_infos,
    installed_dependents,
    missing_dependencies,
    sync_dependencies,
)
from ..nexus.schemas import ModDetails
from ..storage.db import get_session
from .summary import display_summary, ensure_mod_summary

logger = logging.getLogger(__name__)


def _status_str(status) -> str:
    """将 ModStatus（或裸字符串）统一转为字符串。"""
    return status.value if hasattr(status, "value") else str(status)


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
        f"{mod_id}*.rar",
        f"*{mod_id}*.zip",
        f"*{mod_id}*.7z",
        f"*{mod_id}*.rar",
    ]
    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(downloads.glob(pattern))
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _apply_details_to_mod(mod: Mod, details: ModDetails) -> None:
    mod.name = details.name
    mod.version = details.version
    mod.author = details.author
    mod.description = details.summary or details.description
    mod.mod_page_url = details.mod_page_url
    mod.thumbnail_url = details.picture_url


def upsert_mod_from_details(mod_id: int, details: ModDetails) -> int:
    """插入或更新库存模组，返回内部 id（并发安全）。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None:
            _apply_details_to_mod(mod, details)
            session.add(mod)
            session.commit()
            session.refresh(mod)
            return mod.id

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
        try:
            session.commit()
            session.refresh(mod)
            return mod.id
        except IntegrityError:
            session.rollback()
            existing = session.exec(
                select(Mod).where(Mod.nexus_mod_id == mod_id)
            ).first()
            if existing is None:
                raise
            _apply_details_to_mod(existing, details)
            session.add(existing)
            session.commit()
            session.refresh(existing)
            return existing.id


def get_or_create_mod_stub(mod_id: int, name: str = "") -> int:
    """获取或创建最小库存记录（用于本地包登记等）。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None:
            return mod.id
        mod = Mod(nexus_mod_id=mod_id, name=name or f"Mod {mod_id}")
        session.add(mod)
        try:
            session.commit()
            session.refresh(mod)
            return mod.id
        except IntegrityError:
            session.rollback()
            existing = session.exec(
                select(Mod).where(Mod.nexus_mod_id == mod_id)
            ).first()
            if existing is None:
                raise
            return existing.id


def register_local_archive(mod_id: int, archive_path: Path) -> str:
    """登记本地压缩包路径到库存。"""
    rel = str(archive_path.relative_to(config.downloads_dir))
    get_or_create_mod_stub(mod_id)
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            raise RuntimeError(f"Mod {mod_id} missing after upsert")
        mod.local_path = rel
        mod.file_name = archive_path.name
        mod.status = ModStatus.DOWNLOADED
        session.add(mod)
        session.commit()
    return rel


async def ensure_mod_in_inventory(
    mod_id: int,
    details: ModDetails | None = None,
) -> int:
    """确保模组在库存中，返回内部 id。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None and details is None:
            return mod.id

    if details is None:
        async with NexusClient() as client:
            details = await client.get_mod_details(mod_id)

    internal_id = upsert_mod_from_details(mod_id, details)
    dep_items = await collect_dependencies(
        mod_id, details.summary or details.description, details.summary
    )
    sync_dependencies(internal_id, dep_items)
    if config.openai_api_key:
        try:
            await ensure_mod_summary(mod_id)
        except Exception:
            logger.warning("Failed to generate AI summary for mod %s", mod_id)
    return internal_id


def build_mod_overview(mod: Mod) -> dict:
    """构建模组列表项（含依赖、反向依赖、摘要）。"""
    summary, summary_source = display_summary(mod)
    deps = get_dependency_infos(mod.nexus_mod_id)
    dependents = get_dependent_infos(mod.nexus_mod_id)
    missing = [d for d in deps if not d.installed and d.source != "optional"]
    return {
        "id": mod.id,
        "nexus_mod_id": mod.nexus_mod_id,
        "name": mod.name,
        "version": mod.version,
        "status": _status_str(mod.status),
        "enabled": mod.enabled,
        "installed_at": str(mod.installed_at) if mod.installed_at else None,
        "thumbnail_url": mod.thumbnail_url,
        "mod_page_url": mod.mod_page_url,
        "summary_line": summary,
        "summary_source": summary_source,
        "dependencies": [d.to_dict() for d in deps],
        "dependents": [d.to_dict() for d in dependents],
        "dependencies_missing_count": len(missing),
        "dependencies_satisfied": len(missing) == 0,
    }


def check_uninstall_report(mod_id: int) -> dict:
    """评估卸载是否安全（反向依赖 + 卸载计划）。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return {
                "mod_id": mod_id,
                "safe": False,
                "can_uninstall": False,
                "warnings": ["模组不在库存中"],
                "blocking_dependents": [],
                "dependents": [],
                "has_uninstall_plan": False,
            }
        internal_id = mod.id
        name = mod.name
        status = _status_str(mod.status)

    if status != ModStatus.INSTALLED.value:
        return {
            "mod_id": mod_id,
            "name": name,
            "safe": True,
            "can_uninstall": False,
            "warnings": ["模组当前未安装"],
            "blocking_dependents": [],
            "dependents": [d.to_dict() for d in get_dependent_infos(mod_id)],
            "has_uninstall_plan": False,
        }

    blocking = installed_dependents(mod_id)
    plan = get_uninstall_plan(internal_id)
    warnings: list[str] = []
    if blocking:
        names = ", ".join(f"{d.name} ({d.nexus_mod_id})" for d in blocking)
        warnings.append(f"以下已安装模组仍依赖此模组：{names}")
    if plan is None:
        warnings.append("无卸载记录，无法精确回滚已安装文件")

    safe = len(blocking) == 0 and plan is not None
    return {
        "mod_id": mod_id,
        "name": name,
        "safe": safe,
        "can_uninstall": plan is not None,
        "warnings": warnings,
        "blocking_dependents": [d.to_dict() for d in blocking],
        "dependents": [d.to_dict() for d in get_dependent_infos(mod_id)],
        "has_uninstall_plan": plan is not None,
        "uninstall_plan_preview": plan.to_dict() if plan else None,
    }


async def refresh_mod_summaries(mod_ids: list[int] | None = None) -> None:
    """为缺少 AI 摘要的模组批量生成摘要。"""
    with get_session() as session:
        mods = session.exec(select(Mod)).all()
        targets = [
            m.nexus_mod_id
            for m in mods
            if (not mod_ids or m.nexus_mod_id in mod_ids)
            and not m.summary_line
            and (m.description or m.name)
        ]
    for mod_id in targets:
        await ensure_mod_summary(mod_id)


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
    required = [d for d in deps if d.source != "optional"]
    optional = [d for d in deps if d.source == "optional"]
    missing = [d for d in required if not d.installed]
    return json.dumps(
        {
            "mod_id": mod_id,
            "dependencies": [d.to_dict() for d in deps],
            "required_dependencies": [d.to_dict() for d in required],
            "optional_dependencies": [d.to_dict() for d in optional],
            "missing_count": len(missing),
            "all_satisfied": len(missing) == 0,
            "missing": [d.to_dict() for d in missing],
        },
        ensure_ascii=False,
    )
