# -*- coding: utf-8 -*-
"""压缩包结构检查（安装前预览，无需完整解压到游戏目录）。"""
from __future__ import annotations

import logging
import subprocess
import zipfile
from pathlib import Path

from .archives import _find_7z_exe, detect_archive_kind
from .rules import match_rule, resolve_target

logger = logging.getLogger(__name__)

_README_HINTS = ("readme", "install", "installation", "manual", "howto", "guide")
_MAX_README_BYTES = 6000
_MAX_TREE_LINES = 80


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _list_zip_files(archive_path: Path) -> list[str]:
    with zipfile.ZipFile(archive_path, "r") as zf:
        return [
            _normalize_rel(name)
            for name in zf.namelist()
            if name and not name.endswith("/")
        ]


def _list_7z_py7zr(archive_path: Path) -> list[str]:
    import py7zr

    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        return [
            _normalize_rel(name)
            for name in archive.getnames()
            if name and not name.endswith("/")
        ]


def _list_7z_cli(archive_path: Path) -> list[str]:
    exe = _find_7z_exe()
    if exe is None:
        raise RuntimeError("未找到 7-Zip，无法列出压缩包内容")
    proc = subprocess.run(
        [exe, "l", "-slt", str(archive_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "7z list failed").strip())
    entries: list[str] = []
    current = ""
    for line in proc.stdout.splitlines():
        if line.startswith("Path = "):
            current = line.split("=", 1)[1].strip()
        elif line.startswith("Folder = -") and current:
            rel = _normalize_rel(current)
            if rel:
                entries.append(rel)
            current = ""
    return entries


def list_archive_entries(archive_path: Path) -> list[str]:
    """列出压缩包内文件相对路径（不解压到游戏目录）。"""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    kind = detect_archive_kind(archive_path)
    if kind == "single":
        return [archive_path.name]
    if kind == "zip":
        return _list_zip_files(archive_path)
    if kind == "7z":
        try:
            return _list_7z_py7zr(archive_path)
        except Exception as exc:
            logger.warning("py7zr list failed for %s: %s", archive_path.name, exc)
            return _list_7z_cli(archive_path)
    if kind == "rar":
        return _list_7z_cli(archive_path)

    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        return _list_zip_files(archive_path)
    if suffix in {".7z", ".rar"}:
        return _list_7z_cli(archive_path)
    raise ValueError(f"不支持的压缩格式: {archive_path.name}")


def _is_readme_path(rel: str) -> bool:
    lower = rel.lower()
    if not lower.endswith((".txt", ".md", ".rtf")):
        return False
    base = lower.rsplit("/", 1)[-1]
    return any(hint in base for hint in _README_HINTS)


def _read_readme_from_zip(archive_path: Path, rel: str) -> str:
    with zipfile.ZipFile(archive_path, "r") as zf:
        with zf.open(rel) as fh:
            data = fh.read(_MAX_README_BYTES)
    return data.decode("utf-8", errors="replace").strip()


def extract_readme_excerpts(archive_path: Path, entries: list[str]) -> list[dict[str, str]]:
    """从压缩包中提取安装说明类文本。"""
    kind = detect_archive_kind(archive_path)
    excerpts: list[dict[str, str]] = []
    candidates = [rel for rel in entries if _is_readme_path(rel)]
    if not candidates and entries:
        candidates = [
            rel
            for rel in entries
            if rel.lower().endswith((".txt", ".md"))
        ][:3]

    for rel in candidates[:5]:
        text = ""
        try:
            if kind == "zip":
                text = _read_readme_from_zip(archive_path, rel)
            else:
                continue
        except Exception as exc:
            logger.debug("readme read failed %s: %s", rel, exc)
            continue
        if text:
            excerpts.append({"path": rel, "text": text[:_MAX_README_BYTES]})
    return excerpts


def _build_tree_preview(entries: list[str], limit: int = _MAX_TREE_LINES) -> str:
    lines: list[str] = []
    for rel in sorted(entries)[:limit]:
        depth = rel.count("/")
        name = rel.rsplit("/", 1)[-1]
        lines.append(f"{'  ' * depth}{name}")
    if len(entries) > limit:
        lines.append(f"... 另有 {len(entries) - limit} 个文件")
    return "\n".join(lines)


def inspect_archive(archive_path: Path) -> dict:
    """检查压缩包结构并预览规则匹配结果。"""
    entries = list_archive_entries(archive_path)
    inspected: list[dict] = []
    matched = skipped = 0

    for rel in entries:
        rule = match_rule(rel)
        if rule is None:
            skipped += 1
            inspected.append(
                {
                    "rel": rel,
                    "status": "skip",
                    "target": None,
                    "rule": None,
                }
            )
            continue
        target = resolve_target(rel, rule)
        matched += 1
        inspected.append(
            {
                "rel": rel,
                "status": "match",
                "target": target,
                "rule": rule.description or rule.pattern,
            }
        )

    return {
        "archive_path": str(archive_path),
        "kind": detect_archive_kind(archive_path),
        "entry_count": len(entries),
        "entries": inspected,
        "matched_count": matched,
        "skipped_count": skipped,
        "readme_excerpts": extract_readme_excerpts(archive_path, entries),
        "tree_preview": _build_tree_preview(entries),
    }
