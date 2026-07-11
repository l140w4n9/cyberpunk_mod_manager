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
from ..models import Mod, ModStatus, ModDependency, InstallRecord
from ..nexus.client import NexusAPIError, NexusClient
from ..nexus.dependencies import (
    collect_dependencies,
    get_dependency_infos,
    get_dependent_infos,
    installed_dependents,
    missing_dependencies,
    sync_dependencies,
)
from ..nexus.schemas import FilePin, ModDetails
from ..storage.db import get_session
from .concurrency import DEFAULT_CONCURRENCY, gather_bounded
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
    registered = resolve_local_archive_path(mod_id)
    if registered is not None:
        return registered

    downloads = config.downloads_dir
    if not downloads.exists():
        return None

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
        for path in downloads.iterdir():
            if path.is_file() and str(mod_id) in path.name:
                matches.append(path)
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def resolve_local_archive_path(mod_id: int) -> Path | None:
    """从库存登记的 local_path 解析本地压缩包绝对路径。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None or not mod.local_path:
            return None
        stored = Path(mod.local_path)
        if stored.is_absolute() and stored.is_file():
            return stored
        candidate = config.downloads_dir / mod.local_path
        if candidate.is_file():
            return candidate
    return None


def _apply_details_to_mod(mod: Mod, details: ModDetails) -> None:
    mod.name = details.name
    mod.version = details.version
    mod.author = details.author
    mod.description = details.summary or details.description
    mod.mod_page_url = details.mod_page_url
    mod.thumbnail_url = details.picture_url
    if details.internal_mod_id:
        mod.nexus_internal_mod_id = details.internal_mod_id
    mod.legacy_mod_requirements = details.legacy_mod_requirements


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
    """登记本地压缩包路径到库存（支持 downloads 外绝对路径）。"""
    resolved = archive_path.resolve()
    try:
        stored = str(resolved.relative_to(config.downloads_dir.resolve()))
    except ValueError:
        stored = str(resolved)
    get_or_create_mod_stub(mod_id)
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            raise RuntimeError(f"Mod {mod_id} missing after upsert")
        mod.local_path = stored
        mod.file_name = resolved.name
        if mod.status != ModStatus.INSTALLED:
            mod.status = ModStatus.DOWNLOADED
        session.add(mod)
        session.commit()
    return stored


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
    version_id = None
    with get_session() as session:
        mod = session.get(Mod, internal_id)
        if mod and mod.nexus_version_id:
            version_id = mod.nexus_version_id
    dep_items = await collect_dependencies(mod_id, version_id=version_id)
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
    missing = [d for d in deps if not d.installed and d.source not in ("optional", "external")]
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
        "nexus_version_id": mod.nexus_version_id or "",
        "legacy_mod_requirements": mod.legacy_mod_requirements,
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
    if targets:
        await gather_bounded(
            [ensure_mod_summary(mod_id) for mod_id in targets],
            concurrency=DEFAULT_CONCURRENCY,
        )


async def refresh_dependencies(mod_id: int) -> list[dict]:
    """刷新模组依赖信息。"""
    internal_id = await ensure_mod_in_inventory(mod_id)
    if internal_id is None:
        return []
    async with NexusClient() as client:
        details = await client.get_mod_details(mod_id)
    version_id = None
    with get_session() as session:
        mod = session.get(Mod, internal_id)
        if mod and mod.nexus_version_id:
            version_id = mod.nexus_version_id
    dep_items = await collect_dependencies(mod_id, version_id=version_id)
    sync_dependencies(internal_id, dep_items)
    return [d.to_dict() for d in get_dependency_infos(mod_id)]


async def install_from_archive(
    mod_id: int,
    archive_path: Path,
    *,
    smart_install: bool = True,
    merge: bool = False,
) -> str:
    """从本地压缩包安装（可选：先检查结构并由 LLM 制定安装计划）。"""
    from .install_plan import build_install_plan

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return error_json(f"Mod {mod_id} not in inventory")
        internal_id = mod.id
        mod_name = mod.name or ""
        description = mod.description or ""

    if not archive_path.exists():
        return error_json(f"Archive not found: {archive_path}")

    register_local_archive(mod_id, archive_path)

    file_mappings: dict[str, str] | None = None
    plan_source = "rules"
    plan_items: list[dict] = []
    install_plan_preview: dict | None = None

    if smart_install:
        install_plan_preview = await build_install_plan(
            mod_id,
            archive_path,
            mod_name=mod_name,
            description=description,
        )
        file_mappings = install_plan_preview.get("file_mappings") or {}
        plan_source = install_plan_preview.get("plan_source") or "rules"
        plan_items = install_plan_preview.get("plan_items") or []
        if not file_mappings:
            return error_json(
                "无法生成安装计划：压缩包内没有可安装文件",
                mod_id=mod_id,
                install_plan=install_plan_preview,
            )

    installer = Installer()
    try:
        result = installer.install(
            internal_id,
            archive_path,
            file_mappings=file_mappings,
            plan_source=plan_source,
            plan_items=plan_items,
            merge=merge,
        )
    except ValueError as exc:
        return error_json(str(exc), mod_id=mod_id, install_plan=install_plan_preview)
    except Exception as exc:
        return error_json(f"Install failed: {exc}", mod_id=mod_id)
    plan = get_uninstall_plan(internal_id)
    return json.dumps(
        {
            "mod_id": mod_id,
            "internal_id": internal_id,
            "source": "local",
            "local_path": str(archive_path),
            "added_files_count": len(result.added_files),
            "skipped": result.skipped,
            "plan_source": plan_source,
            "install_plan": install_plan_preview,
            "uninstall_plan_preview": plan.to_dict() if plan else None,
        },
        ensure_ascii=False,
    )


async def download_mod(
    mod_id: int,
    *,
    pin: FilePin | None = None,
    allow_adult_content: bool | None = None,
) -> str:
    """通过 Nexus API 下载模组（v3 定位版本 + 遗留下载链接）。"""
    permit_adult = (
        config.allow_adult_content if allow_adult_content is None else allow_adult_content
    )
    try:
        async with NexusClient() as client:
            batch = await client.get_mods_batch([mod_id])
            info = batch.get(mod_id)
            if info and info.adult_content and not permit_adult:
                return error_json(
                    f"模组 {mod_id} 标记为成人内容，已阻止自动下载",
                    adult_content=True,
                    mod_id=mod_id,
                )
            mod_files = await client.resolve_install_versions(mod_id, pin=pin)
            if not mod_files:
                return error_json(f"No file found for mod {mod_id}")
            local_paths: list[dict] = []
            for mod_file in mod_files:
                if not mod_file.file_id:
                    continue
                local_path = await client.download_file(
                    mod_id,
                    mod_file.file_id,
                    config.downloads_dir,
                    file_name=mod_file.file_name,
                )
                local_paths.append(
                    {
                        "file_id": mod_file.file_id,
                        "version_id": mod_file.version_id,
                        "file_name": mod_file.file_name,
                        "version": mod_file.version,
                        "local_path": str(local_path),
                    }
                )
            if not local_paths:
                return error_json(f"No file found for mod {mod_id}")
            mod_file = mod_files[0]
            local_path = Path(local_paths[0]["local_path"])
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
            mod.nexus_version_id = mod_file.version_id or mod.nexus_version_id
            mod.nexus_mod_file_id = mod_file.mod_file_id or mod.nexus_mod_file_id
            mod.nexus_internal_mod_id = (
                mod_file.internal_mod_id or mod.nexus_internal_mod_id
            )
            if mod_file.version:
                mod.version = mod_file.version
            mod.status = ModStatus.DOWNLOADED
            session.add(mod)
            session.commit()

    return json.dumps(
        {
            "mod_id": mod_id,
            "file_id": mod_file.file_id,
            "version_id": mod_file.version_id,
            "file_name": mod_file.file_name,
            "version": mod_file.version,
            "local_path": str(local_path),
            "local_paths": local_paths,
            "files_count": len(local_paths),
            "source": "api",
        },
        ensure_ascii=False,
    )


def _mod_status_info(mod_id: int) -> tuple[str, bool]:
    """返回模组状态字符串与是否已安装。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return ModStatus.NOT_INSTALLED.value, False
        status = _status_str(mod.status)
        return status, status == ModStatus.INSTALLED.value


