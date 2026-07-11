# -*- coding: utf-8 -*-
"""本地文件夹模组扫描与 ID 识别。"""
from __future__ import annotations

import re
from pathlib import Path

from ..installer.archives import SINGLE_MOD_SUFFIXES, detect_archive_kind

ARCHIVE_EXTENSIONS = {".zip", ".7z", ".rar"} | {
    ext for ext in SINGLE_MOD_SUFFIXES if ext.startswith(".")
}

# Nexus 常见命名：Name-MODID-1-0-1703958711.7z
NEXUS_CDN_RE = re.compile(
    r"-(\d{4,6})-(\d+)-(\d+)-(\d+)(?:\.\w+)?$",
    re.IGNORECASE,
)
NEXUS_CDN_MID_RE = re.compile(
    r"-(\d{4,6})-(\d+)-(\d+)-",
    re.IGNORECASE,
)
TOKEN_RE = re.compile(r"(?:^|[\-_\s])(\d{4,6})(?:[\-_\s\.]|$)")


def is_archive_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() in ARCHIVE_EXTENSIONS:
        return True
    try:
        return detect_archive_kind(path) in {"zip", "7z", "rar", "single"}
    except Exception:
        return False


def parse_mod_id_from_filename(filename: str) -> int | None:
    """从 Nexus 风格文件名推断模组 ID。"""
    name = Path(filename).name
    match = NEXUS_CDN_RE.search(name)
    if match:
        return int(match.group(1))
    match = NEXUS_CDN_MID_RE.search(name)
    if match:
        return int(match.group(1))
    tokens = TOKEN_RE.findall(name)
    if tokens:
        # 多个数字时取最像 Nexus ID 的（较长者优先）
        return int(max(tokens, key=lambda t: (len(t), int(t))))
    lead = re.match(r"^(\d{4,6})[_\-]", name)
    if lead:
        return int(lead.group(1))
    return None


def resolve_folder_path(folder_path: str, *, base: Path | None = None) -> Path:
    """解析文件夹路径（支持相对 downloads 目录）。"""
    raw = (folder_path or "").strip()
    if not raw:
        raise ValueError("文件夹路径不能为空")
    path = Path(raw)
    if not path.is_absolute() and base is not None:
        path = base / raw
    return path.resolve()


def iter_archives_in_folder(folder: Path) -> list[Path]:
    """遍历文件夹内压缩包（含一层子目录）。"""
    if not folder.is_dir():
        return []
    found: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        key = str(path.resolve())
        if key not in seen and is_archive_file(path):
            seen.add(key)
            found.append(path.resolve())

    for entry in sorted(folder.iterdir()):
        if entry.is_file():
            add(entry)
        elif entry.is_dir() and not entry.name.startswith(("_", ".")):
            for child in sorted(entry.iterdir()):
                if child.is_file():
                    add(child)
    return found


def scan_folder(folder: Path) -> dict:
    """扫描文件夹，识别模组 ID 与压缩包。"""
    archives = iter_archives_in_folder(folder)
    by_mod: dict[int, Path] = {}
    unknown: list[dict] = []

    for archive in archives:
        mod_id = parse_mod_id_from_filename(archive.name)
        if mod_id is None:
            unknown.append(
                {
                    "file_name": archive.name,
                    "path": str(archive),
                }
            )
            continue
        existing = by_mod.get(mod_id)
        if existing is None or archive.stat().st_mtime > existing.stat().st_mtime:
            by_mod[mod_id] = archive

    detected = [
        {
            "mod_id": mod_id,
            "file_name": path.name,
            "path": str(path),
        }
        for mod_id, path in sorted(by_mod.items())
    ]
    return {
        "folder": str(folder),
        "detected": detected,
        "unknown": unknown,
        "detected_count": len(detected),
        "unknown_count": len(unknown),
    }


def is_downloads_dir(folder: Path, downloads_dir: Path) -> bool:
    """是否为默认 downloads 缓存目录。"""
    try:
        return folder.resolve() == downloads_dir.resolve()
    except OSError:
        return False


def pick_root_mod_ids(detected_ids: set[int], dependency_getter) -> list[int]:
    """在文件夹内找出「根」模组（不是文件夹内其他模组的依赖）。"""
    dep_of_another: set[int] = set()
    for mod_id in detected_ids:
        for dep in dependency_getter(mod_id):
            if dep.nexus_mod_id in detected_ids:
                dep_of_another.add(dep.nexus_mod_id)
    roots = sorted(detected_ids - dep_of_another)
    return roots if roots else sorted(detected_ids)
