# -*- coding: utf-8 -*-
"""异步任务并发控制。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_CONCURRENCY = 6


async def gather_bounded(
    coroutines: list[Awaitable[T]],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_complete: Callable[[int, int, T], None] | None = None,
) -> list[T]:
    """以有限并发执行协程，保持结果顺序与输入一致。"""
    if not coroutines:
        return []

    total = len(coroutines)
    sem = asyncio.Semaphore(max(1, concurrency))
    results: list[T | None] = [None] * total
    done_count = 0
    lock = asyncio.Lock()

    async def run_at(index: int, coro: Awaitable[T]) -> None:
        nonlocal done_count
        async with sem:
            value = await coro
        results[index] = value
        async with lock:
            done_count += 1
            if on_complete is not None:
                on_complete(done_count, total, value)

    await asyncio.gather(*(run_at(index, coro) for index, coro in enumerate(coroutines)))
    return results  # type: ignore[return-value]