def batch_mod_status_info(mod_ids: list[int]) -> dict[int, tuple[str, bool]]:
    """批量查询模组安装状态。"""
    if not mod_ids:
        return {}
    unique_ids = list(dict.fromkeys(mod_ids))
    with get_session() as session:
        mods = session.exec(
            select(Mod).where(Mod.nexus_mod_id.in_(unique_ids))
        ).all()
    by_id = {mod.nexus_mod_id: mod for mod in mods}
    result: dict[int, tuple[str, bool]] = {}
    for mod_id in unique_ids:
        mod = by_id.get(mod_id)
        if mod is None:
            result[mod_id] = (ModStatus.NOT_INSTALLED.value, False)
            continue
        status = _status_str(mod.status)
        result[mod_id] = (status, status == ModStatus.INSTALLED.value)
    return result


def _already_installed_json(mod_id: int) -> str:
    """已安装模组的标准跳过响应。"""
    status, _ = _mod_status_info(mod_id)
    name = ""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is not None:
            name = mod.name or ""
    label = f"({name}) " if name else ""
    return json.dumps(
        {
            "mod_id": mod_id,
            "name": name,
            "skipped": True,
            "reason": "already_installed",
            "status": status,
            "message": f"模组 {mod_id} {label}已安装，已跳过".strip(),
        },
        ensure_ascii=False,
    )


