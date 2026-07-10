# -*- coding: utf-8 -*-
"""FastAPI 路由测试。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from cyberpunk_mod_manager.api.app import app
from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.fixture
def client() -> TestClient:
    init_db()
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["nexus_configured"] is True
    assert data["llm_configured"] is True


def test_list_mods_empty(client: TestClient) -> None:
    resp = client.get("/api/mods")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    if data:
        assert "dependencies" in data[0]
        assert "summary_line" in data[0]


def test_delete_mod_not_found(client: TestClient) -> None:
    resp = client.delete("/api/mods/40404")
    assert resp.status_code == 404


def test_agent_chat_empty_message(client: TestClient) -> None:
    resp = client.post("/api/agent/chat", json={"message": "  "})
    assert resp.status_code == 400


def test_install_mod_mocked(client: TestClient) -> None:
    """使用 mock 服务层验证安装 API 链路。"""
    with patch(
        "cyberpunk_mod_manager.api.routes_mods.mod_ops.install_mod",
        new=AsyncMock(
            return_value=json.dumps(
                {
                    "mod_id": 1001,
                    "internal_id": 1,
                    "added_files_count": 1,
                    "name": "Mock Mod",
                    "uninstall_plan_preview": None,
                }
            )
        ),
    ):
        resp = client.post("/api/mods/install", json={"mod_id": 1001})

    assert resp.status_code == 200
    data = resp.json()
    assert data["mod_id"] == 1001
    assert data["name"] == "Mock Mod"
    assert data["added_files_count"] == 1
