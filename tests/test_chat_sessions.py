# -*- coding: utf-8 -*-
"""Agent 会话存储测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.services import chat_sessions
from cyberpunk_mod_manager.storage.db import init_db


def test_create_and_save_session() -> None:
    init_db()
    created = chat_sessions.create_session("测试会话")
    assert created is not None
    session_id = created["id"]
    messages = [
        {"id": "welcome", "role": "assistant", "content": "hi"},
        {"id": "u1", "role": "user", "content": "安装 11937"},
    ]
    saved = chat_sessions.save_session_messages(session_id, messages)
    assert saved is not None
    assert len(saved["messages"]) == 2
    loaded = chat_sessions.get_session_messages(session_id)
    assert loaded is not None
    assert loaded["messages"][1]["content"] == "安装 11937"
    assert chat_sessions.delete_session(session_id)
