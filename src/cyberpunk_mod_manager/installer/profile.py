# -*- coding: utf-8 -*-
"""游戏安装档案：可配置的路径规则，支持换游戏/换目录而不改代码。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import config

logger = logging.getLogger(__name__)

_PACKAGE_GAMES_DIR = Path(__file__).resolve().parent.parent / "games"


@dataclass
class FrameworkCheck:
    name: str
    mod_ids: list[int] = field(default_factory=list)
    required_paths: list[str] = field(default_factory=list)


@dataclass
class InstallRuleSpec:
    pattern: str
    target_subpath: str
    description: str = ""


@dataclass
class GameInstallProfile:
    """单个游戏的安装路径策略。"""

    game_domain: str
    display_name: str
    preserve_prefixes: list[tuple[str, str, str]] = field(default_factory=list)
    structure_rules: list[InstallRuleSpec] = field(default_factory=list)
    extension_rules: list[InstallRuleSpec] = field(default_factory=list)
    framework_checks: list[FrameworkCheck] = field(default_factory=list)
    source_path: str = ""

    @property
    def preserve_prefix_strings(self) -> list[str]:
        return [item[0] for item in self.preserve_prefixes]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source_path: str = "") -> GameInstallProfile:
        prefixes: list[tuple[str, str, str]] = []
        for item in data.get("preserve_prefixes") or []:
            if isinstance(item, str):
                prefix = item.strip().replace("\\", "/")
                if prefix and not prefix.endswith("/"):
                    prefix += "/"
                prefixes.append((prefix, prefix.rstrip("/"), "保留目录结构"))
                continue
            prefix = str(item.get("prefix") or "").strip().replace("\\", "/")
            if not prefix:
                continue
            if not prefix.endswith("/"):
                prefix += "/"
            target = str(item.get("target_subpath") or prefix.rstrip("/")).replace(
                "\\", "/"
            )
            desc = str(item.get("description") or "保留目录结构")
            prefixes.append((prefix, target, desc))

        def _load_rules(key: str) -> list[InstallRuleSpec]:
            rules: list[InstallRuleSpec] = []
            for item in data.get(key) or []:
                pattern = str(item.get("pattern") or "").strip()
                if not pattern:
                    continue
                rules.append(
                    InstallRuleSpec(
                        pattern=pattern,
                        target_subpath=str(item.get("target_subpath", "")).replace(
                            "\\", "/"
                        ),
                        description=str(item.get("description") or ""),
                    )
                )
            return rules

        checks: list[FrameworkCheck] = []
        for item in data.get("framework_checks") or []:
            mod_ids = item.get("mod_ids") or []
            checks.append(
                FrameworkCheck(
                    name=str(item.get("name") or "框架"),
                    mod_ids=[int(x) for x in mod_ids],
                    required_paths=[
                        str(p).replace("\\", "/")
                        for p in (item.get("required_paths") or [])
                    ],
                )
            )

        return cls(
            game_domain=str(data.get("game_domain") or "unknown"),
            display_name=str(data.get("display_name") or data.get("game_domain") or ""),
            preserve_prefixes=prefixes,
            structure_rules=_load_rules("structure_rules"),
            extension_rules=_load_rules("extension_rules"),
            framework_checks=checks,
            source_path=source_path,
        )


def _profile_search_paths(game_domain: str) -> list[Path]:
    paths: list[Path] = []
    if config.has_data_dir:
        paths.append(config.data_dir_path / "game_profiles" / f"{game_domain}.yaml")
        paths.append(config.data_dir_path / "game_profiles" / f"{game_domain}.yml")
    paths.append(_PACKAGE_GAMES_DIR / f"{game_domain}.yaml")
    paths.append(_PACKAGE_GAMES_DIR / f"{game_domain}.yml")
    return paths


def load_game_profile(game_domain: str | None = None) -> GameInstallProfile:
    """加载安装档案：data_dir 用户配置优先，否则使用包内默认。"""
    domain = (game_domain or getattr(config, "game_domain", "") or "cyberpunk2077").strip()
    for path in _profile_search_paths(domain):
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            profile = GameInstallProfile.from_dict(raw, source_path=str(path))
            logger.debug("Loaded install profile from %s", path)
            return profile
        except (OSError, yaml.YAMLError, ValueError) as exc:
            logger.warning("Failed to load profile %s: %s", path, exc)
    raise FileNotFoundError(
        f"未找到游戏安装档案: {domain}。"
        f"请在 {_PACKAGE_GAMES_DIR} 或 data_dir/game_profiles/ 下提供 {domain}.yaml"
    )


@lru_cache(maxsize=8)
def get_install_profile(game_domain: str | None = None) -> GameInstallProfile:
    return load_game_profile(game_domain)


def reload_install_profile() -> GameInstallProfile:
    get_install_profile.cache_clear()
    return get_install_profile()


def list_available_profiles() -> list[dict[str, str]]:
    seen: set[str] = set()
    items: list[dict[str, str]] = []
    for directory in (_PACKAGE_GAMES_DIR,):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.y*ml")):
            domain = path.stem
            if domain in seen:
                continue
            seen.add(domain)
            try:
                raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                items.append(
                    {
                        "game_domain": domain,
                        "display_name": str(
                            raw.get("display_name") or domain
                        ),
                        "source": str(path),
                    }
                )
            except (OSError, yaml.YAMLError):
                continue
    return items
