# -*- coding: utf-8 -*-
"""Nexus 智能文件选择测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.nexus.client import select_download_file
from cyberpunk_mod_manager.nexus.file_selection import (
    FileSlotCandidate,
    filter_install_candidates,
    is_non_installable_candidate,
    pick_install_versions,
    rank_candidates,
)
from cyberpunk_mod_manager.nexus.schemas import ModDetails, ModFile


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


def test_filters_customer_guide_slot() -> None:
    """模拟 #11077：指南槽位应被过滤。"""
    guide = FileSlotCandidate(
        slot_name="Lizzie's Braindances Guide",
        mod_file_id="2743971",
        version=ModFile(
            file_id=151701,
            file_name="Lizzie's Braindances - Customer's Guide",
            category="main",
            version_id="v-guide",
        ),
        version_raw={},
    )
    mod = FileSlotCandidate(
        slot_name="Lizzie's Braindances",
        mod_file_id="2743972",
        version=ModFile(
            file_id=151698,
            file_name="Lizzie's Braindances 3.12",
            category="main",
            version_id="v-mod",
        ),
        version_raw={},
    )
    assert is_non_installable_candidate(guide)
    assert not is_non_installable_candidate(mod)
    installable = filter_install_candidates([guide, mod])
    assert installable == [mod]
    ranked = rank_candidates("Lizzie's Braindances", installable)
    assert ranked[0].version.file_id == 151698


async def test_pick_install_versions_heuristic_for_11077(monkeypatch) -> None:
    """无 LLM 时启发式应选中真正模组包。"""
    guide_version = {
        "id": "v-guide",
        "name": "Lizzie's Braindances - Customer's Guide",
        "category": "main",
        "game_scoped_id": "151701",
        "file": {"id": "2743971"},
    }
    mod_version = {
        "id": "v-mod",
        "name": "Lizzie's Braindances 3.12",
        "category": "main",
        "game_scoped_id": "151698",
        "file": {"id": "2743972"},
    }

    class FakeClient:
        async def resolve_mod_internal_id(self, mod_id: int) -> str:
            return "internal-11077"

        async def get_mod_files_v3(self, internal: str) -> list[dict]:
            return [
                {"id": "2743971", "name": "Lizzie's Braindances Guide"},
                {"id": "2743972", "name": "Lizzie's Braindances"},
            ]

        async def get_mod_file_versions(self, mod_file_id: str) -> list[dict]:
            if mod_file_id == "2743971":
                return [guide_version]
            return [mod_version]

    details = ModDetails(mod_id=11077, name="Lizzie's Braindances")
    monkeypatch.setattr(
        "cyberpunk_mod_manager.nexus.file_selection.config.openai_api_key",
        "",
    )
    picked = await pick_install_versions(FakeClient(), 11077, details=details)
    assert len(picked) == 1
    assert picked[0].file_id == 151698
