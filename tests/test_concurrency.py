# -*- coding: utf-8 -*-
"""并发工具测试。"""
from __future__ import annotations

import asyncio
import time

import pytest

from cyberpunk_mod_manager.services.concurrency import DEFAULT_CONCURRENCY, gather_bounded


@pytest.mark.asyncio
async def test_gather_bounded_limits_concurrency() -> None:
    active = 0
    peak = 0
    lock = asyncio.Lock()

    async def task(delay: float) -> float:
        nonlocal active, peak
        async with lock:
            active += 1
            peak = max(peak, active)
        await asyncio.sleep(delay)
        async with lock:
            active -= 1
        return delay

    started = time.perf_counter()
    results = await gather_bounded(
        [task(0.05) for _ in range(12)],
        concurrency=6,
    )
    elapsed = time.perf_counter() - started

    assert results == [0.05] * 12
    assert peak <= 6
    assert elapsed < 0.25


def test_default_concurrency_is_six() -> None:
    assert DEFAULT_CONCURRENCY == 6
