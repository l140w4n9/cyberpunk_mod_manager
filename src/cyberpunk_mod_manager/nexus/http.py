# -*- coding: utf-8 -*-
"""Nexus HTTP 请求：429 重试、Retry-After、指数退避、配额头解析。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from .api_errors import parse_api_error
from .rate_limit import compute_retry_delay, update_from_response

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


async def request_with_retry(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    client: httpx.AsyncClient | None = None,
    treat_404_as_ok: bool = False,
    **kwargs: Any,
) -> httpx.Response:
    """发送 Nexus API 请求，处理 429 与配额响应头。"""
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    last_response: httpx.Response | None = None
    try:
        for attempt in range(MAX_RETRIES):
            response = await http.request(method, url, headers=headers, **kwargs)
            update_from_response(response)
            last_response = response
            if response.status_code == 404 and treat_404_as_ok:
                return response
            if response.status_code == 429:
                delay = compute_retry_delay(response, attempt)
                logger.warning(
                    "Nexus API 429，第 %s/%s 次重试，等待 %.1f 秒",
                    attempt + 1,
                    MAX_RETRIES,
                    delay,
                )
                if attempt >= MAX_RETRIES - 1:
                    break
                await asyncio.sleep(delay)
                continue
            if response.is_error:
                raise parse_api_error(response)
            return response
        assert last_response is not None
        raise parse_api_error(last_response)
    finally:
        if owns_client:
            await http.aclose()