async def install_mod(
    mod_id: int,
    *,
    allow_local_fallback: bool = True,
    skip_download: bool = False,
    local_only: bool = False,
    skip_installed: bool = True,
    pin: FilePin | None = None,
) -> str:
    """下载（或本地回退）并安装模组。"""
    await ensure_mod_in_inventory(mod_id)

    if skip_installed:
        _status, installed = _mod_status_info(mod_id)
        if installed:
            return _already_installed_json(mod_id)

    used_local = False
    used_local_reason = ""
    dl_result: str | None = None
    if local_only or skip_download:
        local = resolve_local_archive_path(mod_id) or find_local_archive(mod_id)
        if local is None:
            return error_json(
                f"未找到模组 {mod_id} 的本地压缩包",
                mod_id=mod_id,
                local_only=local_only,
            )
        register_local_archive(mod_id, local)
        used_local = True
    elif not skip_download:
        dl_result = await download_mod(mod_id, pin=pin)
        if is_error(dl_result):
            data = json.loads(dl_result)
            if allow_local_fallback and (
                data.get("premium_only") or data.get("adult_content")
            ):
                local = find_local_archive(mod_id)
                if local is not None:
                    register_local_archive(mod_id, local)
                    used_local = True
                    used_local_reason = (
                        "adult_content" if data.get("adult_content") else "premium_only"
                    )
                elif data.get("premium_only"):
                    return error_json(
                        "该模组需 Nexus Premium 才能 API 下载。"
                        f"请手动下载后放入 {config.downloads_dir}，"
                        f"文件名包含 {mod_id}（如 {mod_id}_xxx.zip），再重试安装。",
                        premium_only=True,
                        mod_id=mod_id,
                        downloads_dir=str(config.downloads_dir),
                    )
                elif data.get("adult_content"):
                    return error_json(
                        "该模组为成人内容，管理器默认不通过 API 自动下载。"
                        f"请在 Nexus 网站登录后手动下载，放入 {config.downloads_dir}，"
                        f"文件名包含 {mod_id}（如 {mod_id}_xxx.zip），再重试安装。"
                        "或在「设置」中开启「允许成人内容 API 下载」。",
                        adult_content=True,
                        mod_id=mod_id,
                        downloads_dir=str(config.downloads_dir),
                    )
                else:
                    return dl_result
            else:
                return dl_result

    archive_path = resolve_local_archive_path(mod_id)
    if archive_path is None:
        return error_json(f"No local archive for mod {mod_id}")

    archive_paths = [archive_path]
    if not used_local and dl_result and not is_error(dl_result):
        try:
            dl_data = json.loads(dl_result)
            extra = [
                Path(item["local_path"])
                for item in dl_data.get("local_paths") or []
                if item.get("local_path")
            ]
            if extra:
                archive_paths = extra
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    result = None
    for index, path in enumerate(archive_paths):
        one = await install_from_archive(
            mod_id,
            path,
            merge=index > 0,
        )
        if is_error(one):
            return one
        result = one

    if result is None:
        return error_json(f"Install failed for mod {mod_id}")

    data = json.loads(result)
    if used_local:
        data["used_local_fallback"] = True
        if used_local_reason == "premium_only":
            data["premium_only"] = True
        if used_local_reason == "adult_content":
            data["adult_content"] = True
    return json.dumps(data, ensure_ascii=False)


