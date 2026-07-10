# -*- coding: utf-8 -*-
"""安装路径规则单元测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.installer.rules import match_rule, resolve_target


def test_match_archive_by_extension() -> None:
    rule = match_rule("some_folder/foo.archive")
    assert rule is not None
    assert rule.target_subpath == "archive/pc/mod"


def test_match_reds_script() -> None:
    rule = match_rule("scripts/my_mod.reds")
    assert rule is not None
    assert rule.target_subpath == "r6/scripts"


def test_match_lua_cet_script() -> None:
    rule = match_rule("mymod/init.lua")
    assert rule is not None
    assert rule.target_subpath == "bin/x64/plugins/cyber_engine_tweaks/mods"


def test_resolve_flat_archive_to_target() -> None:
    rule = match_rule("foo.archive")
    assert rule is not None
    assert resolve_target("foo.archive", rule) == "archive/pc/mod/foo.archive"


def test_resolve_preserves_existing_structure() -> None:
    rel = "archive/pc/mod/custom/foo.archive"
    rule = match_rule(rel)
    assert rule is not None
    assert resolve_target(rel, rule) == rel


def test_resolve_preserves_cet_mod_folder() -> None:
    rel = "bin/x64/plugins/cyber_engine_tweaks/mods/mymod/init.lua"
    rule = match_rule(rel)
    assert rule is not None
    assert resolve_target(rel, rule) == rel


def test_skip_unknown_file() -> None:
    assert match_rule("readme.txt") is None
