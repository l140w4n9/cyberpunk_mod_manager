# -*- coding: utf-8 -*-
"""YAML 路径转义处理测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cyberpunk_mod_manager.config import ConfigError, _load_config_file, save_config


def test_load_windows_path_with_forward_slashes(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "data_dir: D:/foo/bar\n"
        "game_path: D:/games/cyberpunk\n",
        encoding="utf-8",
    )
    data = _load_config_file(cfg)
    assert "foo" in data["data_dir"]
    assert "\\" in data["data_dir"] or "/" in data["data_dir"]


def test_reject_invalid_yaml_escape(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text('data_dir: "D:\\development\\test"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        _load_config_file(cfg)


def test_save_uses_forward_slashes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = save_config(
        {
            "data_dir": r"D:\my data\mods",
            "game_path": r"D:\Games\CP2077",
            "nexus_api_key": "",
            "openai_api_key": "",
        }
    )
    text = path.read_text(encoding="utf-8")
    parsed = yaml.safe_load(text)
    assert parsed["data_dir"] == "D:/my data/mods"
    assert "\\d" not in text or "D:/" in text
