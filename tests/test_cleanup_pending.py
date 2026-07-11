# -*- coding: utf-8 -*-
"""待安装模组清理测试。"""
from __future__ import annotations

from sqlmodel import select

from cyberpunk_mod_manager.models import Mod, ModDependency, ModStatus
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db


def test_delete_pending_mod_from_inventory() -> None:
    init_db()
    mod_internal_id = 0
    with get_session() as session:
        mod = Mod(nexus_mod_id=9001, name="Pending Mod", status=ModStatus.DOWNLOADED)
        session.add(mod)
        session.commit()
        session.refresh(mod)
        mod_internal_id = mod.id
        session.add(
            ModDependency(
                owner_mod_id=mod_internal_id,
                dep_nexus_mod_id=107,
                dep_name="CET",
            )
        )
        session.commit()

    result = mod_ops.delete_mod_from_inventory(9001)
    assert result.get("deleted") == 9001

    with get_session() as session:
        assert session.exec(select(Mod).where(Mod.nexus_mod_id == 9001)).first() is None
        assert (
            session.exec(
                select(ModDependency).where(ModDependency.owner_mod_id == mod_internal_id)
            ).first()
            is None
        )


def test_cannot_delete_installed_mod() -> None:
    init_db()
    with get_session() as session:
        session.add(
            Mod(nexus_mod_id=9002, name="Installed", status=ModStatus.INSTALLED)
        )
        session.commit()

    result = mod_ops.delete_mod_from_inventory(9002)
    assert result.get("error")


def test_cleanup_pending_mods_batch() -> None:
    init_db()
    with get_session() as session:
        session.add(Mod(nexus_mod_id=9010, name="A", status=ModStatus.NOT_INSTALLED))
        session.add(Mod(nexus_mod_id=9011, name="B", status=ModStatus.DOWNLOADED))
        session.add(Mod(nexus_mod_id=9012, name="C", status=ModStatus.INSTALLED))
        session.commit()

    result = mod_ops.cleanup_pending_mods([9010, 9011])
    assert result["deleted_count"] == 2
    assert result["failed_count"] == 0

    with get_session() as session:
        ids = {m.nexus_mod_id for m in session.exec(select(Mod)).all()}
        assert 9010 not in ids
        assert 9011 not in ids
        assert 9012 in ids
