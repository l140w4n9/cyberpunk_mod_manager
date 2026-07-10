# -*- coding: utf-8 -*-
"""Agent 流式 API 测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.agent.streaming import TOOL_LABELS, ToolCallRecord


def test_tool_labels_cover_known_tools() -> None:
    assert "install_mod" in TOOL_LABELS
    assert "search_mod" in TOOL_LABELS
    assert "check_dependencies" in TOOL_LABELS
    assert "install_mod_with_dependencies" in TOOL_LABELS


def test_stream_yields_tool_deltas() -> None:
    """流式事件应包含参数/结果增量类型（供前端时间线实时更新）。"""
    from cyberpunk_mod_manager.agent.streaming import run_agent_stream
    import inspect

    source = inspect.getsource(run_agent_stream)
    assert "tool_args_delta" in source
    assert "tool_result_delta" in source


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
