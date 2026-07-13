# -*- coding: utf-8 -*-
"""Nexus 客户端认证测试。"""
from __future__ import annotations

import time

import pytest

from cyberpunk_mod_manager.nexus.auth_store import NexusTokens, clear_nexus_tokens, save_nexus_tokens


@pytest.mark.asyncio
async def test_nexus_client_requires_oauth_connection() -> None:
    from cyberpunk_mod_manager.nexus.client import NexusAPIError, NexusClient

    clear_nexus_tokens()
    with pytest.raises(NexusAPIError) as exc:
        NexusClient()
    assert exc.value.code == "NEXUS_NOT_CONNECTED"


@pytest.mark.asyncio
async def test_validate_auth_with_real_tokens() -> None:
    """若本地已通过 OAuth 连接，验证应通过。"""
    import os

    from cyberpunk_mod_manager.nexus.auth_store import has_nexus_tokens
    from cyberpunk_mod_manager.nexus.client import NexusClient

    if not has_nexus_tokens() or os.environ.get("CP2077_CONFIG", "").endswith("test_"):
        pytest.skip("未配置真实 Nexus OAuth 令牌")

    async with NexusClient() as client:
        assert await client.validate_auth() is True


def test_save_config_does_not_persist_legacy_api_key(tmp_path, monkeypatch) -> None:
    from cyberpunk_mod_manager.config import save_config

    monkeypatch.chdir(tmp_path)
    path = save_config(
        {
            "data_dir": str(tmp_path / "data"),
            "openai_api_key": "okey",
        }
    )
    text = path.read_text(encoding="utf-8")
    assert "nexus_api_key" not in text
    assert "nexus_oauth_client_id" not in text
