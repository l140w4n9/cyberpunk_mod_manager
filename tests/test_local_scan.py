# -*- coding: utf-8 -*-
"""本地文件夹扫描测试。"""
from __future__ import annotations

from pathlib import Path

from cyberpunk_mod_manager.services.local_scan import (
    parse_mod_id_from_filename,
    scan_folder,
)


def test_parse_nexus_cdn_filename() -> None:
    assert parse_mod_id_from_filename("Avabetterskins-11937-1-0-1703958711.7z") == 11937
    assert parse_mod_id_from_filename("Alternative Skin Material-7341-1-0-1675607841.rar") == 7341
    assert parse_mod_id_from_filename("3D World Map Fixed-26500-1-4-0-1778370358.zip") == 26500


def test_parse_space_separated_id() -> None:
    assert parse_mod_id_from_filename(
        "0-Engine Pure CET 27967 0.18.6 2026-06-29T14-25Z sHlUHDmw2.zip"
    ) == 27967


def test_scan_folder_detects_multiple(tmp_path: Path) -> None:
    folder = tmp_path / "batch"
    folder.mkdir()
    (folder / "Core File-23032-1-0-1753747571.zip").write_bytes(b"pk")
    (folder / "Avabetterskins-11937-1-0-1703958711.7z").write_bytes(b"7z")
    (folder / "readme.txt").write_text("x")

    result = scan_folder(folder)
    ids = {item["mod_id"] for item in result["detected"]}
    assert ids == {23032, 11937}
    assert result["unknown_count"] == 0
