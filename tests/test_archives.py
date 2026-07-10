# -*- coding: utf-8 -*-
"""压缩包解压测试。"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from cyberpunk_mod_manager.installer.archives import detect_archive_kind, extract_archive


def test_detect_zip(tmp_path: Path) -> None:
    archive = tmp_path / "mod.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("foo.archive", b"x")
    assert detect_archive_kind(archive) == "zip"


def test_extract_7z(tmp_path: Path) -> None:
    py7zr = pytest.importorskip("py7zr")

    src_file = tmp_path / "test.archive"
    src_file.write_bytes(b"data")
    archive = tmp_path / "mod.7z"
    with py7zr.SevenZipFile(archive, "w") as zf:
        zf.write(src_file, "test.archive")

    out = tmp_path / "out"
    kind = extract_archive(archive, out)
    assert kind == "7z"
    assert (out / "test.archive").read_bytes() == b"data"


def test_extract_single_archive_file(tmp_path: Path) -> None:
    archive = tmp_path / "direct.archive"
    archive.write_bytes(b"raw")
    out = tmp_path / "out"
    kind = extract_archive(archive, out)
    assert kind == "single"
    assert (out / "direct.archive").exists()
