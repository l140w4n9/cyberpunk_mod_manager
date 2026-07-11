# -*- coding: utf-8 -*-
"""收藏夹 URL 解析测试。"""
from __future__ import annotations

import pytest

from cyberpunk_mod_manager.nexus.collections import (
    CollectionParseError,
    parse_collection_url,
)


def test_parse_collection_url_with_mods_suffix() -> None:
    parsed = parse_collection_url(
        "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
    )
    assert parsed.slug == "iszwwe"
    assert parsed.domain == "cyberpunk2077"


def test_parse_collection_url_without_scheme() -> None:
    parsed = parse_collection_url(
        "www.nexusmods.com/games/cyberpunk2077/collections/abc123"
    )
    assert parsed.slug == "abc123"


def test_reject_other_game_domain() -> None:
    with pytest.raises(CollectionParseError):
        parse_collection_url(
            "https://www.nexusmods.com/games/skyrimspecialedition/collections/foo/mods"
        )


def test_reject_invalid_url() -> None:
    with pytest.raises(CollectionParseError):
        parse_collection_url("https://example.com/collections/foo")
