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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import ConfigError, config
from ..storage.db import init_db
from .routes_mods import router as mods_router
from .routes_agent import router as agent_router
from .routes_config import router as config_router

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

app.include_router(config_router, prefix="/api/config", tags=["config"])
app.include_router(mods_router, prefix="/api/mods", tags=["mods"])
app.include_router(agent_router, prefix="/api/agent", tags=["agent"])


@app.get("/api/health")
async def health() -> dict:
    """健康检查端点。"""
    nexus_valid = False
    if config.nexus_api_key:
        from ..nexus.client import NexusClient

        try:
            async with NexusClient() as client:
                nexus_valid = await client.validate_key()
        except Exception:
            nexus_valid = False
    return {
        "status": "ok",
        "game_path": config.game_path,
        "data_dir": str(config.data_dir) if config.has_data_dir else "",
        "data_dir_configured": config.has_data_dir,
        "config_file": config.config_file,
        "nexus_configured": bool(config.nexus_api_key),
        "nexus_valid": nexus_valid,
        "llm_configured": bool(config.openai_api_key),
    }


# 静态前端页面
app.mount(
    "/",
    StaticFiles(directory=str(WEB_DIR), html=True),
    name="web",
)
