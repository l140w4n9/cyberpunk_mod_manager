# -*- coding: utf-8 -*-
"""配置读写 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import ConfigError, config, reload_config, save_config, save_ui_locale
from ..locale import normalize_locale
from ..storage.db import init_db, reload_db_engine

router = APIRouter()


class ConfigOut(BaseModel):
    data_dir: str = ""
    game_path: str = ""
    game_domain: str = "cyberpunk2077"
    nexus_api_key: str = ""
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    allow_adult_content: bool = False
    install_plan_mode: str = "llm_first"
    ui_locale: str = "zh"
    config_file: str = ""
    has_data_dir: bool = False
    downloads_dir: str = ""
    db_path: str = ""


class ConfigUpdate(BaseModel):
    data_dir: str = Field(..., min_length=1, description="数据存放目录（必填）")
    game_path: str = ""
    game_domain: str = "cyberpunk2077"
    nexus_api_key: str = ""
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    allow_adult_content: bool = False
    install_plan_mode: str = "llm_first"
    ui_locale: str = "zh"


class LocaleUpdate(BaseModel):
    ui_locale: str = Field(..., min_length=2, max_length=8)


@router.get("", response_model=ConfigOut)
async def get_config() -> ConfigOut:
    """获取当前配置（供前端设置页使用）。"""
    return ConfigOut(**config.to_public_dict())


@router.put("", response_model=ConfigOut)
async def update_config(req: ConfigUpdate) -> ConfigOut:
    """保存配置到 config.yaml 并热重载。"""
    try:
        path = save_config(req.model_dump())
    except ConfigError as exc:
        raise HTTPException(400, str(exc)) from exc

    reload_db_engine()
    init_db()

    from ..installer.profile import reload_install_profile

    reload_install_profile()

    # Agent LLM 单例在 routes_agent 中按新配置重建
    from .routes_agent import reset_model

    reset_model()

    data = reload_config().to_public_dict()
    data["config_file"] = str(path)
    return ConfigOut(**data)


@router.put("/locale", response_model=ConfigOut)
async def update_locale(req: LocaleUpdate) -> ConfigOut:
    """仅更新 UI / LLM 回复语言。"""
    try:
        path = save_ui_locale(req.ui_locale)
    except ConfigError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = reload_config().to_public_dict()
    data["config_file"] = str(path)
    data["ui_locale"] = normalize_locale(req.ui_locale)
    return ConfigOut(**data)
