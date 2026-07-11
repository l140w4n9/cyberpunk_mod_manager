# -*- coding: utf-8 -*-
"""测试公共配置：在导入项目模块前设置隔离环境。"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

_test_root = Path(tempfile.mkdtemp(prefix="cp2077_test_"))
_test_config = _test_root / "config.yaml"
os.environ["CP2077_CONFIG"] = str(_test_config)
os.environ["CP2077_DATA_DIR"] = str(_test_root)
os.environ["CP2077_GAME_PATH"] = str(_test_root / "game")
os.environ["NEXUS_API_KEY"] = "test-nexus-key"
os.environ["OPENAI_API_KEY"] = "test-openai-key"

(_test_root / "game").mkdir(parents=True, exist_ok=True)
_test_config.write_text(
    "data_dir: " + str(_test_root).replace("\\", "/") + "\n",
    encoding="utf-8",
)
