# -*- coding: utf-8 -*-
"""AgentScope Agent 工具注册。"""
from __future__ import annotations

import json

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
    """根据 Nexus 模组 ID 查询模组详情，并同步依赖关系。

    Args:
        mod_id: Nexus Mods 的模组 ID（整数）

    Returns:
        模组信息与依赖列表的 JSON 字符串
    """
    async with NexusClient() as client:
        details = await client.get_mod_details(mod_id)
    internal_id = await mod_ops.ensure_mod_in_inventory(mod_id)
    deps = await mod_ops.refresh_dependencies(mod_id)
    payload = details.model_dump()
    payload["dependencies"] = deps
    payload["internal_id"] = internal_id
    return json.dumps(payload, ensure_ascii=False)


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


async def install_local_mod(mod_id: int, archive_name: str) -> str:
    """从 downloads 目录中的本地压缩包安装模组（用于手动下载）。

    Args:
        mod_id: Nexus Mods 的模组 ID
        archive_name: downloads 目录下的文件名

    Returns:
        安装结果 JSON
    """
    archive_path = config.downloads_dir / archive_name
    await mod_ops.ensure_mod_in_inventory(mod_id)
    return mod_ops.install_from_archive(mod_id, archive_path)


async def uninstall_mod(mod_id: int) -> str:
    """按卸载计划移除已安装的模组。"""
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
- install_mod：仅安装单个模组（含 Premium 时本地压缩包回退）
- install_local_mod：从 downloads 目录的本地 zip 安装（手动下载后用）
- uninstall_mod：按记录卸载模组
- list_mods：列出已安装模组
- get_uninstall_plan_tool：查看卸载计划

工作流程：
1. 用户提供模组 ID → search_mod 查询信息与依赖
2. 调用 check_dependencies 查看缺失依赖
3. 调用 install_mod_with_dependencies 自动安装依赖和主模组
4. 若 premium_only 且安装失败，提示用户手动下载后放入 downloads 目录，
   文件名包含 mod_id，再调用 install_local_mod 或重试 install_mod

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
            ModFunctionTool(install_mod),
            ModFunctionTool(install_local_mod),
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
