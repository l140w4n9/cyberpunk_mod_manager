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
from ..services import mod_ops
from ..storage.db import get_session, init_db


def _error_json(message: str, **extra) -> str:
    return mod_ops.error_json(message, **extra)


async def search_mod(mod_id: int) -> str:
    """根据 Nexus 模组 ID 查询模组详情，并同步依赖关系。"""
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
    """检查模组前置依赖是否已安装。

    Args:
        mod_id: Nexus Mods 的模组 ID

    Returns:
        依赖检查报告 JSON
    """
    await mod_ops.refresh_dependencies(mod_id)
    return mod_ops.check_dependencies_report(mod_id)


async def install_mod(mod_id: int) -> str:
    """下载并安装模组；Premium 限制时自动尝试本地压缩包。

    Args:
        mod_id: Nexus Mods 的模组 ID

    Returns:
        安装结果 JSON
    """
    return await mod_ops.install_mod(mod_id, allow_local_fallback=True)


async def install_mod_with_dependencies(mod_id: int) -> str:
    """安装模组并自动安装缺失的前置依赖。

    Args:
        mod_id: Nexus Mods 的模组 ID

    Returns:
        安装结果 JSON（含依赖安装摘要）
    """
    return await mod_ops.install_mod_with_dependencies(
        mod_id,
        install_dependencies=True,
        allow_local_fallback=True,
    )


async def install_mods_batch(mod_ids: list[int]) -> str:
    """批量安装多个模组（各自含缺失依赖）。

    Args:
        mod_ids: Nexus Mods 模组 ID 列表

    Returns:
        批量安装结果 JSON
    """
    results: list[dict] = []
    for mod_id in mod_ids:
        raw = await mod_ops.install_mod_with_dependencies(
            mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
        )
        data = json.loads(raw)
        data["mod_id"] = mod_id
        results.append(data)
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
    """从本地压缩包安装模组（downloads 目录或绝对路径）。

    Args:
        mod_id: Nexus Mods 的模组 ID
        archive_name: 文件名、相对 downloads 的路径或绝对路径

    Returns:
        安装结果 JSON
    """
    path = Path(archive_name)
    archive_path = path if path.is_absolute() else config.downloads_dir / archive_name
    await mod_ops.ensure_mod_in_inventory(mod_id)
    return mod_ops.install_from_archive(mod_id, archive_path)


async def scan_local_folder_tool(folder_path: str) -> str:
    """扫描本地文件夹，识别压缩包中的 Nexus 模组 ID。

    Args:
        folder_path: 文件夹路径（绝对路径或相对 downloads 目录）

    Returns:
        扫描结果 JSON，含 detected / unknown 列表
    """
    result = mod_ops.scan_local_folder(folder_path)
    return result


async def install_local_folder(
    folder_path: str,
    mod_ids: list[int] | None = None,
) -> str:
    """从文件夹批量本地安装：自动识别模组 ID 并安装依赖。

    Args:
        folder_path: 文件夹路径（绝对路径或相对 downloads 目录）
        mod_ids: 指定安装的模组 ID；为空则安装文件夹内识别到的根模组

    Returns:
        批量安装结果 JSON
    """
    return await mod_ops.install_local_folder(
        folder_path,
        mod_ids=mod_ids,
        install_dependencies=True,
        skip_installed=True,
    )


async def uninstall_mod(mod_id: int, force: bool = False) -> str:
    """按卸载计划移除已安装的模组（检查反向依赖）。"""
    report = mod_ops.check_uninstall_report(mod_id)
    if not report.get("can_uninstall"):
        return _error_json(report.get("warnings", ["无法卸载"])[0])
    if not report.get("safe") and not force:
        return _error_json(
            "卸载可能影响其他已安装模组，请先卸载依赖方模组或使用 force",
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
    """列出库存中所有模组及其状态。"""
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


async def get_uninstall_plan_tool(mod_id: int) -> str:
    """查看指定模组的卸载计划（不执行卸载）。"""
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

你的能力（通过工具调用）：
- search_mod：查询模组信息并同步依赖关系
- check_dependencies：检查前置依赖是否已安装
- install_mod_with_dependencies：安装模组并自动安装缺失依赖（首选）
- install_mods_batch：批量安装多个模组（用户说「全部安装」时用）
- install_mod：仅安装单个模组（含 Premium 时本地压缩包回退）
- install_local_mod：从单个本地压缩包安装
- scan_local_folder：扫描文件夹，自动识别模组 ID
- install_local_folder：从文件夹批量本地安装（自动识别 ID + 依赖）
- uninstall_mod：按记录卸载模组
- list_mods：列出已安装模组
- get_uninstall_plan_tool：查看卸载计划

工作流程：
1. 用户提供模组 ID → search_mod 查询信息与依赖
2. 调用 check_dependencies 查看缺失依赖
3. 调用 install_mod_with_dependencies 自动安装依赖和主模组
4. 本地安装：用户给出**独立子文件夹**路径（不要用 downloads 缓存目录做「安装全部」）
   → scan_local_folder_tool 扫描并查看 installed/pending 状态
   → install_local_folder 仅安装未安装的模组（已安装自动跳过）
5. 若 premium_only 且安装失败，提示用户手动下载后放入 downloads 目录，
   文件名包含 mod_id，再调用 install_local_mod / install_local_folder

报告规则：
- 返回 JSON 含 error 时不得声称安装成功
- added_files_count > 0 才算主模组安装成功
- 说明 dependencies_installed / dependencies_failed 摘要
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
