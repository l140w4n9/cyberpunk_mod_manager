# -*- coding: utf-8 -*-
"""Nexus API 速率限制解析与批量暂停逻辑。"""
from __future__ import annotations

import time

import httpx

from cyberpunk_mod_manager.nexus.rate_limit import (
    RateLimitSnapshot,
    compute_retry_delay,
    get_snapshot,
    parse_retry_after,
    should_pause_batch,
    update_from_response,
)


def _response(
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return httpx.Response(status, headers=headers or {}, request=httpx.Request("GET", "https://example.com"))


def test_parse_retry_after_seconds():
    response = _response(429, {"Retry-After": "30"})
    assert parse_retry_after(response) == 30.0


def test_update_from_response_quota_headers():
    snap = update_from_response(
        _response(
            200,
            {
                "X-RL-Hourly-Limit": "1000",
                "X-RL-Hourly-Remaining": "42",
                "X-RL-Daily-Limit": "10000",
                "X-RL-Daily-Remaining": "9000",
            },
        )
    )
    assert snap.hourly_limit == 1000
    assert snap.hourly_remaining == 42
    assert snap.daily_remaining == 9000
    assert "每小时剩余 42 次" in snap.warning


def test_should_pause_batch_when_hourly_low():
    snap = RateLimitSnapshot(hourly_remaining=10, daily_remaining=9000)
    assert should_pause_batch(snap) is True


def test_should_pause_batch_when_blocked():
    snap = RateLimitSnapshot(blocked_until=time.time() + 60)
    assert should_pause_batch(snap) is True


def test_compute_retry_delay_exponential():
    response = _response(429)
    assert compute_retry_delay(response, 0) == 1.0
    assert compute_retry_delay(response, 3) == 8.0


def test_get_snapshot_reflects_last_update():
    update_from_response(_response(200, {"X-RL-Hourly-Remaining": "500"}))
    snap = get_snapshot()
    assert snap.hourly_remaining == 500
