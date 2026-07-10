# -*- coding: utf-8 -*-
"""Nexus 客户端认证测试。"""
from __future__ import annotations

import pytest

from cyberpunk_mod_manager.nexus.client import _build_headers


def test_build_headers_uses_single_apikey_header() -> None:
    headers = _build_headers("test-key-123")
    assert "apikey" in headers
    assert headers["apikey"] == "test-key-123"
    assert "apiKey" not in headers


@pytest.mark.asyncio
async def test_validate_key_with_real_config() -> None:
    """若本地配置了有效 key，验证应通过。"""
    import os

    from cyberpunk_mod_manager.config import config
    from cyberpunk_mod_manager.nexus.client import NexusClient

    if not config.nexus_api_key or os.environ.get("NEXUS_API_KEY") == "test-nexus-key":
        pytest.skip("未配置真实 nexus_api_key")

    async with NexusClient() as client:
        assert await client.validate_key() is True
