# -*- coding: utf-8 -*-
"""Nexus 客户端与安装流程错误处理测试。"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.nexus.client import NexusAPIError
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    init_db()


def _create_mod(nexus_mod_id: int = 27967) -> None:
    with get_session() as session:
        if session.exec(
            select(Mod).where(Mod.nexus_mod_id == nexus_mod_id)
        ).first() is None:
            session.add(Mod(nexus_mod_id=nexus_mod_id, name="0-Engine"))
            session.commit()


@pytest.mark.asyncio
async def test_download_mod_returns_json_error_on_403() -> None:
    _create_mod()
    with patch("cyberpunk_mod_manager.services.mod_ops.NexusClient") as mock_cls:
        client = AsyncMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.get_mods_batch = AsyncMock(return_value={})
        client.resolve_target_version = AsyncMock(
            side_effect=NexusAPIError(
                "Nexus API 403 Forbidden",
                status_code=403,
            )
        )
        mock_cls.return_value = client

        result = await mod_ops.download_mod(27967)
        data = json.loads(result)

    assert "error" in data
    assert "403" in data["error"]


@pytest.mark.asyncio
async def test_install_mod_aborts_when_download_fails_no_local() -> None:
    """下载失败且无本地包时不应使用旧缓存文件继续安装。"""
    _create_mod()
    stale = config.downloads_dir / "stale.zip"
    config.downloads_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(stale, "w") as zf:
        zf.writestr("old.archive", b"stale")

    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 27967)).first()
        mod.local_path = "stale.zip"
        mod.status = ModStatus.DOWNLOADED
        session.add(mod)
        session.commit()

    with patch(
        "cyberpunk_mod_manager.services.mod_ops.download_mod",
        new=AsyncMock(return_value=json.dumps({"error": "HTTP 403 Forbidden"})),
    ):
        with patch(
            "cyberpunk_mod_manager.services.mod_ops.ensure_mod_in_inventory",
            new=AsyncMock(return_value=1),
        ):
            result = await mod_ops.install_mod(
                27967, allow_local_fallback=False
            )

    data = json.loads(result)
    assert "error" in data

    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 27967)).first()
        assert mod.status == ModStatus.DOWNLOADED
        assert mod.status != ModStatus.INSTALLED

    assert not (Path(config.game_path) / "archive/pc/mod/old.archive").exists()


@pytest.mark.asyncio
async def test_install_mod_succeeds_after_download() -> None:
    _create_mod(30001)
    archive = config.downloads_dir / "fresh.zip"
    config.downloads_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("fresh.archive", b"new")

    ok_download = json.dumps(
        {
            "mod_id": 30001,
            "file_id": 1,
            "file_name": "fresh.zip",
            "local_path": str(archive),
        }
    )

    with patch(
        "cyberpunk_mod_manager.services.mod_ops.download_mod",
        new=AsyncMock(return_value=ok_download),
    ):
        with patch(
            "cyberpunk_mod_manager.services.mod_ops.ensure_mod_in_inventory",
            new=AsyncMock(return_value=1),
        ):
            with get_session() as session:
                mod = session.exec(
                    select(Mod).where(Mod.nexus_mod_id == 30001)
                ).first()
                mod.local_path = "fresh.zip"
                session.add(mod)
                session.commit()

            result = await mod_ops.install_mod(30001)

    data = json.loads(result)
    assert "error" not in data
    assert data["added_files_count"] == 1


@pytest.mark.asyncio
async def test_install_mod_uses_local_fallback_for_adult_content(tmp_path: Path) -> None:
    mod_id = 11077
    _create_mod(nexus_mod_id=mod_id)
    config.downloads_dir.mkdir(parents=True, exist_ok=True)
    archive = config.downloads_dir / f"{mod_id}_test.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("demo.archive", b"x")

    adult_error = json.dumps(
        {
            "error": "模组 11077 标记为成人内容，已阻止自动下载",
            "adult_content": True,
            "mod_id": mod_id,
        }
    )
    ok_install = json.dumps(
        {
            "mod_id": mod_id,
            "added_files_count": 1,
            "source": "local",
        }
    )

    with patch(
        "cyberpunk_mod_manager.services.mod_ops.download_mod",
        new=AsyncMock(return_value=adult_error),
    ):
        with patch(
            "cyberpunk_mod_manager.services.mod_ops.ensure_mod_in_inventory",
            new=AsyncMock(return_value=1),
        ):
            with patch(
                "cyberpunk_mod_manager.services.mod_ops.install_from_archive",
                new=AsyncMock(return_value=ok_install),
            ):
                result = await mod_ops.install_mod(mod_id)

    data = json.loads(result)
    assert data.get("used_local_fallback") is True
    assert data.get("adult_content") is True
    assert data.get("added_files_count") == 1

