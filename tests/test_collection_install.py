# -*- coding: utf-8 -*-
"""收藏夹队列与安装任务测试。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.nexus.collections import CollectionInfo, CollectionModEntry
from cyberpunk_mod_manager.services import collection_ops
from cyberpunk_mod_manager.services.collection_ops import QueueItemStatus
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


def _sample_collection() -> CollectionInfo:
    return CollectionInfo(
        title="Test Collection",
        slug="iszwwe",
        domain="cyberpunk2077",
        revision_number=1,
        mod_count=4,
        url="https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods",
        mods=[
            CollectionModEntry(mod_id=100, name="Required A", order=1, optional=False),
            CollectionModEntry(mod_id=200, name="Optional B", order=2, optional=True),
            CollectionModEntry(mod_id=300, name="Required C", order=3, optional=False),
        ],
    )


@pytest.mark.asyncio
async def test_parse_collection_queue_optional_unselected() -> None:
    init_db()
    with patch(
        "cyberpunk_mod_manager.services.collection_ops.fetch_collection",
        new=AsyncMock(return_value=_sample_collection()),
    ):
        data = await collection_ops.parse_collection_url_to_queue(
            "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
        )

    assert data["collection"]["title"] == "Test Collection"
    assert data["stats"]["total"] == 3
    queue = {item["mod_id"]: item for item in data["queue"]}
    assert queue[100]["selected"] is True
    assert queue[200]["selected"] is False
    assert queue[200]["optional"] is True
    assert queue[300]["selected"] is True


@pytest.mark.asyncio
async def test_collection_install_job_continues_after_failure() -> None:
    init_db()
    from cyberpunk_mod_manager.services import mod_ops

    async def fake_install(mod_id: int, **kwargs):
        if mod_id == 200:
            return json.dumps({"error": "download failed", "mod_id": mod_id})
        if mod_id == 300:
            return json.dumps({"mod_id": mod_id, "name": "C", "added_files_count": 1})
        return json.dumps({"mod_id": mod_id, "skipped": True, "message": "skip"})

    with patch(
        "cyberpunk_mod_manager.services.collection_ops.asyncio.create_task"
    ), patch.object(
        mod_ops,
        "install_mod_with_dependencies",
        new=AsyncMock(side_effect=fake_install),
    ):
        job_id = await collection_ops.start_collection_install(
            slug="iszwwe",
            domain="cyberpunk2077",
            title="Test Collection",
            mod_ids=[100, 200, 300],
        )
        # 测试中直接执行队列，避免后台 task 竞态
        collection_ops._jobs[job_id].state = "pending"
        await collection_ops._run_job(
            job_id, install_dependencies=True, skip_installed=True
        )

    job = collection_ops.get_job(job_id)
    assert job is not None
    assert job.state == "done"
    by_id = {item.mod_id: item for item in job.items}
    assert by_id[100].status == QueueItemStatus.SKIPPED.value
    assert by_id[200].status == QueueItemStatus.FAILED.value
    assert by_id[300].status == QueueItemStatus.SUCCESS.value


@pytest.mark.asyncio
async def test_collection_install_skips_installed_without_api_call() -> None:
    """已安装模组应在任务启动时直接标记跳过，不调用安装接口。"""
    init_db()
    from cyberpunk_mod_manager.services import mod_ops

    mod_ops.get_or_create_mod_stub(100, "Installed A")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 100)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    install_mock = AsyncMock(
        return_value=json.dumps({"mod_id": 300, "added_files_count": 1})
    )
    with patch(
        "cyberpunk_mod_manager.services.collection_ops.asyncio.create_task"
    ), patch.object(mod_ops, "install_mod_with_dependencies", new=install_mock):
        job_id = await collection_ops.start_collection_install(
            slug="iszwwe",
            domain="cyberpunk2077",
            title="Test Collection",
            mod_ids=[100, 300],
        )
        collection_ops._jobs[job_id].state = "pending"
        await collection_ops._run_job(
            job_id, install_dependencies=True, skip_installed=True
        )

    job = collection_ops.get_job(job_id)
    by_id = {item.mod_id: item for item in job.items}
    assert by_id[100].status == QueueItemStatus.SKIPPED.value
    assert by_id[100].installed is True
    assert by_id[300].status == QueueItemStatus.SUCCESS.value
    install_mock.assert_awaited_once()
    install_mock.assert_awaited_with(
        300,
        install_dependencies=True,
        allow_local_fallback=True,
        skip_installed=True,
        pin=None,
    )


@pytest.mark.asyncio
async def test_parse_marks_installed_mods() -> None:
    init_db()
    from cyberpunk_mod_manager.services import mod_ops

    mod_ops.get_or_create_mod_stub(100, "Installed")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 100)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    with patch(
        "cyberpunk_mod_manager.services.collection_ops.fetch_collection",
        new=AsyncMock(return_value=_sample_collection()),
    ):
        data = await collection_ops.parse_collection_url_to_queue(
            "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
        )

    first = next(item for item in data["queue"] if item["mod_id"] == 100)
    assert first["installed"] is True
    assert first["selected"] is False
    assert first["status"] == QueueItemStatus.SKIPPED.value
    assert "跳过" in first["message"]
    assert data["stats"]["pending"] == 1
