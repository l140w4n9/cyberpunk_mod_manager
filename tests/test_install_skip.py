# -*- coding: utf-8 -*-
"""单个安装跳过已装模组测试。"""
from __future__ import annotations

import json

import pytest

from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.mark.asyncio
async def test_install_mod_skips_already_installed() -> None:
    init_db()
    mod_ops.get_or_create_mod_stub(88001, "Installed Mod")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 88001)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    result = await mod_ops.install_mod(88001, skip_installed=True)
    data = json.loads(result)
    assert data.get("skipped") is True
    assert data.get("reason") == "already_installed"
    assert "88001" in data.get("message", "")
    assert "error" not in data


@pytest.mark.asyncio
async def test_install_mod_with_deps_skips_main_when_installed() -> None:
    init_db()
    mod_ops.get_or_create_mod_stub(88002, "Main Mod")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 88002)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    result = await mod_ops.install_mod_with_dependencies(
        88002,
        install_dependencies=True,
        skip_installed=True,
    )
    data = json.loads(result)
    assert data.get("skipped") is True
    assert data.get("reason") == "already_installed"
    assert "error" not in data


@pytest.mark.asyncio
async def test_install_mod_force_reinstall_flag_disables_skip() -> None:
    """skip_installed=False 时不应提前跳过（后续可能因无压缩包失败）。"""
    init_db()
    mod_ops.get_or_create_mod_stub(88003, "Force Mod")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 88003)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    result = await mod_ops.install_mod(88003, skip_installed=False, local_only=True)
    data = json.loads(result)
    assert data.get("skipped") is not True
