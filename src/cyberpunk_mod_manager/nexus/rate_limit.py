# -*- coding: utf-8 -*-
"""Nexus API 速率限制状态与批量操作节流。"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Nexus v1/v3 响应头（见 Swagger / help.nexusmods.com）
_HEADER_HOURLY_LIMIT = "x-rl-hourly-limit"
_HEADER_HOURLY_REMAINING = "x-rl-hourly-remaining"
_HEADER_HOURLY_RESET = "x-rl-hourly-reset"
_HEADER_DAILY_LIMIT = "x-rl-daily-limit"
_HEADER_DAILY_REMAINING = "x-rl-daily-remaining"
_HEADER_DAILY_RESET = "x-rl-daily-reset"

BATCH_PAUSE_HOURLY_REMAINING = 50
BATCH_PAUSE_DAILY_REMAINING = 500
WARNING_HOURLY_REMAINING = 100
WARNING_DAILY_REMAINING = 1000


@dataclass
class RateLimitSnapshot:
    hourly_limit: int | None = None
    hourly_remaining: int | None = None
    hourly_reset: int | None = None
    daily_limit: int | None = None
    daily_remaining: int | None = None
    daily_reset: int | None = None
    blocked_until: float | None = None
    warning: str = ""
    last_updated: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "hourly_limit": self.hourly_limit,
            "hourly_remaining": self.hourly_remaining,
            "hourly_reset": self.hourly_reset,
            "daily_limit": self.daily_limit,
            "daily_remaining": self.daily_remaining,
            "daily_reset": self.daily_reset,
            "blocked_until": self.blocked_until,
            "warning": self.warning,
            "should_pause_batch": should_pause_batch(self),
            "last_updated": self.last_updated,
        }


_state = RateLimitSnapshot()
_lock = asyncio.Lock()


def _parse_int_header(headers: httpx.Headers, name: str) -> int | None:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def parse_retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("Retry-After")
    if raw is None:
        return None
    text = str(raw).strip()
    if text.isdigit():
        return float(text)
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is not None:
            return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _build_warning(snap: RateLimitSnapshot) -> str:
    if snap.blocked_until and time.time() < snap.blocked_until:
        wait = int(snap.blocked_until - time.time())
        return f"Nexus API 频率超限，约 {wait} 秒后可继续请求"
    parts: list[str] = []
    if snap.hourly_remaining is not None and snap.hourly_remaining <= WARNING_HOURLY_REMAINING:
        parts.append(f"每小时剩余 {snap.hourly_remaining} 次")
    if snap.daily_remaining is not None and snap.daily_remaining <= WARNING_DAILY_REMAINING:
        parts.append(f"每日剩余 {snap.daily_remaining} 次")
    if parts:
        return "Nexus API 配额偏低：" + "，".join(parts)
    return ""


def update_from_response(response: httpx.Response) -> RateLimitSnapshot:
    """从响应头更新全局配额快照。"""
    global _state
    headers = response.headers
    snap = RateLimitSnapshot(
        hourly_limit=_parse_int_header(headers, _HEADER_HOURLY_LIMIT) or _state.hourly_limit,
        hourly_remaining=_parse_int_header(headers, _HEADER_HOURLY_REMAINING),
        hourly_reset=_parse_int_header(headers, _HEADER_HOURLY_RESET) or _state.hourly_reset,
        daily_limit=_parse_int_header(headers, _HEADER_DAILY_LIMIT) or _state.daily_limit,
        daily_remaining=_parse_int_header(headers, _HEADER_DAILY_REMAINING),
        daily_reset=_parse_int_header(headers, _HEADER_DAILY_RESET) or _state.daily_reset,
        blocked_until=_state.blocked_until,
        last_updated=time.time(),
    )
    if response.status_code == 429:
        retry_after = parse_retry_after(response)
        if retry_after is not None:
            snap.blocked_until = time.time() + retry_after
        elif snap.hourly_reset:
            snap.blocked_until = float(snap.hourly_reset)
        else:
            snap.blocked_until = time.time() + 60.0
    elif snap.blocked_until and time.time() >= snap.blocked_until:
        snap.blocked_until = None
    snap.warning = _build_warning(snap)
    _state = snap
    return snap


def get_snapshot() -> RateLimitSnapshot:
    snap = _state
    snap.warning = _build_warning(snap)
    return snap


def should_pause_batch(snap: RateLimitSnapshot | None = None) -> bool:
    s = snap or get_snapshot()
    now = time.time()
    if s.blocked_until and now < s.blocked_until:
        return True
    if s.hourly_remaining is not None and s.hourly_remaining <= BATCH_PAUSE_HOURLY_REMAINING:
        return True
    if s.daily_remaining is not None and s.daily_remaining <= BATCH_PAUSE_DAILY_REMAINING:
        return True
    return False


def seconds_until_available(snap: RateLimitSnapshot | None = None) -> float:
    s = snap or get_snapshot()
    now = time.time()
    candidates: list[float] = []
    if s.blocked_until and s.blocked_until > now:
        candidates.append(s.blocked_until - now)
    if s.hourly_remaining is not None and s.hourly_remaining <= BATCH_PAUSE_HOURLY_REMAINING:
        if s.hourly_reset and s.hourly_reset > now:
            candidates.append(s.hourly_reset - now)
    if s.daily_remaining is not None and s.daily_remaining <= BATCH_PAUSE_DAILY_REMAINING:
        if s.daily_reset and s.daily_reset > now:
            candidates.append(s.daily_reset - now)
    if not candidates:
        return 0.0
    return max(1.0, min(candidates))


async def await_rate_limit_capacity(*, poll_interval: float = 5.0) -> None:
    """批量操作前等待：配额耗尽或接近下限时暂停。"""
    while should_pause_batch():
        wait = seconds_until_available()
        chunk = min(max(wait, 1.0), poll_interval)
        logger.info("Nexus API 配额不足，批量操作暂停 %.0f 秒", chunk)
        await asyncio.sleep(chunk)


def compute_retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = parse_retry_after(response)
    if retry_after is not None:
        return min(retry_after, 120.0)
    return min(2.0 ** attempt, 60.0)
