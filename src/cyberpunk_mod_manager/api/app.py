# -*- coding: utf-8 -*-
"""FastAPI 应用入口。

提供两类接口：
1. REST 路由：模组 CRUD、安装/卸载、卸载计划查询
2. Agent 路由：通过 AgentScope Agent 处理自然语言请求（给出 mod_id 自动安装）

启动：uvicorn cyberpunk_mod_manager.api.app:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import ConfigError, config
from ..locale import reset_request_locale, resolve_locale, set_request_locale
from ..storage.db import init_db
from .routes_mods import router as mods_router
from .routes_agent import router as agent_router
from .routes_config import router as config_router
from .routes_collections import router as collections_router
from .routes_nexus_auth import router as nexus_auth_router

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时确保数据目录存在并初始化数据库。"""
    if config.has_data_dir:
        try:
            config.ensure_dirs()
            init_db()
        except ConfigError:
            pass
    yield


app = FastAPI(title="Cyberpunk 2077 Mod Manager", lifespan=lifespan)


class LocaleMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        locale = resolve_locale(
            header_locale=request.headers.get("X-Locale"),
            accept_language=request.headers.get("Accept-Language"),
            config_locale=config.ui_locale,
        )
        token = set_request_locale(locale)
        try:
            return await call_next(request)
        finally:
            reset_request_locale(token)


app.add_middleware(LocaleMiddleware)

app.include_router(config_router, prefix="/api/config", tags=["config"])
app.include_router(nexus_auth_router, prefix="/api/nexus/auth", tags=["nexus-auth"])
app.include_router(collections_router, prefix="/api/collections", tags=["collections"])
app.include_router(mods_router, prefix="/api/mods", tags=["mods"])
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])


@app.get("/api/health")
async def health(quick: bool = False) -> dict:
    """健康检查端点。quick=1 时跳过 Nexus 校验，用于前端连通性预检。"""
    import os

    nexus_valid = False
    nexus_user: dict = {}
    from ..nexus.auth_store import has_nexus_tokens, load_nexus_tokens

    if has_nexus_tokens() and not quick:
        from ..nexus.client import NexusAPIError, NexusClient

        try:
            async with NexusClient() as client:
                nexus_valid = await client.validate_auth()
                if nexus_valid:
                    profile = await client.get_user_profile()
                    if profile is not None:
                        nexus_user = profile.model_dump()
        except NexusAPIError:
            nexus_valid = False
        except Exception:
            nexus_valid = False
    elif has_nexus_tokens() and quick:
        nexus_valid = True
        tokens = load_nexus_tokens()
        if tokens and tokens.username:
            nexus_user = {
                "name": tokens.username,
                "user_id": tokens.user_id,
                "is_premium": tokens.is_premium,
            }
    from ..nexus.rate_limit import get_snapshot

    return {
        "status": "ok",
        "server_port": int(os.environ.get("CP2077_PORT") or 0) or None,
        "game_path": config.game_path,
        "data_dir": str(config.data_dir) if config.has_data_dir else "",
        "data_dir_configured": config.has_data_dir,
        "config_file": config.config_file,
        "nexus_configured": has_nexus_tokens(),
        "nexus_valid": nexus_valid,
        "nexus_user": nexus_user,
        "nexus_premium": bool(nexus_user.get("is_premium")),
        "nexus_rate_limit": get_snapshot().to_dict(),
        "llm_configured": bool(config.openai_api_key),
        "ui_locale": config.ui_locale,
    }


# 静态前端：/assets 资源 + SPA 回退（刷新子路径仍返回 index.html）
assets_dir = WEB_DIR / "assets"
if assets_dir.is_dir():
    app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/{full_path:path}")
async def serve_spa(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(404)
    if full_path.startswith("assets/"):
        raise HTTPException(404)
    candidate = WEB_DIR / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    return FileResponse(WEB_DIR / "index.html")
