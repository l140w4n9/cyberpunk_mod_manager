# -*- coding: utf-8 -*-
"""压缩包结构检查测试。"""
from __future__ import annotations

import zipfile
from pathlib import Path

from cyberpunk_mod_manager.installer.inspect import inspect_archive, list_archive_entries


def _make_zip(path: Path, files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)


def test_list_and_inspect_red4ext_structure(tmp_path: Path) -> None:
    archive = tmp_path / "archivexl.zip"
    _make_zip(
        archive,
        {
            "red4ext/plugins/ArchiveXL/ArchiveXL.dll": b"dll",
            "red4ext/plugins/ArchiveXL/Bundle/Migration.xl": b"xl",
            "README.txt": b"install to red4ext/plugins/ArchiveXL",
        },
    )
    entries = list_archive_entries(archive)
    assert "red4ext/plugins/ArchiveXL/ArchiveXL.dll" in entries

    report = inspect_archive(archive)
    assert report["entry_count"] == 3
    assert report["matched_count"] == 2
    dll_entry = next(e for e in report["entries"] if e["rel"].endswith("ArchiveXL.dll"))
    assert dll_entry["status"] == "match"
    assert dll_entry["target"] == "red4ext/plugins/ArchiveXL/ArchiveXL.dll"
