# -*- coding: utf-8 -*-
"""Nexus OAuth 与 Bearer 认证测试。"""
from __future__ import annotations

import base64
import json
import time

import pytest

from cyberpunk_mod_manager.nexus.auth_store import (
    NexusTokens,
    clear_nexus_tokens,
    has_nexus_tokens,
    save_nexus_tokens,
)
from cyberpunk_mod_manager.nexus.oauth import (
    build_authorize_url,
    build_redirect_uri,
    generate_pkce_pair,
    start_oauth_flow,
)


def test_generate_pkce_pair_lengths() -> None:
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert challenge
    assert "=" not in challenge


def test_build_authorize_url_contains_pkce_params() -> None:
    verifier, challenge = generate_pkce_pair()
    url = build_authorize_url(
        client_id="test-client",
        redirect_uri="http://127.0.0.1:8000/api/nexus/auth/callback",
        state="state-123",
        code_challenge=challenge,
    )
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert "client_id=test-client" in url
    assert verifier  # used in session, not URL


def test_build_redirect_uri_uses_port() -> None:
    assert build_redirect_uri(8123).endswith("/api/nexus/auth/callback")


def test_token_roundtrip_encrypted_storage() -> None:
    clear_nexus_tokens()
    save_nexus_tokens(
        NexusTokens(
            access_token="access-1",
            refresh_token="refresh-1",
            expires_at=time.time() + 3600,
            username="demo",
            user_id=42,
            is_premium=True,
        )
    )
    assert has_nexus_tokens()
    clear_nexus_tokens()
    assert not has_nexus_tokens()


def test_start_oauth_flow_requires_client_id(monkeypatch) -> None:
    from cyberpunk_mod_manager.nexus.oauth import NexusOAuthError, start_oauth_flow

    monkeypatch.delenv("NEXUS_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setattr(
        "cyberpunk_mod_manager.nexus.credentials.NEXUS_OAUTH_CLIENT_ID",
        "",
    )
    with pytest.raises(NexusOAuthError) as exc:
        start_oauth_flow(port=8000)
    assert exc.value.code == "NEXUS_OAUTH_NOT_CONFIGURED"


def test_start_oauth_flow_returns_authorize_url(monkeypatch) -> None:
    monkeypatch.setenv("NEXUS_OAUTH_CLIENT_ID", "public_test")
    result = start_oauth_flow(port=8000)
    assert result["authorize_url"].startswith("https://users.nexusmods.com/oauth/authorize")
    assert result["state"]


@pytest.mark.asyncio
async def test_build_nexus_headers_uses_bearer(monkeypatch) -> None:
    from cyberpunk_mod_manager.nexus.client import build_nexus_headers

    header = base64.urlsafe_b64encode(
        json.dumps({"user": {"username": "u1", "id": 1, "membership_roles": []}}).encode()
    ).decode().rstrip("=")
    fake_jwt = f"aaa.{header}.bbb"
    save_nexus_tokens(
        NexusTokens(
            access_token=fake_jwt,
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )
    )

    async def _fake_refresh(tokens=None):
        return NexusTokens(
            access_token=fake_jwt,
            refresh_token="refresh",
            expires_at=time.time() + 3600,
        )

    monkeypatch.setattr(
        "cyberpunk_mod_manager.nexus.oauth.refresh_access_token",
        _fake_refresh,
    )
    headers = await build_nexus_headers()
    assert headers["Authorization"] == f"Bearer {fake_jwt}"
    assert "apikey" not in headers
    clear_nexus_tokens()
