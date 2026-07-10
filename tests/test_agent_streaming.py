# -*- coding: utf-8 -*-
"""Agent 流式 API 测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.agent.streaming import TOOL_LABELS, ToolCallRecord


def test_tool_labels_cover_known_tools() -> None:
    assert "install_mod" in TOOL_LABELS
    assert "search_mod" in TOOL_LABELS
    assert "check_dependencies" in TOOL_LABELS
    assert "install_mod_with_dependencies" in TOOL_LABELS


def test_tool_call_record_to_dict() -> None:
    record = ToolCallRecord(
        id="tc-1",
        name="search_mod",
        label="查询模组信息",
        arguments='{"mod_id": 123}',
        result='{"name": "test"}',
        state="success",
    )
    data = record.to_dict()
    assert data["name"] == "search_mod"
    assert data["arguments"]
    assert data["result"]
