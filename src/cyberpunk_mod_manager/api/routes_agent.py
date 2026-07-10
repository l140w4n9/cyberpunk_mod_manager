# -*- coding: utf-8 -*-
"""Agent 路由：接收自然语言或 mod_id，交由 AgentScope Agent 处理。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentscope.message import UserMsg

from ..agent.streaming import _format_sse, run_agent_collect, run_agent_stream
from ..agent.tools import build_agent
from ..config import config

router = APIRouter()

_MODEL = None


def _get_model():
    global _MODEL
    if _MODEL is None:
        if not config.openai_api_key:
            raise HTTPException(
                503,
                "未配置 openai_api_key，请在 config.yaml 或环境变量 OPENAI_API_KEY 中设置",
            )
        from agentscope.credential import OpenAICredential
        from agentscope.model import OpenAIChatModel

        _MODEL = OpenAIChatModel(
            credential=OpenAICredential(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url,
            ),
            model=config.model_name,
        )
    return _MODEL


class AgentRequest(BaseModel):
    message: str


class ToolCallOut(BaseModel):
    id: str
    name: str
    label: str
    arguments: str = ""
    result: str = ""
    state: str = "running"


class AgentResponse(BaseModel):
    reply: str
    mod_id: Optional[int] = None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)


def _build_user_message(text: str, raw: str) -> UserMsg:
    if text.isdigit():
        content = (
            f"请帮我安装模组 ID 为 {text} 的模组，"
            "完成后告诉我安装结果和卸载方式。"
        )
    else:
        content = raw
    return UserMsg(content=content, name="user")


@router.post("/chat", response_model=AgentResponse)
async def chat(req: AgentRequest) -> AgentResponse:
    """与 Agent 对话（返回完整结果及工具调用记录）。"""
    text = req.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")
    agent = build_agent(_get_model())
    msg = _build_user_message(text, req.message)
    try:
        result = await run_agent_collect(agent, msg)
    except Exception as exc:
        raise HTTPException(500, f"Agent 处理失败: {exc}") from exc
    return AgentResponse(
        reply=result.reply,
        mod_id=int(text) if text.isdigit() else None,
        tool_calls=[ToolCallOut(**t.to_dict()) for t in result.tool_calls],
    )


@router.post("/chat/stream")
async def chat_stream(req: AgentRequest) -> StreamingResponse:
    """SSE 流式对话，实时推送工具调用过程。"""

    text = req.message.strip()
    if not text:
        raise HTTPException(400, "消息不能为空")

    agent = build_agent(_get_model())
    msg = _build_user_message(text, req.message)

    async def event_generator():
        try:
            async for event, data in run_agent_stream(agent, msg):
                payload = dict(data)
                if event == "done" and text.isdigit():
                    payload["mod_id"] = int(text)
                yield _format_sse(event, payload)
        except Exception as exc:
            yield _format_sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
