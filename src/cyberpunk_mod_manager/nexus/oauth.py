# -*- coding: utf-8 -*-
"""Nexus Mods OAuth 2.0 + PKCE。"""
from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx

from .auth_store import NexusTokens, clear_nexus_tokens, load_nexus_tokens, save_nexus_tokens
from .credentials import get_oauth_client_id

logger = logging.getLogger(__name__)

NEXUS_AUTHORIZE_URL = "https://users.nexusmods.com/oauth/authorize"
NEXUS_TOKEN_URL = "https://users.nexusmods.com/oauth/token"

_pending_sessions: dict[str, dict[str, Any]] = {}
_SESSION_TTL_SECONDS = 600


class NexusOAuthError(RuntimeError):
    def __init__(self, message: str, *, code: str = "NEXUS_OAUTH_ERROR") -> None:
        super().__init__(message)
        self.code = code


def _purge_expired_sessions() -> None:
    now = time.time()
    expired = [
        state
        for state, row in _pending_sessions.items()
        if now - float(row.get("created_at") or 0) > _SESSION_TTL_SECONDS
    ]
    for state in expired:
        _pending_sessions.pop(state, None)


def generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    if len(verifier) < 43:
        verifier = verifier + secrets.token_hex(8)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_redirect_uri(port: int) -> str:
    return f"http://127.0.0.1:{port}/api/nexus/auth/callback"


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": "",
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge_method": "S256",
        "code_challenge": code_challenge,
    }
    return f"{NEXUS_AUTHORIZE_URL}?{urlencode(params)}"


def start_oauth_flow(*, port: int) -> dict[str, str]:
    client_id = get_oauth_client_id()
    if not client_id:
        raise NexusOAuthError(
            "应用未配置 OAuth Client ID（需由开发者向 Nexus 注册后写入）",
            code="NEXUS_OAUTH_NOT_CONFIGURED",
        )
    _purge_expired_sessions()
    verifier, challenge = generate_pkce_pair()
    state = str(uuid.uuid4())
    redirect_uri = build_redirect_uri(port)
    _pending_sessions[state] = {
        "code_verifier": verifier,
        "redirect_uri": redirect_uri,
        "created_at": time.time(),
    }
    return {
        "state": state,
        "authorize_url": build_authorize_url(
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            code_challenge=challenge,
        ),
        "redirect_uri": redirect_uri,
    }


def _tokens_from_response(body: dict[str, Any]) -> NexusTokens:
    access = str(body.get("access_token") or "")
    refresh = str(body.get("refresh_token") or "")
    if not access or not refresh:
        raise NexusOAuthError("Nexus 未返回有效令牌", code="NEXUS_OAUTH_TOKEN_MISSING")
    expires_in = int(body.get("expires_in") or 3600)
    return NexusTokens(
        access_token=access,
        refresh_token=refresh,
        expires_at=time.time() + expires_in,
    )


def _apply_profile_from_jwt(tokens: NexusTokens) -> NexusTokens:
    from .jwt_verify import verify_access_token

    payload = verify_access_token(tokens.access_token)
    if not payload:
        return tokens
    user = payload.get("user") or {}
    roles = user.get("membership_roles") or []
    tokens.username = str(user.get("username") or tokens.username)
    tokens.user_id = int(user.get("id") or payload.get("sub") or 0)
    tokens.is_premium = any(
        role in {"premium", "lifetimepremium", "supporter"}
        for role in roles
    )
    return tokens


async def _post_token_form(data: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            NEXUS_TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    if response.is_error:
        text = response.text[:300]
        if response.status_code in {400, 401}:
            raise NexusOAuthError(
                "OAuth 授权失败或已过期，请重新连接 Nexus 账户",
                code="NEXUS_OAUTH_DENIED",
            )
        raise NexusOAuthError(
            f"Nexus OAuth HTTP {response.status_code}: {text}",
            code="NEXUS_OAUTH_HTTP_ERROR",
        )
    body = response.json()
    if not isinstance(body, dict):
        raise NexusOAuthError("Nexus OAuth 返回格式无效", code="NEXUS_OAUTH_INVALID")
    return body


async def exchange_authorization_code(*, state: str, code: str) -> NexusTokens:
    _purge_expired_sessions()
    session = _pending_sessions.pop(state, None)
    if session is None:
        raise NexusOAuthError("OAuth 会话无效或已过期", code="NEXUS_OAUTH_STATE_INVALID")
    client_id = get_oauth_client_id()
    body = await _post_token_form(
        {
            "grant_type": "authorization_code",
            "redirect_uri": str(session["redirect_uri"]),
            "client_id": client_id,
            "code": code,
            "code_verifier": str(session["code_verifier"]),
            "scope": "",
        }
    )
    tokens = _apply_profile_from_jwt(_tokens_from_response(body))
    save_nexus_tokens(tokens)
    return tokens


async def refresh_access_token(tokens: NexusTokens | None = None) -> NexusTokens:
    current = tokens or load_nexus_tokens()
    if current is None:
        raise NexusOAuthError("未连接 Nexus 账户", code="NEXUS_NOT_CONNECTED")
    if not current.is_expired:
        return current
    client_id = get_oauth_client_id()
    body = await _post_token_form(
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": current.refresh_token,
        }
    )
    refreshed = _tokens_from_response(body)
    refreshed.refresh_token = str(body.get("refresh_token") or current.refresh_token)
    refreshed.username = current.username
    refreshed.user_id = current.user_id
    refreshed.is_premium = current.is_premium
    refreshed = _apply_profile_from_jwt(refreshed)
    save_nexus_tokens(refreshed)
    return refreshed


async def ensure_access_token() -> str:
    tokens = await refresh_access_token()
    return tokens.access_token


def disconnect_nexus() -> None:
    clear_nexus_tokens()
