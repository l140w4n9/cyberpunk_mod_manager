# -*- coding: utf-8 -*-
"""配置管理：从配置文件读取，环境变量可覆盖。

配置文件查找顺序：
1. 环境变量 CP2077_CONFIG 指定的路径
2. Python 包所在目录及其上级目录（项目内 config.yaml）
3. 用户配置目录（%APPDATA%/cyberpunk_mod_manager 或 ~/.config/cyberpunk_mod_manager）
4. 当前工作目录（最后兜底，避免随启动目录变化而丢失）

``data_dir`` 为必填项，无默认值；须通过配置文件或前端设置页指定。

配置文件示例 (config.yaml)：

    data_dir: "D:/CyberpunkModManager/data"
    game_path: "D:/Steam/steamapps/common/Cyberpunk 2077"
    nexus_api_key: "你的 Nexus API Key"
    openai_api_key: "你的 LLM API Key"
    model_name: "gpt-4o-mini"
    openai_base_url: "https://api.openai.com/v1"
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

import yaml
from pydantic import BaseModel, Field


class ConfigError(Exception):
    """配置缺失或无效。"""


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


def _user_config_dir() -> Path:
    """跨启动目录稳定的用户级配置目录。"""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "cyberpunk_mod_manager"


def _project_config_candidates() -> list[Path]:
    """从包位置向上收集项目内可能的配置文件。"""
    names = ("config.yaml", "config.yml", "config.toml")
    candidates: list[Path] = []
    for directory in _package_search_dirs():
        for name in names:
            candidates.append(directory / name)
    return candidates


def _default_config_write_path() -> Path:
    """无现有配置时的默认写入位置（不依赖 cwd）。"""
    for directory in _package_search_dirs():
        if (directory / "config.example.yaml").exists():
            return directory / "config.yaml"
    return _user_config_dir() / "config.yaml"


def _find_config_file() -> Path | None:
    """按优先级查找配置文件。"""
    candidates: list[Path] = []
    env_path = os.environ.get("CP2077_CONFIG")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(_project_config_candidates())
    for name in ("config.yaml", "config.yml", "config.toml"):
        candidates.append(_user_config_dir() / name)
    for name in ("config.yaml", "config.yml", "config.toml"):
        candidates.append(Path.cwd() / name)

    seen: set[str] = set()
    for p in candidates:
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists():
            return p
    return None


def resolve_config_write_path(config_file: str = "") -> Path:
    """确定配置写入路径。"""
    if config_file:
        return Path(config_file)
    found = _find_config_file()
    if found is not None:
        return found
    return _default_config_write_path()


def _normalize_path_value(value: Any) -> str:
    """将路径规范为字符串（兼容 YAML 正斜杠写法）。"""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    return str(Path(text).expanduser())


def _yaml_safe_path(value: str) -> str:
    """写入 YAML 时使用正斜杠，避免 Windows 反斜杠转义问题。"""
    text = _normalize_path_value(value)
    return text.replace("\\", "/")


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
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"配置文件格式错误 ({path}): {exc}. "
            "Windows 路径请使用正斜杠，例如 D:/data，或使用双反斜杠 D:\\\\data。"
        ) from exc
    if not isinstance(data, dict):
        raise ConfigError(f"配置文件根节点必须是字典: {path}")
    for key in ("data_dir", "game_path"):
        if key in data and data[key] is not None:
            data[key] = _normalize_path_value(data[key])
    return data


class AppConfig(BaseModel):
    """运行时配置。

    取值优先级：环境变量 > 配置文件 > 默认值。
    """

    # 数据目录（必填，无默认路径）
    data_dir: str = ""
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
    # 已加载的配置文件路径（便于调试）
    config_file: str = ""

    @property
    def has_data_dir(self) -> bool:
        return bool(str(self.data_dir).strip())

    @property
    def data_dir_path(self) -> Path:
        if not self.has_data_dir:
            raise ConfigError(
                "data_dir 未配置。请在前端「设置」页或 config.yaml 中指定数据存放目录。"
            )
        return Path(self.data_dir).expanduser()

    def ensure_dirs(self) -> None:
        """创建数据与下载目录。应在应用启动时调用，而非导入时。"""
        if not self.has_data_dir:
            return
        path = self.data_dir_path
        path.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    @property
    def downloads_dir(self) -> Path:
        """下载缓存目录（派生自 data_dir）。"""
        return self.data_dir_path / "downloads"

    @property
    def db_path(self) -> Path:
        return self.data_dir_path / "manager.db"

    @property
    def nexus_headers(self) -> dict[str, str]:
        """Nexus API 请求头。"""
        return {
            "apikey": self.nexus_api_key,
            "Application-Name": self.app_name,
            "Application-Version": "0.1.0",
            "User-Agent": f"{self.app_name}/0.1.0",
        }

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "data_dir": self.data_dir,
            "game_path": self.game_path,
            "nexus_api_key": self.nexus_api_key,
            "openai_api_key": self.openai_api_key,
            "model_name": self.model_name,
            "openai_base_url": self.openai_base_url,
            "config_file": self.config_file,
            "has_data_dir": self.has_data_dir,
            "downloads_dir": str(self.downloads_dir) if self.has_data_dir else "",
            "db_path": str(self.db_path) if self.has_data_dir else "",
        }


def _build_config() -> AppConfig:
    """合并配置文件、环境变量，构建 AppConfig。"""
    config_path = _find_config_file()
    file_cfg: dict[str, Any] = {}
    if config_path is not None:
        try:
            file_cfg = _load_config_file(config_path)
        except ConfigError as exc:
            logger.warning("配置文件无法解析，将使用空配置: %s", exc)
            file_cfg = {}

    env_map = {
        "data_dir": "CP2077_DATA_DIR",
        "game_path": "CP2077_GAME_PATH",
        "nexus_api_key": "NEXUS_API_KEY",
        "openai_api_key": "OPENAI_API_KEY",
        "model_name": "MODEL_NAME",
        "openai_base_url": "OPENAI_BASE_URL",
    }
    merged: dict[str, Any] = dict(file_cfg)
    for field, env_var in env_map.items():
        val = os.environ.get(env_var)
        if val:
            merged[field] = val
    if config_path is not None:
        merged["config_file"] = str(config_path)
    return AppConfig(**merged)


def save_config(values: dict[str, Any]) -> Path:
    """将配置写入 YAML 文件并热重载。"""
    data_dir = str(values.get("data_dir", "")).strip()
    if not data_dir:
        raise ConfigError("data_dir 为必填项")

    payload = {
        "data_dir": _yaml_safe_path(data_dir),
        "game_path": _yaml_safe_path(
            str(values.get("game_path", "")).strip()
            or r"C:\Program Files (x86)\Steam\steamapps\common\Cyberpunk 2077"
        ),
        "nexus_api_key": str(values.get("nexus_api_key", "")).strip(),
        "openai_api_key": str(values.get("openai_api_key", "")).strip(),
        "model_name": str(values.get("model_name", "gpt-4o-mini")).strip()
        or "gpt-4o-mini",
        "openai_base_url": str(values.get("openai_base_url", "https://api.openai.com/v1")).strip()
        or "https://api.openai.com/v1",
    }

    path = resolve_config_write_path(config.config_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Cyberpunk 2077 模组管理器配置\n"
        "# 也可在前端「设置」页修改\n\n"
    )
    content = header + yaml.safe_dump(payload, allow_unicode=True, default_style="")
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    reload_config()
    if config.config_file == "":
        config.config_file = str(path)
    return path


def reload_config() -> AppConfig:
    """重新加载配置单例。"""
    global config
    config = _build_config()
    if config.config_file == "":
        write_path = resolve_config_write_path()
        if write_path.exists():
            config.config_file = str(write_path)
    return config


# 全局单例
config = _build_config()
