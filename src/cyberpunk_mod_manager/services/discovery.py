# -*- coding: utf-8 -*-
"""Nexus 模组发现与同步（trending / tracked / updated feed）。"""
from __future__ import annotations

import json
from typing import Any

from sqlmodel import select

from ..models import Mod, ModStatus
from ..nexus.client import NexusClient, parse_mod_id_from_url
from ..storage.db import get_session
from . import mod_ops
from .concurrency import DEFAULT_CONCURRENCY, gather_bounded
from ..nexus.schemas import ModDetails


async def fetch_trending_mods() -> list[dict[str, Any]]:
    async with NexusClient() as client:
        items = await client.get_trending_mods()
    return [item.model_dump() for item in items if item.mod_id]


async def fetch_updated_feed(*, period: str = "1w") -> list[dict[str, Any]]:
    async with NexusClient() as client:
        rows = await client.get_updated_mod_feed(period=period)
    return [
        {
            "mod_id": int(row.get("mod_id") or 0),
            "latest_file_update": row.get("latest_file_update"),
            "latest_mod_activity": row.get("latest_mod_activity"),
        }
        for row in rows
        if row.get("mod_id")
    ]


async def sync_tracked_mods_to_inventory() -> dict[str, Any]:
    async with NexusClient() as client:
        tracked_ids = await client.get_tracked_mod_ids()
    if not tracked_ids:
        return {"synced": 0, "tracked_count": 0, "mod_ids": []}

    async def register(mod_id: int) -> None:
        try:
            async with NexusClient() as client:
                details = await client.get_mod_details(mod_id)
            await mod_ops.ensure_mod_in_inventory(mod_id, details)
        except Exception:
            return

    await gather_bounded(
        [register(mid) for mid in tracked_ids],
        concurrency=DEFAULT_CONCURRENCY,
    )
    return {
        "synced": len(tracked_ids),
        "tracked_count": len(tracked_ids),
        "mod_ids": tracked_ids,
    }


async def batch_mod_availability(mod_ids: list[int]) -> list[dict[str, Any]]:
    if not mod_ids:
        return []
    async with NexusClient() as client:
        batch = await client.get_mods_batch(mod_ids)
    rows: list[dict[str, Any]] = []
    for mid in mod_ids:
        info = batch.get(mid)
        if info is None:
            rows.append(
                {
                    "mod_id": mid,
                    "found": False,
                    "status": "unknown",
                    "adult_content": False,
                }
            )
        else:
            rows.append(
                {
                    "mod_id": mid,
                    "found": True,
                    "name": info.name,
                    "status": info.status,
                    "adult_content": info.adult_content,
                    "summary": info.summary,
                }
            )
    return rows


def compare_local_with_updated_feed(feed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feed_ids = {int(row["mod_id"]) for row in feed if row.get("mod_id")}
    with get_session() as session:
        mods = session.exec(select(Mod)).all()
    hits: list[dict[str, Any]] = []
    for mod in mods:
        if mod.nexus_mod_id not in feed_ids:
            continue
        row = next(
            (r for r in feed if int(r.get("mod_id") or 0) == mod.nexus_mod_id),
            None,
        )
        if row is None:
            continue
        hits.append(
            {
                "mod_id": mod.nexus_mod_id,
                "name": mod.name,
                "local_status": (
                    mod.status.value
                    if hasattr(mod.status, "value")
                    else str(mod.status)
                ),
                "latest_file_update": row.get("latest_file_update"),
                "latest_mod_activity": row.get("latest_mod_activity"),
            }
        )
    return hits
