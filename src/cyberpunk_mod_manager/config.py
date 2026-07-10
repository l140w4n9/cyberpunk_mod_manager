# -*- coding: utf-8 -*-
"""配置管理：从配置文件读取，环境变量可覆盖。

配置文件查找顺序：
1. 环境变量 CP2077_CONFIG 指定的路径
2. 当前工作目录下的 config.yaml / config.yml / config.toml
3. Python 包所在目录及其上级目录（支持从仓库根目录启动）
4. 数据目录 (~/.cyberpunk_mod_manager/config.yaml)

配置文件示例 (config.yaml)：

    game_path: "D:/Steam/steamapps/common/Cyberpunk 2077"
    nexus_api_key: "你的 Nexus API Key"
    openai_api_key: "你的 LLM API Key"
    model_name: "gpt-4o-mini"
    openai_base_url: "https://api.openai.com/v1"
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _package_search_dirs() -> list[Path]:
    """从已安装包位置向上收集可能包含 config 的目录。"""
    try:
        import cyberpunk_mod_manager as pkg

        root = Path(pkg.__file__).resolve().parent
    except Exception:
        return []
    dirs: list[Path] = []
    cur = root
    for _ in range(5):
        dirs.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    return dirs


def _find_config_file() -> Path | None:
    """按优先级查找配置文件。"""
    names = ("config.yaml", "config.yml", "config.toml")
    candidates: list[Path] = []
    env_path = os.environ.get("CP2077_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    for name in names:
        candidates.append(Path.cwd() / name)
    for directory in _package_search_dirs():
        for name in names:
            candidates.append(directory / name)
    candidates.append(Path.home() / ".cyberpunk_mod_manager" / "config.yaml")

    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists():
            return p
    return None


def _load_config_file(path: Path | None) -> dict[str, Any]:
    """加载指定配置文件内容为字典；path 为 None 时返回空字典。"""
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        try:
            import tomllib  # Python 3.11+
        except ImportError:
            import tomli as tomllib  # type: ignore
        return tomllib.loads(text)
    # yaml —— 必需依赖（pyyaml>=6.0），缺失时让 ImportError 直接抛出，
    # 而非静默返回空配置导致后续以默认值运行并产生难以定位的错误。
    import yaml
    return yaml.safe_load(text) or {}


class AppConfig(BaseModel):
    """运行时配置。

    取值优先级：环境变量 > 配置文件 > 默认值。
    """

    # Cyberpunk 2077 游戏安装根目录
    game_path: str = r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077"
    # Nexus Mods API Key
    nexus_api_key: str = ""
    # LLM 配置
    openai_api_key: str = ""
    model_name: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    # 应用名称，用于 Nexus API 请求头
    app_name: str = "CyberpunkModManager"
    # 数据目录
    data_dir: Path = Path.home() / ".cyberpunk_mod_manager"
    # 已加载的配置文件路径（便于调试）
    config_file: str = ""

    def model_post_init(self, __context) -> None:  # type: ignore[override]
        # 仅做类型规范化，不在导入时产生文件系统副作用。
        self.data_dir = Path(self.data_dir)

    def ensure_dirs(self) -> None:
        """创建数据与下载目录。应在应用启动时调用，而非导入时。"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    @property
    def downloads_dir(self) -> Path:
        """下载缓存目录（始终派生自 data_dir，不作为可配置字段）。"""
        return self.data_dir / "downloads"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "manager.db"

    @property
    def nexus_headers(self) -> dict[str, str]:
        """Nexus API 请求头（参考 Stardrop NexusClient.CreateClient）。"""
        return {
            "apikey": self.nexus_api_key,
            "Application-Name": self.app_name,
            "Application-Version": "0.1.0",
            "User-Agent": f"{self.app_name}/0.1.0",
        }


def _build_config() -> AppConfig:
    """合并配置文件、环境变量，构建 AppConfig。"""
    # 只查找一次配置文件，避免两次调用间文件系统变化导致不一致。
    config_path = _find_config_file()
    file_cfg = _load_config_file(config_path)

    # 环境变量覆盖（优先级最高）
    env_map = {
        "game_path": "CP2077_GAME_PATH",
        "nexus_api_key": "NEXUS_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "model_name": "MODEL_NAME",
        "openai_base_url": "OPENAI_BASE_URL",
        "data_dir": "CP2077_DATA_DIR",
    }
    merged: dict[str, Any] = dict(file_cfg)
    for field, env_var in env_map.items():
        val = os.environ.get(env_var)
        if val:
            merged[field] = val
    if config_path is not None:
        merged["config_file"] = str(config_path)
    return AppConfig(**merged)


# 全局单例
config = _build_config()
