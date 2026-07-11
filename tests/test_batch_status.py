# -*- coding: utf-8 -*-
"""批量状态查询测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db


def test_batch_mod_status_info() -> None:
    init_db()
    with get_session() as session:
        session.add(
            Mod(nexus_mod_id=1001, name="Installed", status=ModStatus.INSTALLED)
        )
        session.add(
            Mod(nexus_mod_id=1002, name="Pending", status=ModStatus.DOWNLOADED)
        )
        session.commit()

    result = mod_ops.batch_mod_status_info([1001, 1002, 1999])
    assert result[1001] == (ModStatus.INSTALLED.value, True)
    assert result[1002] == (ModStatus.DOWNLOADED.value, False)
    assert result[1999] == (ModStatus.NOT_INSTALLED.value, False)
