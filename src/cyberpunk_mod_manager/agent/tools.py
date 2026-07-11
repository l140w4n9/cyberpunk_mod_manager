# -*- coding: utf-8 -*-
"""AgentScope Agent 工具注册。"""
from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import select

from agentscope.agent import Agent
from agentscope.model import ChatModelBase
from agentscope.permission import PermissionBehavior, PermissionDecision
from agentscope.tool import FunctionTool, Toolkit

from ..config import config
from ..installer import Installer, get_uninstall_plan
from ..models import Mod, ModStatus
from ..nexus.client import NexusClient
from ..services import health_audit, mod_ops
from ..services.concurrency import DEFAULT_CONCURRENCY, gather_bounded
from ..storage.db import get_session, init_db

# 统一说明：凡出现 mod_id / mod_ids 均指 Nexus 网站模组数字 ID（如 27967），
# 不是数据库内部 id，也不是压缩包文件名。


def _error_json(message: str, **extra) -> str:
    return mod_ops.error_json(message, **extra)


async def search_mod(mod_id: int) -> str:
    """查询 Nexus 模组详情并同步依赖关系到本地库存。

    Args:
        mod_id: Nexus Mods 模组数字 ID（正整数，例如 27967）。不是内部数据库 id。

    Returns:
        JSON 字符串：模组 name、version、dependencies、internal_id 等。
    """
    try:
        async with NexusClient() as client:
            details = await client.get_mod_details(mod_id)
        internal_id = await mod_ops.ensure_mod_in_inventory(mod_id, details=details)
        deps = await mod_ops.refresh_dependencies(mod_id)
        payload = details.model_dump()
        payload["dependencies"] = deps
        payload["internal_id"] = internal_id
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return _error_json(f"查询模组失败: {exc}")


async def check_dependencies(mod_id: int) -> str:
    """检查指定模组的前置依赖是否已安装。

    Args:
        mod_id: Nexus Mods 模组数字 ID（要检查依赖的**主模组** ID）。

    Returns:
        JSON 字符串：dependencies、missing、all_satisfied 等字段。
    """
    await mod_ops.refresh_dependencies(mod_id)
    return mod_ops.check_dependencies_report(mod_id)


async def install_mod(mod_id: int) -> str:
    """仅安装单个模组（不主动遍历依赖树；Premium 失败时尝试本地包）。

    Args:
        mod_id: Nexus Mods 模组数字 ID（要安装的主模组）。

    Returns:
        JSON 字符串：added_files_count、skipped、error 等。added_files_count>0 才算成功。
    """
    return await mod_ops.install_mod(mod_id, allow_local_fallback=True)


async def install_mod_with_dependencies(mod_id: int) -> str:
    """安装模组并自动安装缺失的必需前置依赖（首选安装工具）。

    Args:
        mod_id: Nexus Mods 模组数字 ID（要安装的主模组；会先装其缺失依赖再装主模组）。

    Returns:
        JSON 字符串：含 dependencies_installed、dependencies_failed、added_files_count。
    """
    return await mod_ops.install_mod_with_dependencies(
        mod_id,
        install_dependencies=True,
        allow_local_fallback=True,
    )


async def install_mods_batch(mod_ids: list[int]) -> str:
    """批量安装多个模组（每个模组各自补全缺失依赖，最多 6 路并发）。

    Args:
        mod_ids: Nexus Mods 模组数字 ID 数组，例如 [107, 1511, 27967]。不要传字符串。

    Returns:
        JSON 字符串：results、succeeded、failed、no_files_written 列表。
    """
    results: list[dict] = []

    async def install_one(mod_id: int) -> dict:
        raw = await mod_ops.install_mod_with_dependencies(
            mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
        )
        data = json.loads(raw)
        data["mod_id"] = mod_id
        return data

    results = await gather_bounded(
        [install_one(mod_id) for mod_id in mod_ids],
        concurrency=DEFAULT_CONCURRENCY,
    )
    succeeded = [
        r["mod_id"]
        for r in results
        if not r.get("error") and r.get("added_files_count", 0) > 0
    ]
    failed = [r for r in results if r.get("error")]
    skipped = [
        r["mod_id"]
        for r in results
        if not r.get("error") and r.get("added_files_count", 0) == 0
    ]
    return json.dumps(
        {
            "results": results,
            "succeeded": succeeded,
            "failed": failed,
            "no_files_written": skipped,
        },
        ensure_ascii=False,
    )


