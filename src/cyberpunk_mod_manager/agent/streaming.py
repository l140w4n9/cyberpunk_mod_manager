# -*- coding: utf-8 -*-
"""Agent 流式事件收集与 SSE 序列化。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from agentscope.agent import Agent
from agentscope.event import (
    TextBlockDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
    ToolResultEndEvent,
    ToolResultTextDeltaEvent,
)
from agentscope.message import Msg, UserMsg

TOOL_LABELS = {
    "search_mod": "查询模组信息",
    "check_dependencies": "检查前置依赖",
    "install_mod_with_dependencies": "安装模组及依赖",
    "install_mods_batch": "批量安装模组",
    "install_mod": "下载并安装模组",
    "install_local_mod": "本地压缩包安装",
    "uninstall_mod": "卸载模组",
    "list_mods": "列出库存模组",
    "get_uninstall_plan_tool": "查看卸载计划",
}


@dataclass
class ToolCallRecord:
    """单次工具调用记录。"""

    id: str
    name: str
    label: str
    arguments: str = ""
    result: str = ""
    state: str = "running"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "arguments": self.arguments,
            "result": self.result,
            "state": self.state,
        }


@dataclass
class AgentRunResult:
    """一次 Agent 对话的完整结果。"""

    reply: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)


def _format_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _truncate(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (已截断)"


async def run_agent_stream(
    agent: Agent,
    msg: UserMsg,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    """消费 Agent reply_stream，产出前端可消费的 SSE 事件。"""
    tools: dict[str, ToolCallRecord] = {}
    reply_parts: list[str] = []
    final_msg: Msg | None = None

    async for evt in agent.reply_stream(msg):
        if isinstance(evt, Msg):
            final_msg = evt
            continue

        if isinstance(evt, ToolCallStartEvent):
            record = ToolCallRecord(
                id=evt.tool_call_id,
                name=evt.tool_call_name,
                label=TOOL_LABELS.get(evt.tool_call_name, evt.tool_call_name),
            )
            tools[evt.tool_call_id] = record
            yield "tool_start", record.to_dict()
            continue

        if isinstance(evt, ToolCallDeltaEvent):
            record = tools.get(evt.tool_call_id)
            if record is not None:
                record.arguments += evt.delta or ""
                yield "tool_args_delta", {
                    "id": evt.tool_call_id,
                    "delta": evt.delta or "",
                    "arguments": _truncate(record.arguments, 4000),
                }
            continue

        if isinstance(evt, ToolCallEndEvent):
            record = tools.get(evt.tool_call_id)
            if record is not None:
                yield "tool_args", {
                    "id": record.id,
                    "arguments": _truncate(record.arguments),
                }
            continue

        if isinstance(evt, ToolResultTextDeltaEvent):
            record = tools.get(evt.tool_call_id)
            if record is not None:
                record.result += evt.delta or ""
                yield "tool_result_delta", {
                    "id": evt.tool_call_id,
                    "delta": evt.delta or "",
                    "result": _truncate(record.result, 4000),
                }
            continue

        if isinstance(evt, ToolResultEndEvent):
            record = tools.get(evt.tool_call_id)
            if record is not None:
                record.state = str(evt.state)
                yield "tool_result", {
                    "id": record.id,
                    "result": _truncate(record.result),
                    "state": record.state,
                }
            continue

        if isinstance(evt, TextBlockDeltaEvent):
            reply_parts.append(evt.delta or "")
            yield "text_delta", {"delta": evt.delta or ""}

    if final_msg is not None:
        reply = final_msg.get_text_content() or "".join(reply_parts)
    else:
        reply = "".join(reply_parts)

    yield "done", {
        "reply": reply,
        "tool_calls": [t.to_dict() for t in tools.values()],
    }


async def run_agent_collect(agent: Agent, msg: UserMsg) -> AgentRunResult:
    """非流式收集 Agent 结果（含工具调用记录）。"""
    result = AgentRunResult()
    async for event, data in run_agent_stream(agent, msg):
        if event == "text_delta":
            result.reply += data.get("delta", "")
        elif event == "done":
            result.reply = data.get("reply", result.reply)
            result.tool_calls = [
                ToolCallRecord(
                    id=t["id"],
                    name=t["name"],
                    label=t.get("label", t["name"]),
                    arguments=t.get("arguments", ""),
                    result=t.get("result", ""),
                    state=t.get("state", "done"),
                )
                for t in data.get("tool_calls", [])
            ]
    return result
