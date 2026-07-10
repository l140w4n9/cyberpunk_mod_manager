# -*- coding: utf-8 -*-
"""库存 upsert 并发安全测试。"""
from __future__ import annotations

import asyncio

import pytest

from cyberpunk_mod_manager.models import Mod
from cyberpunk_mod_manager.nexus.schemas import ModDetails
from cyberpunk_mod_manager.services.mod_ops import upsert_mod_from_details
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.fixture(autouse=True)
def _db() -> None:
    init_db()


def _details(mod_id: int = 26500) -> ModDetails:
    return ModDetails(
        mod_id=mod_id,
        name="3D World Map Fixed",
        summary="map fix",
        description="",
        author="author",
        version="1.4.0",
        picture_url="",
        mod_page_url="https://example.com",
    )


def test_upsert_mod_is_idempotent() -> None:
    details = _details()
    id1 = upsert_mod_from_details(26500, details)
    id2 = upsert_mod_from_details(26500, details)
    assert id1 == id2

    with get_session() as session:
        count = len(session.exec(select(Mod)).all())
    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_upsert_no_integrity_error() -> None:
    details = _details(26501)

    async def _once() -> int:
        return await asyncio.to_thread(upsert_mod_from_details, 26501, details)

    results = await asyncio.gather(*[_once() for _ in range(8)])
    assert len(set(results)) == 1

    with get_session() as session:
        mods = session.exec(select(Mod).where(Mod.nexus_mod_id == 26501)).all()
    assert len(mods) == 1
