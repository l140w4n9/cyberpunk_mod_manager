# -*- coding: utf-8 -*-
"""智能安装计划测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.services.install_plan import (
    merge_plan_mappings,
    mappings_from_inspection,
    needs_llm_plan,
)


def _sample_inspection() -> dict:
    return {
        "entries": [
            {
                "rel": "red4ext/plugins/ArchiveXL/Bundle/Migration.xl",
                "status": "match",
                "target": "archive/pc/mod/Migration.xl",
            },
            {
                "rel": "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
                "status": "skip",
                "target": None,
            },
        ],
        "matched_count": 1,
        "skipped_count": 1,
    }


def test_needs_llm_when_skipped() -> None:
    assert needs_llm_plan(_sample_inspection()) is True


def test_merge_llm_fixes_skipped_paths() -> None:
    inspection = {
        "entries": [
            {
                "rel": "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
                "status": "skip",
                "target": None,
            },
            {
                "rel": "engine/config/platform/pc/input_loader.ini",
                "status": "skip",
                "target": None,
            },
        ],
        "matched_count": 0,
        "skipped_count": 2,
    }
    base = mappings_from_inspection(inspection)
    assert base == {}

    mappings, items = merge_plan_mappings(
        inspection,
        [
            {
                "src": "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
                "target": "red4ext/plugins/ArchiveXL/ArchiveXL.dll",
                "reason": "RED4ext 插件",
            }
        ],
    )
    assert mappings["red4ext/plugins/ArchiveXL/ArchiveXL.dll"].endswith("ArchiveXL.dll")
    assert any(i["source"] == "llm" for i in items)
