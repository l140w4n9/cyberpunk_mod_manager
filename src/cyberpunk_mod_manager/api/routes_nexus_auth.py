# -*- coding: utf-8 -*-
"""Nexus Mods OAuth 授权路由。"""
from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from ..nexus.auth_store import has_nexus_tokens, load_nexus_tokens
from ..nexus.oauth import (
    NexusOAuthError,
    disconnect_nexus,
    exchange_authorization_code,
    start_oauth_flow,
)
from .errors import api_error

router = APIRouter()


def _server_port() -> int:
    raw = os.environ.get("CP2077_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return 8000


@router.get("/status")
async def nexus_auth_status() -> dict:
    tokens = load_nexus_tokens()
    return {
        "connected": has_nexus_tokens(),
        "username": tokens.username if tokens else "",
        "user_id": tokens.user_id if tokens else 0,
        "is_premium": bool(tokens and tokens.is_premium),
        "auth_method": "oauth" if has_nexus_tokens() else "",
    }


@router.post("/start")
async def nexus_auth_start() -> dict:
    try:
        return start_oauth_flow(port=_server_port())
    except NexusOAuthError as exc:
        raise api_error(400, exc.code, str(exc)) from exc


@router.get("/callback")
async def nexus_auth_callback(
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
) -> HTMLResponse:
    if error:
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:24px">
        <p>授权失败：{error}</p>
        <script>window.opener?.postMessage({{type:'nexus-oauth-error',error:{error!r}}}, '*');</script>
        </body></html>"""
        return HTMLResponse(html, status_code=400)
    if not code or not state:
        raise HTTPException(400, "缺少 OAuth code 或 state")
    try:
        tokens = await exchange_authorization_code(state=state, code=code)
    except NexusOAuthError as exc:
        html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:24px">
        <p>{exc}</p>
        <script>window.opener?.postMessage({{type:'nexus-oauth-error',error:{str(exc)!r}}}, '*');</script>
        </body></html>"""
        return HTMLResponse(html, status_code=400)
    username = tokens.username or "Nexus 用户"
    html = f"""<!DOCTYPE html><html><body style="font-family:sans-serif;padding:24px">
    <p>已连接 Nexus 账户：{username}</p>
    <p>可以关闭此窗口。</p>
    <script>window.opener?.postMessage({{type:'nexus-oauth-complete',username:{username!r}}}, '*'); window.close();</script>
    </body></html>"""
    return HTMLResponse(html)


@router.delete("")
async def nexus_auth_disconnect() -> dict:
    disconnect_nexus()
    return {"connected": False}
