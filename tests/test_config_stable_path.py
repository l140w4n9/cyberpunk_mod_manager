# -*- coding: utf-8 -*-
"""配置路径稳定性测试。"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import cyberpunk_mod_manager.config as config_mod
from cyberpunk_mod_manager.config import _default_config_write_path, save_config


def _reload_config_module(monkeypatch, cwd: Path):
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("CP2077_CONFIG", raising=False)
    original = sys.modules.get("cyberpunk_mod_manager.config")
    sys.modules.pop("cyberpunk_mod_manager.config", None)
    mod = importlib.import_module("cyberpunk_mod_manager.config")
    if original is not None:
        monkeypatch.setitem(sys.modules, "cyberpunk_mod_manager.config", original)
    return mod


def test_default_write_path_does_not_use_cwd(monkeypatch, tmp_path: Path) -> None:
    """无配置文件时，默认写入路径不应依赖 cwd。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CP2077_CONFIG", raising=False)
    path = _default_config_write_path()
    assert path.name == "config.yaml"
    assert not str(path).startswith(str(tmp_path))


def test_save_writes_to_loaded_config_file(monkeypatch, tmp_path: Path) -> None:
    """保存应写回已加载的配置文件，而非 cwd。"""
    cfg_file = tmp_path / "project" / "config.yaml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(
        "data_dir: " + str(tmp_path / "data").replace("\\", "/") + "\n",
        encoding="utf-8",
    )
    other_cwd = tmp_path / "other_cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    monkeypatch.setattr(config_mod.config, "config_file", str(cfg_file))

    saved = save_config(
        {
            "data_dir": str(tmp_path / "data2"),
            "game_path": str(tmp_path / "game"),
            "nexus_api_key": "nk",
            "openai_api_key": "ok",
            "model_name": "m",
            "openai_base_url": "https://api.example.com/v1",
        }
    )
    assert saved == cfg_file
    text = cfg_file.read_text(encoding="utf-8")
    assert "data2" in text.replace("\\", "/")
