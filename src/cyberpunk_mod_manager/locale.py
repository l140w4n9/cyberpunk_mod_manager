# -*- coding: utf-8 -*-
"""UI 语言上下文：请求头 X-Locale 优先，其次 config.ui_locale。"""
from __future__ import annotations

from contextvars import ContextVar, Token

_LOCALE: ContextVar[str] = ContextVar("ui_locale", default="")


def normalize_locale(value: str | None) -> str:
    if not value:
        return "zh"
    lang = str(value).strip().lower().replace("_", "-")
    if lang.startswith("en"):
        return "en"
    if lang.startswith("zh"):
        return "zh"
    return "zh"


def parse_accept_language(header: str | None) -> str:
    if not header:
        return "zh"
    for part in header.split(","):
        token = part.split(";")[0].strip().lower()
        if token.startswith("en"):
            return "en"
        if token.startswith("zh"):
            return "zh"
    return "zh"


def resolve_locale(
    *,
    header_locale: str | None = None,
    accept_language: str | None = None,
    config_locale: str | None = None,
) -> str:
    if header_locale:
        return normalize_locale(header_locale)
    if accept_language:
        return parse_accept_language(accept_language)
    if config_locale:
        return normalize_locale(config_locale)
    return "zh"


def set_request_locale(locale: str) -> Token:
    return _LOCALE.set(normalize_locale(locale))


def reset_request_locale(token: Token) -> None:
    _LOCALE.reset(token)


def get_request_locale() -> str:
    current = _LOCALE.get()
    if current:
        return normalize_locale(current)
    from .config import config

    return normalize_locale(getattr(config, "ui_locale", "zh") or "zh")


def effective_locale(explicit: str | None = None) -> str:
    if explicit:
        return normalize_locale(explicit)
    return get_request_locale()
