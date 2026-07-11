# -*- coding: utf-8 -*-
"""依赖名称补全测试。"""
from __future__ import annotations

from sqlmodel import select

from cyberpunk_mod_manager.models import Mod, ModDependency, ModStatus
from cyberpunk_mod_manager.nexus.dependencies import (
    enrich_dependency_names_sync,
    get_dependency_infos,
    sync_dependencies,
)
from cyberpunk_mod_manager.storage.db import get_session, init_db


def test_enrich_dependency_name_from_inventory() -> None:
    init_db()
    with get_session() as session:
        owner = Mod(
            nexus_mod_id=11937,
            name="Test Owner",
            status=ModStatus.INSTALLED,
        )
        dep = Mod(
            nexus_mod_id=1873,
            name="4k Complexion and Body",
            status=ModStatus.INSTALLED,
        )
        session.add(owner)
        session.add(dep)
        session.commit()
        session.refresh(owner)

    sync_dependencies(
        owner.id,
        [{"mod_id": 1873, "name": "", "source": "parsed"}],
    )
    assert enrich_dependency_names_sync() >= 1

    infos = get_dependency_infos(11937)
    assert len(infos) == 1
    assert infos[0].name == "4k Complexion and Body"

    with get_session() as session:
        owner = session.exec(select(Mod).where(Mod.nexus_mod_id == 11937)).first()
        rec = session.exec(
            select(ModDependency).where(ModDependency.owner_mod_id == owner.id)
        ).first()
        assert rec is not None
        assert rec.dep_name == "4k Complexion and Body"
