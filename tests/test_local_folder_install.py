# -*- coding: utf-8 -*-
"""文件夹安装安全策略测试。"""
from __future__ import annotations

import json

import pytest

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.services.local_scan import scan_folder
from cyberpunk_mod_manager.storage.db import get_session, init_db


@pytest.mark.asyncio
async def test_blocks_bulk_install_on_downloads_dir(tmp_path) -> None:
    init_db()
    downloads = config.downloads_dir
    downloads.mkdir(parents=True, exist_ok=True)
    archive = downloads / "Core File-23032-1-0-1753747571.zip"
    archive.write_bytes(b"pk")

    result = await mod_ops.install_local_folder(".")
    data = json.loads(result)
    assert "error" in data
    assert "downloads" in data["error"]


@pytest.mark.asyncio
async def test_skip_already_installed_mod(tmp_path) -> None:
    init_db()
    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "Core File-23032-1-0-1753747571.zip").write_bytes(b"pk")

    mod_ops.get_or_create_mod_stub(23032, "Core File")
    with get_session() as session:
        from sqlmodel import select

        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 23032)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    result = await mod_ops.install_local_folder(str(folder))
    data = json.loads(result)
    assert data.get("skipped") and data["skipped"][0]["mod_id"] == 23032
    assert data["succeeded"] == []
    assert data.get("message")


def test_scan_includes_install_status(tmp_path) -> None:
    init_db()
    folder = tmp_path / "batch2"
    folder.mkdir()
    (folder / "Core File-26500-1-0-1753747571.zip").write_bytes(b"pk")

    mod_ops.get_or_create_mod_stub(26500, "Test Mod")
    with get_session() as session:
        from sqlmodel import select

        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 26500)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    raw = mod_ops.scan_local_folder(str(folder))
    data = json.loads(raw)
    assert data["detected"][0]["installed"] is True
    assert data["installed_count"] == 1
    assert data["pending_count"] == 0