async def install_local_mod(mod_id: int, archive_name: str) -> str:
    """从本地压缩包安装指定模组（不走 Nexus 下载）。

    Args:
        mod_id: Nexus Mods 模组数字 ID（必须与压缩包内模组一致）。
        archive_name: 压缩包路径。可为 downloads 目录下文件名（如 27967_xxx.zip）、相对 downloads 的子路径，或绝对路径。

    Returns:
        JSON 字符串：added_files_count、local_path、error 等。
    """
    path = Path(archive_name)
    archive_path = path if path.is_absolute() else config.downloads_dir / archive_name
    await mod_ops.ensure_mod_in_inventory(mod_id)
    return mod_ops.install_from_archive(mod_id, archive_path)


async def scan_local_folder_tool(folder_path: str) -> str:
    """扫描文件夹中的压缩包并识别 Nexus 模组 ID（只扫描不安装）。

    Args:
        folder_path: 文件夹绝对路径，或相对 data/downloads 的子路径。勿用 downloads 根目录做批量安装扫描。

    Returns:
        JSON 字符串：detected（含 mod_id、path、installed）、unknown 列表。
    """
    result = mod_ops.scan_local_folder(folder_path)
    return result


async def install_local_folder(
    folder_path: str,
    mod_ids: list[int] | None = None,
) -> str:
    """从文件夹批量本地安装（自动识别 ID、补依赖、跳过已安装）。

    Args:
        folder_path: 文件夹绝对路径或相对 downloads 的子路径（须为独立子文件夹，非 downloads 缓存根目录）。
        mod_ids: 可选，指定要安装的 Nexus 模组 ID 列表；传 null/省略则安装扫描到的全部根模组。

    Returns:
        JSON 字符串：succeeded、failed、skipped、results。
    """
    return await mod_ops.install_local_folder(
        folder_path,
        mod_ids=mod_ids,
        install_dependencies=True,
        skip_installed=True,
    )


async def uninstall_mod(mod_id: int, force: bool = False) -> str:
    """按卸载计划移除已安装模组（会检查反向依赖）。

    Args:
        mod_id: Nexus Mods 模组数字 ID（要卸载的模组）。
        force: 是否强制卸载。默认 false；当存在反向依赖且用户确认风险时传 true。

    Returns:
        JSON 字符串：removed_files_count、forced；含 error 时表示未卸载。
    """
    report = mod_ops.check_uninstall_report(mod_id)
    if not report.get("can_uninstall"):
        return _error_json(report.get("warnings", ["无法卸载"])[0])
    if not report.get("safe") and not force:
        return _error_json(
            "卸载可能影响其他已安装模组，请先卸载依赖方模组或使用 force=true",
            report=report,
        )
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return _error_json(f"Mod {mod_id} not in inventory")
        internal_id = mod.id
    installer = Installer()
    result = installer.uninstall(internal_id)
    return json.dumps(
        {
            "mod_id": mod_id,
            "removed_files_count": len(result.added_files),
            "restored_backups": len(result.backed_up_files),
            "removed_dirs": len(result.created_dirs),
            "forced": force,
        },
        ensure_ascii=False,
    )


async def list_mods() -> str:
    """列出本地库存中全部模组及安装状态（无参数）。

    Returns:
        JSON 数组：每项含 nexus_mod_id、name、status（installed/downloaded 等）、enabled。
    """
    with get_session() as session:
        mods = session.exec(select(Mod)).all()
    return json.dumps(
        [
            {
                "id": m.id,
                "nexus_mod_id": m.nexus_mod_id,
                "name": m.name,
                "version": m.version,
                "status": m.status.value if isinstance(m.status, ModStatus) else m.status,
                "enabled": m.enabled,
                "installed_at": str(m.installed_at) if m.installed_at else None,
            }
            for m in mods
        ],
        ensure_ascii=False,
    )


async def list_pending_mods() -> str:
    """列出待安装模组：已入库但尚未装进游戏目录（无参数）。

    Returns:
        JSON 字符串：count、mods 列表（含 nexus_mod_id、name、status）。
    """
    return health_audit.list_pending_mods()


async def list_incomplete_mods() -> str:
    """列出依赖不全模组：status=installed 但缺少必需依赖（无参数）。

    Returns:
        JSON 字符串：count、mods 列表（含 dependencies_missing_count）。
    """
    return health_audit.list_incomplete_mods()


async def check_mod_updates() -> str:
    """检查所有已安装模组在 Nexus 上是否有新版本（无参数，会请求 Nexus API）。

    Returns:
        JSON 字符串：update_count、updates（mod_id、installed_version、latest_version）。
    """
    return await health_audit.check_mod_updates()


