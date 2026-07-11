# -*- coding: utf-8 -*-
"""Agent 工具参数文档测试。"""
from __future__ import annotations

import asyncio

from cyberpunk_mod_manager.agent.tools import build_toolkit

# 无参工具
NO_PARAM_TOOLS = {
    "list_mods",
    "list_pending_mods",
    "list_incomplete_mods",
    "check_mod_updates",
}


def test_all_tool_params_have_descriptions() -> None:
    tk = build_toolkit()
    schemas = asyncio.run(tk.get_tool_schemas())
    missing: list[str] = []
    for schema in schemas:
        fn = schema["function"]
        name = fn["name"]
        props = fn["parameters"].get("properties") or {}
        if not props:
            if name not in NO_PARAM_TOOLS:
                missing.append(f"{name}: no properties")
            continue
        for param, meta in props.items():
            desc = (meta.get("description") or "").strip()
            if not desc:
                missing.append(f"{name}.{param}")
    assert not missing, "缺少参数说明: " + ", ".join(missing)


def test_mod_id_param_mentions_nexus() -> None:
    tk = build_toolkit()
    schemas = asyncio.run(tk.get_tool_schemas())
    by_name = {s["function"]["name"]: s for s in schemas}
    for tool in ("search_mod", "install_mod", "check_dependencies"):
        desc = by_name[tool]["function"]["parameters"]["properties"]["mod_id"][
            "description"
        ]
        assert "Nexus" in desc or "nexus" in desc.lower()
