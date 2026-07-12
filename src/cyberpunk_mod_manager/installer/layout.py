# -*- coding: utf-8 -*-
"""压缩包路径规范化：剥离多余外层目录，使框架包路径对齐游戏根目录。"""
from __future__ import annotations

from collections.abc import Callable


def _normalize_slash(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _strip_leading_segments(rel: str, depth: int) -> str:
    parts = _normalize_slash(rel).split("/")
    if depth <= 0 or len(parts) <= depth:
        return _normalize_slash(rel)
    return "/".join(parts[depth:])


def _score_known_prefixes(rel: str, prefixes: list[str]) -> int:
    norm = _normalize_slash(rel)
    return int(any(norm.startswith(prefix) for prefix in prefixes))


def detect_wrapper_strip_depth(entries: list[str], known_prefixes: list[str]) -> int:
    """检测应剥离的外层目录层数（如 cet_1.37.1/bin/x64 → 剥掉 cet_1.37.1）。"""
    if not entries or not known_prefixes:
        return 0
    best_depth = 0
    best_score = -1
    max_depth = min(4, max(len(_normalize_slash(e).split("/")) for e in entries))
    for depth in range(0, max_depth + 1):
        score = sum(
            _score_known_prefixes(
                _strip_leading_segments(e, depth), known_prefixes
            )
            for e in entries
        )
        if score > best_score:
            best_score = score
            best_depth = depth
    if best_score <= 0:
        return 0
    return best_depth


def build_path_normalizer(
    entries: list[str],
    known_prefixes: list[str],
) -> Callable[[str], str]:
    """根据整包条目列表构建路径规范化函数。"""
    depth = detect_wrapper_strip_depth(entries, known_prefixes)

    def normalize(rel: str) -> str:
        return _strip_leading_segments(rel, depth)

    return normalize