async def audit_installation(auto_fix: bool = False) -> str:
    """一键审查安装健康状态（依赖、待装、更新、卸载记录）并生成建议。

    Args:
        auto_fix: 是否审查后自动修复。false=仅检测与建议；true=自动补依赖并重装有更新的模组。

    Returns:
        JSON 字符串：healthy、issues、incomplete、pending、updates、llm_report、auto_fix 结果。
    """
    return await health_audit.audit_installation(auto_fix=auto_fix)


async def get_uninstall_plan_tool(mod_id: int) -> str:
    """查看模组卸载计划（列出将删除/恢复的文件，不执行卸载）。

    Args:
        mod_id: Nexus Mods 模组数字 ID（已安装且有安装记录的模组）。

    Returns:
        JSON 字符串：added_files、backed_up_files 等；无记录时返回 error。
    """
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            return _error_json(f"Mod {mod_id} not in inventory")
        internal_id = mod.id
    plan = get_uninstall_plan(internal_id)
    if plan is None:
        return _error_json(f"No install record for mod {mod_id}")
    return json.dumps(plan.to_dict(), ensure_ascii=False)


class ModFunctionTool(FunctionTool):
    async def check_permissions(self, *_args, **_kwargs) -> PermissionDecision:
        return PermissionDecision(
            behavior=PermissionBehavior.ALLOW,
            message="模组管理工具已授权",
        )


SYSTEM_PROMPT = """你是赛博朋克 2077 模组管理助手。你可以帮助用户下载、安装、卸载和管理游戏模组。

【参数通则】
- mod_id / mod_ids：一律指 Nexus 网站模组数字 ID（如 27967），不是数据库 id、不是文件名。
- folder_path：本地文件夹绝对路径，或相对 downloads 的子路径；禁止对 downloads 缓存根目录批量「安装全部」。
- archive_name：本地 zip/7z 路径或 downloads 下的文件名。
- force：仅 uninstall_mod 使用，true 表示无视反向依赖警告强制卸载。
- auto_fix：仅 audit_installation 使用，true 才会自动补依赖与重装更新。

【工具与参数】
- search_mod(mod_id)
- check_dependencies(mod_id)
- install_mod_with_dependencies(mod_id) — 首选安装
- install_mods_batch(mod_ids) — 批量，mod_ids 为整数数组
- install_mod(mod_id) — 不自动装依赖
- install_local_mod(mod_id, archive_name)
- scan_local_folder_tool(folder_path)
- install_local_folder(folder_path, mod_ids=null)
- uninstall_mod(mod_id, force=false)
- list_mods() / list_pending_mods() / list_incomplete_mods() / check_mod_updates() — 无参
- audit_installation(auto_fix=false)
- get_uninstall_plan_tool(mod_id)

工作流程：
1. 用户提供模组 ID → search_mod → check_dependencies → install_mod_with_dependencies
2. 本地安装：scan_local_folder_tool → install_local_folder
3. 维护：list_incomplete_mods / list_pending_mods → check_mod_updates → audit_installation
4. Premium 下载失败：提示用户手动下载到 downloads（文件名含 mod_id）后 install_local_mod

报告规则：
- JSON 含 error 时不得声称成功
- added_files_count > 0 才算主模组安装成功
- 说明 dependencies_installed / dependencies_failed
"""


def build_toolkit() -> Toolkit:
    return Toolkit(
        tools=[
            ModFunctionTool(search_mod),
            ModFunctionTool(check_dependencies),
            ModFunctionTool(install_mod_with_dependencies),
            ModFunctionTool(install_mods_batch),
            ModFunctionTool(install_mod),
            ModFunctionTool(install_local_mod),
            ModFunctionTool(scan_local_folder_tool),
            ModFunctionTool(install_local_folder),
            ModFunctionTool(uninstall_mod),
            ModFunctionTool(list_mods),
            ModFunctionTool(list_pending_mods),
            ModFunctionTool(list_incomplete_mods),
            ModFunctionTool(check_mod_updates),
            ModFunctionTool(audit_installation),
            ModFunctionTool(get_uninstall_plan_tool),
        ]
    )


def build_agent(model: ChatModelBase) -> Agent:
    init_db()
    return Agent(
        name="CyberpunkModAgent",
        system_prompt=SYSTEM_PROMPT,
        model=model,
        toolkit=build_toolkit(),
    )