async def install_mod_with_dependencies(
    mod_id: int,
    *,
    install_dependencies: bool = True,
    allow_local_fallback: bool = True,
    local_only: bool = False,
    skip_installed: bool = True,
    pin: FilePin | None = None,
) -> str:
    """安装模组及其缺失的前置依赖。"""
    await ensure_mod_in_inventory(mod_id)
    await refresh_dependencies(mod_id)

    main_status, main_installed = _mod_status_info(mod_id)
    installed_deps: list[dict] = []
    failed_deps: list[dict] = []
    missing = missing_dependencies(mod_id) if install_dependencies else []

    if install_dependencies and missing:

        async def install_dep(dep) -> tuple[dict | None, dict | None]:
            dep_result = await install_mod(
                dep.nexus_mod_id,
                allow_local_fallback=allow_local_fallback,
                local_only=local_only,
                skip_installed=skip_installed,
            )
            if is_error(dep_result):
                return None, {
                    "nexus_mod_id": dep.nexus_mod_id,
                    "name": dep.name,
                    "error": json.loads(dep_result).get("error"),
                }
            dep_data = json.loads(dep_result)
            return {
                "nexus_mod_id": dep.nexus_mod_id,
                "name": dep.name,
                "result": dep_data,
                "skipped": bool(dep_data.get("skipped")),
            }, None

        dep_outcomes = await gather_bounded(
            [install_dep(dep) for dep in missing],
            concurrency=DEFAULT_CONCURRENCY,
        )
        for ok_item, fail_item in dep_outcomes:
            if ok_item is not None:
                installed_deps.append(ok_item)
            if fail_item is not None:
                failed_deps.append(fail_item)

    if main_installed and skip_installed:
        name = ""
        with get_session() as session:
            mod = session.exec(
                select(Mod).where(Mod.nexus_mod_id == mod_id)
            ).first()
            if mod is not None:
                name = mod.name or ""
        label = f"({name}) " if name else ""
        repaired = [d for d in installed_deps if not d.get("skipped")]
        skipped_deps = [d for d in installed_deps if d.get("skipped")]

        if not missing and not failed_deps:
            payload = json.loads(_already_installed_json(mod_id))
            payload["dependencies"] = [
                d.to_dict() for d in get_dependency_infos(mod_id)
            ]
            payload["dependencies_installed"] = installed_deps
            payload["dependencies_failed"] = failed_deps
            return json.dumps(payload, ensure_ascii=False)

        parts: list[str] = []
        if repaired:
            parts.append(f"已补装 {len(repaired)} 个依赖")
        if skipped_deps:
            parts.append(f"{len(skipped_deps)} 个依赖已就绪")
        if failed_deps:
            parts.append(f"{len(failed_deps)} 个依赖失败")
        message = f"模组 {mod_id} {label}{'，'.join(parts)}".strip()

        return json.dumps(
            {
                "mod_id": mod_id,
                "name": name,
                "skipped": not repaired and not failed_deps,
                "reason": "deps_repair",
                "status": main_status,
                "message": message,
                "dependencies_installed": installed_deps,
                "dependencies_failed": failed_deps,
                "dependencies": [d.to_dict() for d in get_dependency_infos(mod_id)],
                "added_files_count": sum(
                    int((d.get("result") or {}).get("added_files_count") or 0)
                    for d in repaired
                ),
            },
            ensure_ascii=False,
        )

    main_result = await install_mod(
        mod_id,
        allow_local_fallback=allow_local_fallback,
        local_only=local_only,
        skip_installed=False if missing else skip_installed,
        pin=pin,
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


def scan_local_folder(folder_path: str) -> str:
    """扫描本地文件夹，识别压缩包与模组 ID。"""
    from .local_scan import is_downloads_dir, resolve_folder_path, scan_folder

    try:
        folder = resolve_folder_path(folder_path, base=config.downloads_dir)
    except ValueError as exc:
        return error_json(str(exc))
    if not folder.is_dir():
        return error_json(f"文件夹不存在: {folder}")
    payload = scan_folder(folder)
    detected_ids = [int(item["mod_id"]) for item in payload["detected"]]
    status_map = batch_mod_status_info(detected_ids)
    for item in payload["detected"]:
        mod_id = int(item["mod_id"])
        status, installed = status_map.get(
            mod_id, (ModStatus.NOT_INSTALLED.value, False)
        )
        item["status"] = status
        item["installed"] = installed
    payload["downloads_dir"] = str(config.downloads_dir)
    payload["is_downloads_dir"] = is_downloads_dir(folder, config.downloads_dir)
    payload["installed_count"] = sum(
        1 for item in payload["detected"] if item.get("installed")
    )
    payload["pending_count"] = sum(
        1 for item in payload["detected"] if not item.get("installed")
    )
    return json.dumps(payload, ensure_ascii=False)


async def install_local_folder(
    folder_path: str,
    mod_ids: list[int] | None = None,
    *,
    install_dependencies: bool = True,
    skip_installed: bool = True,
) -> str:
    """从文件夹批量本地安装（自动识别 ID、处理依赖）。"""
    from .local_scan import is_downloads_dir, pick_root_mod_ids, resolve_folder_path, scan_folder

    try:
        folder = resolve_folder_path(folder_path, base=config.downloads_dir)
    except ValueError as exc:
        return error_json(str(exc))
    if not folder.is_dir():
        return error_json(f"文件夹不存在: {folder}")

    if is_downloads_dir(folder, config.downloads_dir) and not mod_ids:
        return error_json(
            "为安全起见，禁止对 downloads 缓存目录执行「安装全部」。"
            "请指定独立子文件夹路径，或在上方填写要安装的模组 ID。",
            folder=str(folder),
            is_downloads_dir=True,
        )

    scan = scan_folder(folder)
    detected = scan["detected"]
    if not detected:
        return error_json(
            "文件夹内未识别到可安装的模组压缩包",
            folder=str(folder),
            unknown=scan["unknown"],
        )

    detected_ids = {int(item["mod_id"]) for item in detected}
    if mod_ids:
        targets = [mid for mid in mod_ids if mid in detected_ids]
        missing_targets = [mid for mid in mod_ids if mid not in detected_ids]
    else:
        targets = pick_root_mod_ids(detected_ids, get_dependency_infos)
        missing_targets = []

    skipped: list[dict] = []
    if skip_installed:
        status_map = batch_mod_status_info(targets)
        pending: list[int] = []
        for mod_id in targets:
            _status, installed = status_map.get(
                mod_id, (ModStatus.NOT_INSTALLED.value, False)
            )
            if installed:
                skipped.append({"mod_id": mod_id, "reason": "already_installed"})
            else:
                pending.append(mod_id)
        targets = pending

    if not targets:
        return json.dumps(
            {
                "folder": str(folder),
                "scan": scan,
                "targets": [],
                "missing_targets": missing_targets,
                "skipped": skipped,
                "results": [],
                "succeeded": [],
                "failed": [],
                "message": "没有需要安装的模组（均已安装或已跳过）",
                "local_only": True,
            },
            ensure_ascii=False,
        )

    archive_by_id = {int(item["mod_id"]): Path(item["path"]) for item in detected}
    register_ids = set(targets)
    if install_dependencies:
        for mod_id in list(targets):
            for dep in missing_dependencies(mod_id):
                if dep.nexus_mod_id in archive_by_id:
                    register_ids.add(dep.nexus_mod_id)

    async def register_mod(mod_id: int) -> None:
        archive = archive_by_id.get(mod_id)
        if archive is None:
            return
        register_local_archive(mod_id, archive)
        try:
            await ensure_mod_in_inventory(mod_id)
        except Exception as exc:
            logger.warning("ensure_mod_in_inventory(%s) failed: %s", mod_id, exc)

    await gather_bounded(
        [register_mod(mod_id) for mod_id in register_ids],
        concurrency=DEFAULT_CONCURRENCY,
    )

    async def install_target(mod_id: int) -> dict:
        if install_dependencies:
            raw = await install_mod_with_dependencies(
                mod_id,
                install_dependencies=True,
                allow_local_fallback=True,
                local_only=True,
            )
        else:
            raw = await install_mod(
                mod_id,
                allow_local_fallback=True,
                local_only=True,
            )
        data = json.loads(raw)
        data["mod_id"] = mod_id
        return data

    results = await gather_bounded(
        [install_target(mod_id) for mod_id in targets],
        concurrency=DEFAULT_CONCURRENCY,
    )

    succeeded = [
        r["mod_id"]
        for r in results
        if not r.get("error")
    ]
    failed = [r for r in results if r.get("error")]

    return json.dumps(
        {
            "folder": str(folder),
            "scan": scan,
            "targets": targets,
            "missing_targets": missing_targets,
            "skipped": skipped,
            "results": results,
            "succeeded": succeeded,
            "failed": failed,
            "local_only": True,
        },
        ensure_ascii=False,
    )


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


def _is_pending_inventory_mod(mod: Mod) -> bool:
    return _status_str(mod.status) != ModStatus.INSTALLED.value


def delete_mod_from_inventory(nexus_mod_id: int) -> dict:
    """从库存移除模组记录（仅允许未安装状态）。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == nexus_mod_id)
        ).first()
        if mod is None:
            return {"error": f"Mod {nexus_mod_id} not found", "mod_id": nexus_mod_id}
        if not _is_pending_inventory_mod(mod):
            return {
                "error": "已安装模组请先在「已安装」页卸载，不能直接从库存清理",
                "mod_id": nexus_mod_id,
            }
        internal_id = mod.id
        name = mod.name or ""
        for dep in session.exec(
            select(ModDependency).where(ModDependency.owner_mod_id == internal_id)
        ).all():
            session.delete(dep)
        for record in session.exec(
            select(InstallRecord).where(InstallRecord.mod_id == internal_id)
        ).all():
            session.delete(record)
        session.delete(mod)
        session.commit()
    return {"deleted": nexus_mod_id, "mod_id": nexus_mod_id, "name": name}


def cleanup_pending_mods(mod_ids: list[int] | None = None) -> dict:
    """批量清理待安装模组（从库存删除，不触碰游戏目录）。"""
    with get_session() as session:
        mods = session.exec(select(Mod)).all()
    pending = [m for m in mods if _is_pending_inventory_mod(m)]
    if mod_ids is not None:
        allowed = set(mod_ids)
        pending = [m for m in pending if m.nexus_mod_id in allowed]
    deleted: list[dict] = []
    failed: list[dict] = []
    for mod in pending:
        result = delete_mod_from_inventory(mod.nexus_mod_id)
        if result.get("error"):
            failed.append(result)
        else:
            deleted.append(result)
    return {
        "deleted": deleted,
        "failed": failed,
        "deleted_count": len(deleted),
        "failed_count": len(failed),
    }
