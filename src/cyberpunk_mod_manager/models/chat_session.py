# -*- coding: utf-8 -*-
"""Agent 聊天会话模型。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(SQLModel, table=True):
    """Agent 对话会话，消息以 JSON 数组存储。"""

    id: str = Field(primary_key=True)
    title: str = Field(default="")
    messages_json: str = Field(default="[]")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
