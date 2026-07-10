# -*- coding: utf-8 -*-
"""Cyberpunk 2077 模组安装路径映射规则。

不同文件类型需放置到游戏目录的不同子路径，安装时据此决定目标位置，
卸载时根据记录的 added_files 反向删除。
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass


@dataclass
class InstallRule:
    """一条安装规则：匹配模式 → 目标子路径（相对游戏根目录）。"""

    pattern: str
    target_subpath: str
    description: str = ""


# Cyberpunk 2077 常见模组文件安装规则（顺序敏感，先匹配先生效）
INSTALL_RULES: list[InstallRule] = [
    # 原生 archive 模组
    InstallRule("*.archive", "archive/pc/mod", "原生 archive 模组"),
    # ArchiveXL
    InstallRule("*.xl", "archive/pc/mod", "ArchiveXL 模组"),
    # TweakXL
    InstallRule("*.tweak", "r6/tweaks", "TweakXL 调整文件"),
    InstallRule("*.yaml", "r6/tweaks", "TweakXL YAML 调整"),
    # redscript
    InstallRule("*.reds", "r6/scripts", "redscript 脚本"),
    # Cyber Engine Tweaks (CET) lua 脚本
    InstallRule("*.lua", "bin/x64/plugins/cyber_engine_tweaks/mods", "CET lua 脚本"),
    # 预设目录结构（保留原始相对路径）
    InstallRule("archive/pc/mod/*", "archive/pc/mod", "已有 archive 结构"),
    InstallRule("r6/scripts/*", "r6/scripts", "已有 redscript 结构"),
    InstallRule("r6/tweaks/*", "r6/tweaks", "已有 tweak 结构"),
    InstallRule(
        "bin/x64/plugins/*",
        "bin/x64/plugins",
        "已有 plugins 结构",
    ),
]


def match_rule(rel_path: str) -> InstallRule | None:
    """根据文件相对路径匹配安装规则。"""
    rel_path = rel_path.replace("\\", "/")
    for rule in INSTALL_RULES:
        if fnmatch.fnmatch(rel_path, rule.pattern):
            return rule
        # 也匹配纯文件名
        basename = rel_path.rsplit("/", 1)[-1]
        if fnmatch.fnmatch(basename, rule.pattern):
            return rule
    return None


def resolve_target(rel_path: str, rule: InstallRule) -> str:
    """计算文件最终目标相对路径。"""
    rel_path = rel_path.replace("\\", "/")
    # 压缩包内已包含正确目录结构时，保留完整相对路径
    if rel_path.startswith(rule.target_subpath + "/"):
        return rel_path
    if rule.pattern.endswith("/*"):
        prefix = rule.pattern[:-2]
        if rel_path.startswith(prefix + "/"):
            return rel_path
    basename = rel_path.rsplit("/", 1)[-1]
    return f"{rule.target_subpath}/{basename}"
