# -*- coding: utf-8 -*-
"""配置读写 API。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..config import ConfigError, config, reload_config, save_config, save_ui_locale
from ..locale import normalize_locale
from ..storage.db import init_db, reload_db_engine
from .errors import raise_api_error

router = APIRouter()


class NexusStatusOut(BaseModel):
    connected: bool = False
    username: str = ""
    auth_method: str = ""


class ConfigOut(BaseModel):
    data_dir: str = ""
    game_path: str = ""
    game_domain: str = "cyberpunk2077"
    nexus: NexusStatusOut = Field(default_factory=NexusStatusOut)
    openai_configured: bool = False
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
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    allow_adult_content: bool = False
    install_plan_mode: str = "llm_first"
    ui_locale: str = "zh"


class LocaleUpdate(BaseModel):
    ui_locale: str = Field(..., min_length=2, max_length=8)


def _config_response(data: dict) -> ConfigOut:
    return ConfigOut(
        data_dir=data.get("data_dir", ""),
        game_path=data.get("game_path", ""),
        game_domain=data.get("game_domain", "cyberpunk2077"),
        nexus=NexusStatusOut(
            connected=bool(data.get("nexus_connected")),
            username=str(data.get("nexus_username") or ""),
            auth_method=str(data.get("nexus_auth_method") or ""),
        ),
        openai_configured=bool(data.get("openai_configured")),
        model_name=data.get("model_name", "gpt-4o-mini"),
        openai_base_url=data.get("openai_base_url", "https://api.openai.com/v1"),
        allow_adult_content=bool(data.get("allow_adult_content")),
        install_plan_mode=data.get("install_plan_mode", "llm_first"),
        ui_locale=data.get("ui_locale", "zh"),
        config_file=data.get("config_file", ""),
        has_data_dir=bool(data.get("has_data_dir")),
        downloads_dir=data.get("downloads_dir", ""),
        db_path=data.get("db_path", ""),
    )


@router.get("", response_model=ConfigOut)
async def get_config() -> ConfigOut:
    """获取当前配置（供前端设置页使用，不含任何密钥明文）。"""
    return _config_response(config.to_public_dict())


@router.put("", response_model=ConfigOut)
async def update_config(req: ConfigUpdate) -> ConfigOut:
    """保存配置到 config.yaml 并热重载。"""
    try:
        path = save_config(req.model_dump())
    except ConfigError as exc:
        raise_api_error(400, "CONFIG_INVALID", str(exc))

    reload_db_engine()
    init_db()

    from ..installer.profile import reload_install_profile

    reload_install_profile()

    from .routes_agent import reset_model

    reset_model()

    data = reload_config().to_public_dict()
    data["config_file"] = str(path)
    return _config_response(data)


@router.put("/locale", response_model=ConfigOut)
async def update_locale(req: LocaleUpdate) -> ConfigOut:
    """仅更新 UI / LLM 回复语言。"""
    try:
        path = save_ui_locale(req.ui_locale)
    except ConfigError as exc:
        raise_api_error(400, "CONFIG_INVALID", str(exc))
    data = reload_config().to_public_dict()
    data["config_file"] = str(path)
    data["ui_locale"] = normalize_locale(req.ui_locale)
    return _config_response(data)
