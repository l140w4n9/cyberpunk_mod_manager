# -*- coding: utf-8 -*-
"""Agent 聊天会话存储。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel import select

from ..models.chat_session import ChatSession
from ..storage.db import get_session

WELCOME_MESSAGE = {
    "id": "welcome",
    "role": "assistant",
    "content": (
        "你好！我是模组管理 Agent。给我一个 Nexus 模组 ID 或自然语言指令，"
        "我会展示完整的工具调用过程并自动安装。"
    ),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _preview(messages: list[dict[str, Any]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user" and item.get("content"):
            text = str(item["content"]).strip()
            return text[:40] + ("…" if len(text) > 40 else "")
        if item.get("role") == "turn" and item.get("reply"):
            text = str(item["reply"]).strip()
            return text[:40] + ("…" if len(text) > 40 else "")
    return ""


def list_sessions() -> list[dict[str, Any]]:
    with get_session() as session:
        rows = session.exec(
            select(ChatSession).order_by(ChatSession.updated_at.desc())
        ).all()
    result = []
    for row in rows:
        messages = json.loads(row.messages_json or "[]")
        result.append(
            {
                "id": row.id,
                "title": row.title or _preview(messages) or "新会话",
                "preview": _preview(messages),
                "message_count": len(messages),
                "created_at": row.created_at.isoformat(),
                "updated_at": row.updated_at.isoformat(),
            }
        )
    return result


def get_session_messages(session_id: str) -> dict[str, Any] | None:
    with get_session() as db:
        row = db.get(ChatSession, session_id)
        if row is None:
            return None
        messages = json.loads(row.messages_json or "[]")
        return {
            "id": row.id,
            "title": row.title,
            "messages": messages,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
        }


def create_session(title: str = "") -> dict[str, Any] | None:
    session_id = str(uuid.uuid4())
    messages = [WELCOME_MESSAGE]
    now = _utcnow()
    row = ChatSession(
        id=session_id,
        title=title or "新会话",
        messages_json=json.dumps(messages, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    )
    with get_session() as db:
        db.add(row)
        db.commit()
    return get_session_messages(session_id)  # type: ignore[return-value]


def save_session_messages(
    session_id: str,
    messages: list[dict[str, Any]],
    *,
    title: str | None = None,
) -> dict[str, Any] | None:
    with get_session() as db:
        row = db.get(ChatSession, session_id)
        if row is None:
            return None
        row.messages_json = json.dumps(messages, ensure_ascii=False)
        row.updated_at = _utcnow()
        if title is not None:
            row.title = title
        elif not row.title or row.title == "新会话":
            preview = _preview(messages)
            if preview:
                row.title = preview[:60]
        db.add(row)
        db.commit()
    return get_session_messages(session_id)


def delete_session(session_id: str) -> bool:
    with get_session() as db:
        row = db.get(ChatSession, session_id)
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
