# -*- coding: utf-8 -*-
"""LLM 主导安装计划测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cyberpunk_mod_manager.services.install_plan import (
    apply_llm_file_mappings,
    build_install_plan,
    effective_install_plan_mode,
    merge_plan_mappings,
)


def _cet_inspection() -> dict:
    entries = [
        {
            "rel": "cet_1.37.1/bin/x64/version.dll",
            "normalized_rel": "bin/x64/version.dll",
            "status": "skip",
            "target": None,
        },
        {
            "rel": "cet_1.37.1/bin/x64/global.ini",
            "normalized_rel": "bin/x64/global.ini",
            "status": "skip",
            "target": None,
        },
        {
            "rel": "cet_1.37.1/bin/x64/plugins/cyber_engine_tweaks.asi",
            "normalized_rel": "bin/x64/plugins/cyber_engine_tweaks.asi",
            "status": "match",
            "target": "bin/x64/plugins/cyber_engine_tweaks.asi",
        },
    ]
    return {
        "entries": entries,
        "entry_count": len(entries),
        "matched_count": 1,
        "skipped_count": 2,
        "wrapper_strip_depth": 1,
        "tree_preview": "version.dll\nglobal.ini",
        "readme_excerpts": [],
    }


def test_apply_llm_mappings_uses_raw_src_paths() -> None:
    inspection = _cet_inspection()
    llm_files = [
        {
            "src": "cet_1.37.1/bin/x64/version.dll",
            "target": "bin/x64/version.dll",
            "reason": "CET 加载器",
        },
        {
            "src": "cet_1.37.1/bin/x64/global.ini",
            "target": "bin/x64/global.ini",
            "reason": "CET 配置",
        },
    ]
    mappings, items = apply_llm_file_mappings(inspection, llm_files)
    assert mappings["cet_1.37.1/bin/x64/version.dll"] == "bin/x64/version.dll"
    assert mappings["cet_1.37.1/bin/x64/global.ini"] == "bin/x64/global.ini"
    assert all(i["source"] == "llm" for i in items)


def test_effective_mode_rules_only_without_api_key(monkeypatch) -> None:
    monkeypatch.setattr(
        "cyberpunk_mod_manager.services.install_plan.config.openai_api_key",
        "",
    )
    monkeypatch.setattr(
        "cyberpunk_mod_manager.services.install_plan.config.install_plan_mode",
        "llm_first",
    )
    assert effective_install_plan_mode() == "rules_only"


@pytest.mark.asyncio
async def test_build_install_plan_llm_first(monkeypatch, tmp_path) -> None:
    from cyberpunk_mod_manager import config as cfg

    archive = tmp_path / "mod.zip"
    archive.write_bytes(b"fake")

    monkeypatch.setattr(cfg.config, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.config, "install_plan_mode", "llm_first")

    inspection = _cet_inspection()
    llm_files = [
        {
            "src": "cet_1.37.1/bin/x64/version.dll",
            "target": "bin/x64/version.dll",
            "reason": "CET",
        }
    ]

    with patch(
        "cyberpunk_mod_manager.services.install_plan.inspect_archive",
        return_value=inspection,
    ), patch(
        "cyberpunk_mod_manager.services.install_plan._llm_plan_install",
        new=AsyncMock(return_value=(llm_files, "按说明保留 bin/x64 结构")),
    ):
        plan = await build_install_plan(
            107,
            archive,
            mod_name="Cyber Engine Tweaks",
            description="Drop zip contents into game folder",
        )

    assert plan["plan_source"] == "llm"
    assert plan["plan_mode"] == "llm_first"
    assert "version.dll" in plan["file_mappings"]["cet_1.37.1/bin/x64/version.dll"]


@pytest.mark.asyncio
async def test_build_install_plan_llm_fallback_to_rules(monkeypatch, tmp_path) -> None:
    from cyberpunk_mod_manager import config as cfg

    archive = tmp_path / "mod.zip"
    archive.write_bytes(b"fake")
    monkeypatch.setattr(cfg.config, "openai_api_key", "test-key")
    monkeypatch.setattr(cfg.config, "install_plan_mode", "llm_first")

    inspection = _cet_inspection()
    with patch(
        "cyberpunk_mod_manager.services.install_plan.inspect_archive",
        return_value=inspection,
    ), patch(
        "cyberpunk_mod_manager.services.install_plan._llm_plan_install",
        new=AsyncMock(return_value=([], "")),
    ):
        plan = await build_install_plan(107, archive)

    assert plan["plan_source"] == "rules_fallback"
    assert plan["file_mappings"]


def test_merge_hybrid_keeps_rules_and_llm() -> None:
    inspection = _cet_inspection()
    mappings, _items = merge_plan_mappings(
        inspection,
        [
            {
                "src": "cet_1.37.1/bin/x64/version.dll",
                "target": "bin/x64/version.dll",
                "reason": "LLM",
            }
        ],
    )
    assert "cet_1.37.1/bin/x64/plugins/cyber_engine_tweaks.asi" in mappings
    assert mappings["cet_1.37.1/bin/x64/version.dll"] == "bin/x64/version.dll"
