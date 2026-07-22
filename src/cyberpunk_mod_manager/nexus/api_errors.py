# -*- coding: utf-8 -*-
"""Nexus API 错误类型与 HTTP 响应解析。"""
from __future__ import annotations

from typing import Any

import httpx

from .rate_limit import parse_retry_after


class NexusAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        is_premium_only: bool = False,
        code: str = "NEXUS_API_ERROR",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_premium_only = is_premium_only
        self.code = code


def _parse_problem_details(response: httpx.Response) -> dict[str, Any] | None:
    content_type = (response.headers.get("content-type") or "").lower()
    if "json" not in content_type and response.status_code not in {
        400,
        401,
        403,
        404,
        422,
        429,
    }:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def parse_api_error(response: httpx.Response) -> NexusAPIError:
    problem = _parse_problem_details(response)
    detail = str((problem or {}).get("detail") or "").strip()
    title = str((problem or {}).get("title") or "").strip()
    body = response.text
    lower = (detail or body).lower()
    is_premium_only = (
        response.status_code == 403
        and "premium" in lower
        and ("download" in lower or "subscription" in lower)
    )
    if response.status_code == 429:
        retry = parse_retry_after(response)
        suffix = f"（约 {int(retry)} 秒后重试）" if retry else ""
        message = (
            detail
            or title
            or f"Nexus API 请求频率超限，请稍后重试{suffix}"
        )
        code = "NEXUS_RATE_LIMIT"
    elif response.status_code == 401:
        message = detail or title or "Nexus 授权无效或已过期，请重新连接账户。"
        code = "NEXUS_UNAUTHORIZED"
    elif is_premium_only:
        message = (
            detail
            or title
            or "非 Premium 账户无法通过 API 获取下载链接，请在网站手动下载后放入 downloads 目录。"
        )
        code = "NEXUS_PREMIUM_REQUIRED"
    elif response.status_code == 403:
        message = detail or title or "Nexus API 拒绝访问该资源。"
        code = "NEXUS_FORBIDDEN"
    elif response.status_code == 404:
        message = detail or title or "Nexus 资源不存在。"
        code = "NEXUS_NOT_FOUND"
    elif response.status_code == 422:
        message = detail or title or "Nexus 请求参数无效。"
        code = "NEXUS_VALIDATION_ERROR"
    else:
        message = (
            detail
            or title
            or f"Nexus API HTTP {response.status_code}: {body or response.reason_phrase}"
        )
        code = "NEXUS_API_ERROR"
    return NexusAPIError(
        message,
        status_code=response.status_code,
        is_premium_only=is_premium_only,
        code=code,
    )
