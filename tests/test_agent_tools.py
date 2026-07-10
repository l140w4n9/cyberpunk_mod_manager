# -*- coding: utf-8 -*-
"""Agent 工具注册测试。"""
from __future__ import annotations

import asyncio

from agentscope.permission import PermissionBehavior

from cyberpunk_mod_manager.agent.tools import build_agent, build_toolkit


def test_toolkit_has_all_tools() -> None:
    tk = build_toolkit()
    schemas = asyncio.run(tk.get_tool_schemas())
    names = [s["function"]["name"] for s in schemas]
    assert names == [
        "search_mod",
        "check_dependencies",
        "install_mod_with_dependencies",
        "install_mod",
        "install_local_mod",
        "uninstall_mod",
        "list_mods",
        "get_uninstall_plan_tool",
    ]


def test_mod_tools_auto_allow_permissions() -> None:
    tk = build_toolkit()
    tool = asyncio.run(tk.get_tool("search_mod"))
    assert tool is not None
    decision = asyncio.run(tool.check_permissions())
    assert decision.behavior == PermissionBehavior.ALLOW


def test_build_agent_without_model_call() -> None:
    """验证 Agent 工厂可正常构建（不实际调用 LLM）。"""
    from unittest.mock import MagicMock

    mock_model = MagicMock()
    agent = build_agent(mock_model)
    assert agent.name == "CyberpunkModAgent"
    schemas = asyncio.run(agent.toolkit.get_tool_schemas())
    assert len(schemas) == 8
