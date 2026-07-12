# -*- coding: utf-8 -*-
"""安装后验收测试。"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.installer.engine import Installer
from cyberpunk_mod_manager.installer.verify import verify_installed_files
from cyberpunk_mod_manager.models import Mod
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    init_db()
    from cyberpunk_mod_manager.installer.profile import reload_install_profile

    reload_install_profile()


def _create_mod(nexus_mod_id: int = 107) -> int:
    with get_session() as session:
        existing = session.exec(
            select(Mod).where(Mod.nexus_mod_id == nexus_mod_id)
        ).first()
        if existing is not None:
            return existing.id
        mod = Mod(nexus_mod_id=nexus_mod_id, name="CET", version="1.37.1")
        session.add(mod)
        session.commit()
        session.refresh(mod)
        return mod.id


def test_verify_cet_framework_files(tmp_path: Path) -> None:
    mod_id = _create_mod()
    archive = tmp_path / "cet.zip"
    files = {
        "bin/x64/version.dll": b"dll",
        "bin/x64/global.ini": b"ini",
        "bin/x64/plugins/cyber_engine_tweaks.asi": b"asi",
    }
    with zipfile.ZipFile(archive, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)

    installer = Installer()
    installer.install(mod_id, archive)

    report = verify_installed_files(internal_mod_id=mod_id, nexus_mod_id=107)
    assert report["ok"] is True
    assert "Cyber Engine Tweaks" in report["checks_run"]


def test_verify_detects_missing_framework_file(tmp_path: Path) -> None:
    mod_id = _create_mod()
    for rel in ("bin/x64/version.dll", "bin/x64/global.ini"):
        path = Path(config.game_path) / rel
        if path.is_file():
            path.unlink()
    archive = tmp_path / "partial.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("bin/x64/plugins/cyber_engine_tweaks.asi", b"asi")

    installer = Installer()
    installer.install(mod_id, archive)

    report = verify_installed_files(internal_mod_id=mod_id, nexus_mod_id=107)
    assert report["ok"] is False
    assert report["missing_required"]
