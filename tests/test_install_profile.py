# -*- coding: utf-8 -*-
"""游戏安装档案加载测试。"""
from __future__ import annotations

from pathlib import Path

import yaml

from cyberpunk_mod_manager.installer.profile import (
    GameInstallProfile,
    load_game_profile,
    reload_install_profile,
)


def test_load_builtin_cyberpunk_profile() -> None:
    reload_install_profile()
    profile = load_game_profile("cyberpunk2077")
    assert profile.game_domain == "cyberpunk2077"
    assert any(
        prefix.startswith("bin/x64/") for prefix in profile.preserve_prefix_strings
    )
    assert profile.extension_rules
    cet = next(
        (c for c in profile.framework_checks if 107 in c.mod_ids),
        None,
    )
    assert cet is not None
    assert "bin/x64/version.dll" in cet.required_paths


def test_user_profile_overrides_builtin(tmp_path, monkeypatch) -> None:
    custom = tmp_path / "game_profiles" / "cyberpunk2077.yaml"
    custom.parent.mkdir(parents=True)
    custom.write_text(
        yaml.safe_dump(
            {
                "game_domain": "cyberpunk2077",
                "display_name": "Custom CP77",
                "preserve_prefixes": [{"prefix": "custom_root/"}],
                "extension_rules": [],
                "structure_rules": [],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cyberpunk_mod_manager.installer.profile.config.data_dir", str(tmp_path)
    )
    reload_install_profile()
    profile = load_game_profile("cyberpunk2077")
    assert profile.display_name == "Custom CP77"
    assert profile.preserve_prefix_strings == ["custom_root/"]


def test_profile_from_dict_accepts_string_prefixes() -> None:
    profile = GameInstallProfile.from_dict(
        {
            "game_domain": "testgame",
            "preserve_prefixes": ["mods/", "data/"],
        }
    )
    assert profile.preserve_prefix_strings == ["mods/", "data/"]
