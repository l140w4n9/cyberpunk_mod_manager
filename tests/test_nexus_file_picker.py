# -*- coding: utf-8 -*-
"""Nexus 文件选择逻辑测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.nexus.client import select_download_file
from cyberpunk_mod_manager.nexus.schemas import ModFile


def test_prefers_main_over_archived_old_file() -> None:
    """模拟 mod 870：旧版归档在前，MAIN 在后。"""
    files = [
        ModFile(
            file_id=2447,
            file_name="old-v0.1.zip",
            category_id=6,
            category_name=None,
            uploaded_timestamp=1610371435,
        ),
        ModFile(
            file_id=9827,
            file_name="new-v0.2.zip",
            category_id=1,
            category_name="MAIN",
            uploaded_timestamp=1617042952,
        ),
    ]
    picked = select_download_file(files)
    assert picked is not None
    assert picked.file_id == 9827


def test_prefers_is_primary_flag() -> None:
    files = [
        ModFile(file_id=1, category_name="MAIN", uploaded_timestamp=100),
        ModFile(file_id=2, is_primary=True, uploaded_timestamp=50),
    ]
    picked = select_download_file(files)
    assert picked.file_id == 2


def test_picks_newest_when_only_archived() -> None:
    files = [
        ModFile(file_id=10, uploaded_timestamp=100),
        ModFile(file_id=20, uploaded_timestamp=200),
    ]
    picked = select_download_file(files)
    assert picked.file_id == 20
