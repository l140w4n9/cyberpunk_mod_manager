# -*- coding: utf-8 -*-
"""模组安装路径映射：从可配置的游戏档案加载规则。"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass

from .profile import GameInstallProfile, InstallRuleSpec, get_install_profile


@dataclass
class InstallRule:
    """一条安装规则：匹配模式 → 目标子路径（相对游戏根目录）。"""

    pattern: str
    target_subpath: str
    description: str = ""


def _spec_to_rule(spec: InstallRuleSpec) -> InstallRule:
    return InstallRule(
        pattern=spec.pattern,
        target_subpath=spec.target_subpath,
        description=spec.description,
    )


def _profile_rules(profile: GameInstallProfile) -> tuple[
    list[tuple[str, str, str]],
    list[InstallRule],
]:
    structure = [_spec_to_rule(spec) for spec in profile.structure_rules]
    extension = [_spec_to_rule(spec) for spec in profile.extension_rules]
    return profile.preserve_prefixes, structure + extension


def match_rule(
    rel_path: str,
    *,
    profile: GameInstallProfile | None = None,
) -> InstallRule | None:
    """根据文件相对路径匹配安装规则。"""
    prof = profile or get_install_profile()
    rel_path = rel_path.replace("\\", "/")
    prefix_rules, install_rules = _profile_rules(prof)
    for prefix, target_subpath, description in prefix_rules:
        if rel_path.startswith(prefix):
            return InstallRule(f"{prefix}*", target_subpath, description)
    for rule in install_rules:
        if fnmatch.fnmatch(rel_path, rule.pattern):
            return rule
        basename = rel_path.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(basename, rule.pattern):
            return rule
    return None


def resolve_target(rel_path: str, rule: InstallRule) -> str:
    """计算文件最终目标相对路径。"""
    rel_path = rel_path.replace("\\", "/")
    if not rule.target_subpath:
        basename = rel_path.rsplit("/", 1)[-1]
        return basename
    if rel_path.startswith(rule.target_subpath + "/"):
        return rel_path
    if rule.pattern.endswith("/*"):
        prefix = rule.pattern[:-2]
        if rel_path.startswith(prefix + "/"):
            return rel_path
    if rule.pattern.endswith("/*") and rule.pattern[:-2].endswith("/"):
        prefix = rule.pattern[:-1]
        if rel_path.startswith(prefix):
            return rel_path
    basename = rel_path.rsplit("/", 1)[-1]
    return f"{rule.target_subpath}/{basename}"


def resolve_mapping(
    archive_rel: str,
    *,
    profile: GameInstallProfile | None = None,
    normalizer=None,
) -> str | None:
    """将压缩包内相对路径解析为游戏目录相对路径。"""
    norm = normalizer(archive_rel) if normalizer else archive_rel.replace("\\", "/")
    rule = match_rule(norm, profile=profile)
    if rule is None:
        return None
    return resolve_target(norm, rule)
