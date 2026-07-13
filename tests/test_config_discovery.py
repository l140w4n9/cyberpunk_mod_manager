# -*- coding: utf-8 -*-
"""配置发现逻辑测试。"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


def _reload_config(monkeypatch, cwd: Path) -> object:
    monkeypatch.chdir(cwd)
    original = sys.modules.get("cyberpunk_mod_manager.config")
    sys.modules.pop("cyberpunk_mod_manager.config", None)
    mod = importlib.import_module("cyberpunk_mod_manager.config")
    if original is not None:
        monkeypatch.setitem(sys.modules, "cyberpunk_mod_manager.config", original)
    return mod.config


def test_finds_config_from_repo_root(monkeypatch, tmp_path: Path) -> None:
    """从仓库根目录启动时，应能找到 config.yaml。"""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "data_dir: " + str(tmp_path / "data").replace("\\", "/") + "\n"
        "openai_api_key: test-key\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CP2077_CONFIG", str(config_file))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NEXUS_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("CP2077_DATA_DIR", raising=False)
    cfg = _reload_config(monkeypatch, tmp_path)
    assert cfg.openai_api_key == "test-key"
    assert cfg.has_data_dir is True
    assert cfg.config_file.endswith("config.yaml")
