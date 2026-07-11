# -*- coding: utf-8 -*-
"""收藏夹 API 路由测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from cyberpunk_mod_manager.api.app import app
from cyberpunk_mod_manager.storage.db import init_db


@pytest.fixture
def client() -> TestClient:
    init_db()
    with TestClient(app) as c:
        yield c


def test_parse_collection_api(client: TestClient) -> None:
    mock_payload = {
        "collection": {
            "title": "Test",
            "slug": "iszwwe",
            "domain": "cyberpunk2077",
            "revision_number": 1,
            "mod_count": 1,
            "unique_mod_count": 1,
            "url": "https://example.com",
            "source_url": "https://example.com",
        },
        "queue": [
            {
                "mod_id": 100,
                "name": "A",
                "order": 1,
                "optional": False,
                "selected": True,
                "installed": False,
                "status": "pending",
                "message": "",
            }
        ],
        "stats": {"total": 1, "installed": 0, "pending": 1, "optional": 0, "selected": 1},
    }
    with patch(
        "cyberpunk_mod_manager.api.routes_collections.collection_ops.parse_collection_url_to_queue",
        new=AsyncMock(return_value=mock_payload),
    ):
        resp = client.post(
            "/api/collections/parse",
            json={"url": "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"},
        )
    assert resp.status_code == 200
    assert resp.json()["collection"]["slug"] == "iszwwe"


def test_get_missing_job_returns_404(client: TestClient) -> None:
    resp = client.get("/api/collections/jobs/does-not-exist")
    assert resp.status_code == 404
