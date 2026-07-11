# -*- coding: utf-8 -*-
"""配置保存与必填项测试。"""
from __future__ import annotations

from pathlib import Path

import pytest

from cyberpunk_mod_manager.config import ConfigError, save_config


def test_save_config_requires_data_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        save_config({"data_dir": ""})


def test_save_config_writes_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    data_dir = tmp_path / "appdata"
    path = save_config(
        {
            "data_dir": str(data_dir),
            "game_path": str(tmp_path / "game"),
            "nexus_api_key": "nkey",
            "openai_api_key": "okey",
            "model_name": "m1",
            "openai_base_url": "https://api.example.com/v1",
        }
    )
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "data_dir" in text
    assert str(data_dir).replace("\\", "/") in text or str(data_dir) in text
