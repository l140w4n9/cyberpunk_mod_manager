# -*- coding: utf-8 -*-
"""安装/卸载引擎集成测试。"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.installer import get_uninstall_plan
from cyberpunk_mod_manager.installer.engine import Installer
from cyberpunk_mod_manager.models import Mod, ModStatus
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


@pytest.fixture(autouse=True)
def _fresh_db() -> None:
    init_db()


def _create_mod(nexus_mod_id: int = 12345) -> int:
    with get_session() as session:
        existing = session.exec(
            select(Mod).where(Mod.nexus_mod_id == nexus_mod_id)
        ).first()
        if existing is not None:
            return existing.id
        mod = Mod(nexus_mod_id=nexus_mod_id, name="Test Mod", version="1.0")
        session.add(mod)
        session.commit()
        session.refresh(mod)
        return mod.id


def test_install_and_uninstall_flat_archive(tmp_path: Path) -> None:
    mod_id = _create_mod()
    archive = tmp_path / "test_mod.zip"
    _make_zip(archive, {"foo.archive": b"fake archive"})

    installer = Installer()
    result = installer.install(mod_id, archive)

    target = Path(config.game_path) / "archive/pc/mod/foo.archive"
    assert target.exists()
    assert "archive/pc/mod/foo.archive" in result.added_files

    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.id == mod_id)).first()
        assert mod.status == ModStatus.INSTALLED
        assert mod.installed_at is not None

    plan = get_uninstall_plan(mod_id)
    assert plan is not None
    assert "archive/pc/mod/foo.archive" in plan.added_files

    installer.uninstall(mod_id)
    assert not target.exists()

    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.id == mod_id)).first()
        assert mod.status == ModStatus.NOT_INSTALLED
        assert mod.installed_at is None


def test_install_preserves_nested_structure(tmp_path: Path) -> None:
    mod_id = _create_mod(nexus_mod_id=99999)
    archive = tmp_path / "structured.zip"
    rel = "bin/x64/plugins/cyber_engine_tweaks/mods/mymod/init.lua"
    _make_zip(archive, {rel: b"print('hello')"})

    installer = Installer()
    result = installer.install(mod_id, archive)

    target = Path(config.game_path) / rel
    assert target.exists()
    assert rel in result.added_files


def test_reinstall_replaces_install_record(tmp_path: Path) -> None:
    mod_id = _create_mod(nexus_mod_id=88888)
    archive1 = tmp_path / "v1.zip"
    archive2 = tmp_path / "v2.zip"
    _make_zip(archive1, {"a.archive": b"v1"})
    _make_zip(archive2, {"b.archive": b"v2"})

    installer = Installer()
    installer.install(mod_id, archive1)
    installer.uninstall(mod_id)
    installer.install(mod_id, archive2)

    plan = get_uninstall_plan(mod_id)
    assert plan is not None
    assert "archive/pc/mod/b.archive" in plan.added_files
    assert "archive/pc/mod/a.archive" not in plan.added_files


def test_install_preserves_red4ext_plugin_structure(tmp_path: Path) -> None:
    mod_id = _create_mod(nexus_mod_id=4198)
    archive = tmp_path / "archivexl.zip"
    dll = "red4ext/plugins/ArchiveXL/ArchiveXL.dll"
    xl = "red4ext/plugins/ArchiveXL/Bundle/Migration.xl"
    _make_zip(archive, {dll: b"dll", xl: b"xl"})

    installer = Installer()
    result = installer.install(mod_id, archive)

    assert dll in result.added_files
    assert xl in result.added_files
    assert (Path(config.game_path) / dll).exists()
    assert (Path(config.game_path) / xl).exists()


def test_install_fails_when_no_rules_match(tmp_path: Path) -> None:
    mod_id = _create_mod(nexus_mod_id=55555)
    archive = tmp_path / "readme_only.zip"
    _make_zip(archive, {"readme.txt": b"no rules"})

    installer = Installer()
    with pytest.raises(ValueError, match="没有可安装的文件"):
        installer.install(mod_id, archive)

    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.id == mod_id)).first()
        assert mod.status != ModStatus.INSTALLED


def test_backup_and_restore_on_overwrite(tmp_path: Path) -> None:
    mod_id = _create_mod(nexus_mod_id=77777)
    game_file = Path(config.game_path) / "archive/pc/mod/existing.archive"
    game_file.parent.mkdir(parents=True, exist_ok=True)
    game_file.write_bytes(b"original")

    archive = tmp_path / "overwrite.zip"
    _make_zip(archive, {"existing.archive": b"replaced"})

    installer = Installer()
    installer.install(mod_id, archive)

    assert game_file.read_bytes() == b"replaced"
    plan = get_uninstall_plan(mod_id)
    assert plan is not None
    assert len(plan.backed_up_files) == 1

    installer.uninstall(mod_id)
    assert game_file.read_bytes() == b"original"
