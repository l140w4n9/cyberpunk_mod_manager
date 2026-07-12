# -*- coding: utf-8 -*-
"""安装/卸载引擎。

安装流程：
1. 解压下载的压缩包到临时目录
2. 遍历文件，按 rules.py 匹配目标路径
3. 复制文件到游戏目录（覆盖前备份原文件）
4. 将所有文件操作记录为 InstallRecord（卸载计划）
5. 更新 Mod 状态

卸载流程：
1. 读取 InstallRecord
2. 预检所有 backed_up_files 备份是否存在（缺失则中止，避免误删后无法恢复）
3. 删除 added_files 中的文件
4. 恢复 backed_up_files
5. 清理 created_dirs 中为空的目录
6. 删除 InstallRecord，更新 Mod 状态
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import select

from ..config import config
from ..models import Mod, ModStatus, InstallRecord
from ..storage.db import get_session
from .archives import extract_archive
from .layout import build_path_normalizer
from .profile import get_install_profile
from .rules import match_rule, resolve_target


@dataclass
class InstallResult:
    """安装结果，含卸载计划。"""

    mod_id: int
    added_files: list[str] = field(default_factory=list)
    created_dirs: list[str] = field(default_factory=list)
    backed_up_files: list[dict] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class Installer:
    """模组安装/卸载引擎。"""

    def __init__(self, game_path: str | None = None) -> None:
        self.game_path = Path(game_path or config.game_path)

    def _resolve_target(
        self,
        rel_to_extract: str,
        file_mappings: dict[str, str] | None,
        *,
        normalizer=None,
    ) -> str | None:
        rel = rel_to_extract.replace("\\", "/")
        if file_mappings is not None and rel in file_mappings:
            return file_mappings[rel]
        norm = normalizer(rel) if normalizer else rel
        rule = match_rule(norm)
        if rule is None:
            return None
        return resolve_target(norm, rule)

    def install(
        self,
        mod_id: int,
        archive_path: Path,
        *,
        file_mappings: dict[str, str] | None = None,
        plan_source: str = "",
        plan_items: list[dict] | None = None,
        merge: bool = False,
    ) -> InstallResult:
        """安装指定模组的压缩包，返回安装结果（含卸载计划）。"""
        if not archive_path.exists():
            raise FileNotFoundError(f"Archive not found: {archive_path}")

        # 解压到临时目录
        tmp_dir = config.downloads_dir / f"_extract_{mod_id}"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True)

        result = InstallResult(mod_id=mod_id)
        created_dirs_set: set[str] = set()
        copied_files: list[str] = []  # 已复制文件，用于失败时回滚

        try:
            extract_archive(archive_path, tmp_dir)

            game_root = self.game_path.resolve()
            all_rels: list[str] = []
            for root, _dirs, files in os.walk(tmp_dir):
                root_path = Path(root)
                for fname in files:
                    all_rels.append(
                        (root_path / fname).relative_to(tmp_dir).as_posix()
                    )
            profile = get_install_profile()
            normalizer = build_path_normalizer(
                all_rels, profile.preserve_prefix_strings
            )

            # 遍历解压后的文件
            for root, _dirs, files in os.walk(tmp_dir):
                root_path = Path(root)
                for fname in files:
                    src = root_path / fname
                    rel_to_extract = src.relative_to(tmp_dir).as_posix()
                    if file_mappings is not None:
                        if rel_to_extract not in file_mappings:
                            result.skipped.append(rel_to_extract)
                            continue
                        target_rel = file_mappings[rel_to_extract]
                    else:
                        target_rel = self._resolve_target(
                            rel_to_extract,
                            None,
                            normalizer=normalizer,
                        )
                        if target_rel is None:
                            result.skipped.append(rel_to_extract)
                            continue
                    target_abs = self.game_path / target_rel
                    # 防止路径穿越（zip-slip）：解析后不得逃出游戏目录
                    if not target_abs.resolve().is_relative_to(game_root):
                        raise ValueError(
                            f"Refusing to install file outside game directory: {target_rel}"
                        )
                    target_abs.parent.mkdir(parents=True, exist_ok=True)
                    # 记录创建的目录
                    dir_rel = target_abs.parent.relative_to(self.game_path).as_posix()
                    created_dirs_set.add(dir_rel)
                    # 备份被覆盖的原文件
                    if target_abs.exists():
                        backup_dir = config.data_dir_path / "backups" / str(mod_id)
                        backup_dir.mkdir(parents=True, exist_ok=True)
                        # 保留完整相对路径作为备份名，避免不同子目录下同名文件互相覆盖
                        safe_name = target_rel.replace("/", "__")
                        backup_path = backup_dir / safe_name
                        shutil.copy2(target_abs, backup_path)
                        result.backed_up_files.append(
                            {
                                "path": target_rel,
                                "backup": str(backup_path.relative_to(config.data_dir_path)),
                            }
                        )
                    # 复制文件
                    shutil.copy2(src, target_abs)
                    result.added_files.append(target_rel)
                    copied_files.append(target_rel)

            result.created_dirs = sorted(created_dirs_set)

            if not result.added_files:
                skipped_preview = ", ".join(result.skipped[:5])
                suffix = "…" if len(result.skipped) > 5 else ""
                raise ValueError(
                    "压缩包内没有可安装的文件（安装规则未匹配）。"
                    f"跳过 {len(result.skipped)} 个文件"
                    + (f"，例如：{skipped_preview}{suffix}" if skipped_preview else "")
                )

            # 持久化卸载计划
            self._save_record(
                mod_id,
                result,
                archive_path,
                plan_source=plan_source,
                plan_items=plan_items or [],
                merge=merge,
            )
            # 更新模组状态
            self._update_mod_status(mod_id, ModStatus.INSTALLED)
        except Exception:
            # 回滚：删除已复制的新文件，并恢复被覆盖的原文件
            for rel in copied_files:
                abs_path = self.game_path / rel
                if abs_path.exists():
                    try:
                        abs_path.unlink()
                    except OSError:
                        pass
            for item in result.backed_up_files:
                target_abs = self.game_path / item["path"]
                backup_abs = config.data_dir_path / item["backup"]
                if backup_abs.exists():
                    try:
                        shutil.copy2(backup_abs, target_abs)
                    except OSError:
                        pass
            raise
        finally:
            # 无论成功与否，清理临时目录
            shutil.rmtree(tmp_dir, ignore_errors=True)
        return result

    def uninstall(self, mod_id: int) -> InstallResult:
        """按卸载计划移除模组。"""
        with get_session() as session:
            record = session.exec(
                select(InstallRecord).where(
                    InstallRecord.mod_id == mod_id
                )
            ).first()
            if record is None:
                raise RuntimeError(f"No install record for mod {mod_id}")
            added_files = json.loads(record.added_files)
            created_dirs = json.loads(record.created_dirs)
            backed_up_files = json.loads(record.backed_up_files)

        result = InstallResult(mod_id=mod_id)

        # 1. 删除前先确认所有备份文件都存在，避免删了原文件却无法恢复
        for item in backed_up_files:
            backup_abs = config.data_dir_path / item["backup"]
            if not backup_abs.exists():
                raise RuntimeError(
                    f"Backup file missing, cannot safely uninstall: {item['backup']}"
                )

        # 2. 删除新增文件
        for rel in added_files:
            abs_path = self.game_path / rel
            if abs_path.exists():
                abs_path.unlink()
                result.added_files.append(rel)

        # 3. 恢复备份文件
        for item in backed_up_files:
            target_abs = self.game_path / item["path"]
            backup_abs = config.data_dir_path / item["backup"]
            if backup_abs.exists():
                target_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_abs, target_abs)
                result.backed_up_files.append(item)

        # 4. 清理空目录（自底向上）
        for rel in sorted(created_dirs, key=len, reverse=True):
            abs_dir = self.game_path / rel
            if abs_dir.is_dir() and not any(abs_dir.iterdir()):
                abs_dir.rmdir()
                result.created_dirs.append(rel)

        # 5. 删除记录并更新状态
        with get_session() as session:
            for old in session.exec(
                select(InstallRecord).where(InstallRecord.mod_id == mod_id)
            ).all():
                session.delete(old)
            session.commit()
        self._update_mod_status(mod_id, ModStatus.NOT_INSTALLED)
        return result

    def _save_record(
        self,
        mod_id: int,
        result: InstallResult,
        archive_path: Path,
        *,
        plan_source: str = "",
        plan_items: list[dict] | None = None,
        merge: bool = False,
    ) -> None:
        with get_session() as session:
            existing = session.exec(
                select(InstallRecord).where(InstallRecord.mod_id == mod_id)
            ).first()
            if merge and existing is not None:
                added = json.loads(existing.added_files)
                created = json.loads(existing.created_dirs)
                backed = json.loads(existing.backed_up_files)
                plan_json = json.loads(existing.plan_json or "[]")
                sources = existing.source_file or ""
                added_set = set(added)
                for rel in result.added_files:
                    if rel not in added_set:
                        added.append(rel)
                        added_set.add(rel)
                created_set = set(created)
                for rel in result.created_dirs:
                    if rel not in created_set:
                        created.append(rel)
                        created_set.add(rel)
                backup_paths = {item.get("path") for item in backed}
                for item in result.backed_up_files:
                    if item.get("path") not in backup_paths:
                        backed.append(item)
                if plan_items:
                    plan_json.extend(plan_items)
                source_file = sources
                if str(archive_path) not in sources.split(";"):
                    source_file = (
                        f"{sources};{archive_path}" if sources else str(archive_path)
                    )
                record = InstallRecord(
                    mod_id=mod_id,
                    added_files=json.dumps(added, ensure_ascii=False),
                    created_dirs=json.dumps(created, ensure_ascii=False),
                    backed_up_files=json.dumps(backed, ensure_ascii=False),
                    config_writes=existing.config_writes,
                    source_file=source_file,
                    plan_source=plan_source or existing.plan_source,
                    plan_json=json.dumps(plan_json, ensure_ascii=False),
                )
                session.delete(existing)
                session.add(record)
                session.commit()
                return

        record = InstallRecord(
            mod_id=mod_id,
            added_files=json.dumps(result.added_files, ensure_ascii=False),
            created_dirs=json.dumps(result.created_dirs, ensure_ascii=False),
            backed_up_files=json.dumps(result.backed_up_files, ensure_ascii=False),
            config_writes="[]",
            source_file=str(archive_path),
            plan_source=plan_source,
            plan_json=json.dumps(plan_items or [], ensure_ascii=False),
        )
        with get_session() as session:
            for old in session.exec(
                select(InstallRecord).where(InstallRecord.mod_id == mod_id)
            ).all():
                session.delete(old)
            session.add(record)
            session.commit()

    def _update_mod_status(self, mod_id: int, status: ModStatus) -> None:
        with get_session() as session:
            mod = session.exec(
                select(Mod).where(Mod.id == mod_id)
            ).first()
            if mod is not None:
                mod.status = status
                if status == ModStatus.INSTALLED:
                    mod.installed_at = datetime.now(timezone.utc)
                elif status == ModStatus.NOT_INSTALLED:
                    mod.installed_at = None
                session.add(mod)
                session.commit()
