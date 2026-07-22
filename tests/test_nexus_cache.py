# -*- coding: utf-8 -*-
"""Nexus TTL 内存缓存。"""
from __future__ import annotations

import asyncio

import pytest

from cyberpunk_mod_manager.nexus import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear_cache()
    yield
    cache.clear_cache()


@pytest.mark.asyncio
async def test_get_or_fetch_caches_value():
    calls = 0

    async def factory() -> str:
        nonlocal calls
        calls += 1
        return "payload"

    first = await cache.get_or_fetch("key", 60, factory)
    second = await cache.get_or_fetch("key", 60, factory)
    assert first == second == "payload"
    assert calls == 1


@pytest.mark.asyncio
async def test_cache_expires(monkeypatch):
    now = [1000.0]

    monkeypatch.setattr(cache.time, "time", lambda: now[0])

    async def factory() -> int:
        return 1

    await cache.get_or_fetch("exp", 10, factory)
    now[0] = 1011.0
    calls = 0

    async def factory2() -> int:
        nonlocal calls
        calls += 1
        return 2

    value = await cache.get_or_fetch("exp", 10, factory2)
    assert value == 2
    assert calls == 1
