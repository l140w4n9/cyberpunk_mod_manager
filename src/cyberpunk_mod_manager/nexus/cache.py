# -*- coding: utf-8 -*-
"""Nexus API 响应 TTL 内存缓存。"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

# 秒
TTL_MOD_DETAILS = 3600
TTL_MOD_FILES = 1800
TTL_DEPENDENCIES = 3600
TTL_COLLECTION_REVISION = 300
TTL_USER_PROFILE = 600
TTL_UPDATED_MODS = 300
TTL_MODS_BATCH = 1800
TTL_GAME_ID = 86400


@dataclass
class _Entry:
    value: Any
    expires_at: float


_store: dict[str, _Entry] = {}
_lock = asyncio.Lock()


def _purge_expired(now: float | None = None) -> None:
    ts = now if now is not None else time.time()
    expired = [key for key, entry in _store.items() if entry.expires_at <= ts]
    for key in expired:
        _store.pop(key, None)


def make_key(category: str, *parts: Any) -> str:
    return category + ":" + ":".join(str(p) for p in parts)


async def get_cached(key: str) -> Any | None:
    async with _lock:
        _purge_expired()
        entry = _store.get(key)
        if entry is None:
            return None
        return entry.value


async def set_cached(key: str, value: Any, ttl_seconds: float) -> None:
    async with _lock:
        _store[key] = _Entry(value=value, expires_at=time.time() + ttl_seconds)


async def get_or_fetch(
    key: str,
    ttl_seconds: float,
    factory: Callable[[], Awaitable[T]],
) -> T:
    cached = await get_cached(key)
    if cached is not None:
        return cached  # type: ignore[return-value]
    value = await factory()
    await set_cached(key, value, ttl_seconds)
    return value


def clear_cache() -> None:
    _store.clear()
