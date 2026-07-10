# -*- coding: utf-8 -*-
"""模组压缩包解压（zip / 7z / rar / 单文件）。"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

# 可直接安装的单个模组文件（无需解压）
SINGLE_MOD_SUFFIXES = {
    ".archive",
    ".xl",
    ".reds",
    ".lua",
    ".tweak",
    ".yaml",
    ".yml",
}


def detect_archive_kind(path: Path) -> str:
    """检测文件类型：zip / 7z / rar / single / unknown。"""
    suffix = path.suffix.lower()
    if suffix in SINGLE_MOD_SUFFIXES:
        return "single"

    with path.open("rb") as fh:
        magic = fh.read(8)

    if magic[:2] == b"PK":
        return "zip"
    if magic[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if magic[:4] == b"Rar!":
        return "rar"
    if magic[:5] == b"<!DOC" or magic[:5] == b"<html":
        return "html"
    return "unknown"


def _extract_zip(archive_path: Path, dest_dir: Path) -> None:
    with zipfile.ZipFile(archive_path, "r") as zf:
        total_size = sum(info.file_size for info in zf.infolist())
        max_size = 2 * 1024 * 1024 * 1024
        if total_size > max_size:
            raise ValueError(
                f"Archive uncompressed size ({total_size} bytes) exceeds limit"
            )
        dest_resolved = dest_dir.resolve()
        for info in zf.infolist():
            target = (dest_dir / info.filename).resolve()
            if not target.is_relative_to(dest_resolved):
                raise ValueError(f"Unsafe path in archive: {info.filename}")
        zf.extractall(dest_dir)


def _extract_7z_py7zr(archive_path: Path, dest_dir: Path) -> None:
    import py7zr

    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        archive.extractall(path=dest_dir)


def _find_7z_exe() -> str | None:
    candidates = [
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _extract_with_7z_cli(archive_path: Path, dest_dir: Path) -> None:
    exe = _find_7z_exe()
    if exe is None:
        raise RuntimeError(
            "无法解压该格式。请安装 7-Zip，或将模组手动解压为 zip 后再安装。"
        )
    dest_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [exe, "x", str(archive_path), f"-o{dest_dir}", "-y"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"7-Zip 解压失败: {stderr or proc.returncode}")


def extract_archive(archive_path: Path, dest_dir: Path) -> str:
    """解压模组包到目标目录，返回检测到的格式类型。"""
    if not archive_path.is_file():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    kind = detect_archive_kind(archive_path)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    if kind == "single":
        shutil.copy2(archive_path, dest_dir / archive_path.name)
        return kind
    if kind == "html":
        raise ValueError(
            f"下载文件不是有效压缩包（疑似 HTML 错误页）: {archive_path.name}"
        )
    if kind == "zip":
        try:
            _extract_zip(archive_path, dest_dir)
        except zipfile.BadZipFile as exc:
            raise ValueError(
                f"文件不是有效的 zip 压缩包: {archive_path.name}"
            ) from exc
        return kind
    if kind == "7z":
        try:
            _extract_7z_py7zr(archive_path, dest_dir)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).debug(
                "py7zr extraction failed, falling back to 7z CLI",
                exc_info=exc,
            )
            _extract_with_7z_cli(archive_path, dest_dir)
        return kind
    if kind == "rar":
        _extract_with_7z_cli(archive_path, dest_dir)
        return kind

    # 按扩展名兜底
    suffix = archive_path.suffix.lower()
    if suffix == ".zip":
        _extract_zip(archive_path, dest_dir)
        return "zip"
    if suffix == ".7z":
        try:
            _extract_7z_py7zr(archive_path, dest_dir)
        except Exception:
            _extract_with_7z_cli(archive_path, dest_dir)
        return "7z"
    if suffix == ".rar":
        _extract_with_7z_cli(archive_path, dest_dir)
        return "rar"

    raise ValueError(
        f"不支持的压缩格式: {archive_path.name}。"
        "请使用 zip/7z/rar，或将文件解压后重新打包为 zip。"
    )
