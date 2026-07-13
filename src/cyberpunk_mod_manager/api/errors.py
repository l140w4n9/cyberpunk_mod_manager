# -*- coding: utf-8 -*-
"""API 结构化错误响应。"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from ..nexus.client import NexusAPIError
from ..nexus.oauth import NexusOAuthError


def api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if extra:
        detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


def raise_api_error(
    status_code: int,
    code: str,
    message: str,
    *,
    extra: dict[str, Any] | None = None,
) -> None:
    raise api_error(status_code, code, message, extra=extra)


def nexus_exception_to_http(exc: Exception) -> HTTPException:
    if isinstance(exc, NexusOAuthError):
        status = 401 if exc.code in {"NEXUS_NOT_CONNECTED", "NEXUS_OAUTH_DENIED"} else 502
        return api_error(status, exc.code, str(exc))
    if isinstance(exc, NexusAPIError):
        status = exc.status_code or 502
        if exc.is_premium_only:
            status = 403
        elif exc.code == "NEXUS_UNAUTHORIZED":
            status = 401
        elif exc.code == "NEXUS_NOT_FOUND":
            status = 404
        elif exc.code == "NEXUS_FORBIDDEN":
            status = 403
        return api_error(
            status,
            exc.code,
            str(exc),
            extra={"premium_only": exc.is_premium_only} if exc.is_premium_only else None,
        )
    return api_error(502, "NEXUS_API_ERROR", str(exc))
