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
async def test_install_mod_with_deps_skips_main_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_db()
    mod_ops.get_or_create_mod_stub(88002, "Main Mod")
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == 88002)).first()
        mod.status = ModStatus.INSTALLED
        session.add(mod)
        session.commit()

    async def noop_refresh(_mod_id: int) -> list[dict]:
        return []

    monkeypatch.setattr(mod_ops, "refresh_dependencies", noop_refresh)

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
async def test_install_mod_with_deps_repairs_missing_deps_when_main_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已安装主模组但缺依赖时，应补装依赖而非直接跳过。"""
    from cyberpunk_mod_manager.models import ModDependency

    init_db()
    main_id = mod_ops.get_or_create_mod_stub(88004, "Main With Deps")
    dep_id = mod_ops.get_or_create_mod_stub(88005, "Missing Dep")
    with get_session() as session:
        main = session.exec(select(Mod).where(Mod.nexus_mod_id == 88004)).first()
        dep = session.exec(select(Mod).where(Mod.nexus_mod_id == 88005)).first()
        main.status = ModStatus.INSTALLED
        dep.status = ModStatus.NOT_INSTALLED
        session.add(
            ModDependency(
                owner_mod_id=main.id,
                dep_nexus_mod_id=88005,
                dep_name="Missing Dep",
                source="nexus",
            )
        )
        session.add(main)
        session.add(dep)
        session.commit()

    async def fake_install_mod(
        mod_id: int,
        *,
        allow_local_fallback: bool = True,
        skip_download: bool = False,
        local_only: bool = False,
        skip_installed: bool = True,
        pin=None,
    ) -> str:
        if mod_id == 88005:
            return json.dumps(
                {
                    "mod_id": 88005,
                    "name": "Missing Dep",
                    "added_files_count": 2,
                    "skipped": False,
                }
            )
        return await mod_ops.install_mod(
            mod_id,
            allow_local_fallback=allow_local_fallback,
            local_only=local_only,
            skip_installed=skip_installed,
            pin=pin,
        )

    monkeypatch.setattr(mod_ops, "install_mod", fake_install_mod)

    async def noop_refresh(_mod_id: int) -> list[dict]:
        return []

    monkeypatch.setattr(mod_ops, "refresh_dependencies", noop_refresh)

    result = await mod_ops.install_mod_with_dependencies(
        88004,
        install_dependencies=True,
        skip_installed=True,
    )
    data = json.loads(result)
    assert data.get("reason") == "deps_repair"
    assert data.get("added_files_count") == 2
    assert len(data.get("dependencies_installed") or []) == 1
    assert "已补装" in data.get("message", "")


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
