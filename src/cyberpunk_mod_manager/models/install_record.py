# -*- coding: utf-8 -*-
"""安装记录（卸载计划）模型 —— 安装时记录所有文件操作，卸载时反向执行。"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class InstallRecord(SQLModel, table=True):
    """卸载计划表。

    安装一个模组时写入一条记录，包含：
    - added_files: 安装过程中新增到游戏目录的文件列表（JSON 数组，相对游戏根目录）
    - created_dirs: 安装过程中创建的目录列表（卸载时仅在为空时删除）
    - backed_up_files: 被覆盖前备份的原文件（用于卸载时恢复）
    - config_writes: 写入的配置项（用于回滚）
    - framework: 依赖的框架
    """

    __tablename__ = "install_records"

    id: int | None = Field(default=None, primary_key=True)
    mod_id: int = Field(foreign_key="mods.id", index=True)
    # JSON 字符串：["archive/pc/mod/foo.archive", ...]
    added_files: str = "[]"
    # JSON 字符串：["archive/pc/mod/foo_extra", ...]
    created_dirs: str = "[]"
    # JSON 字符串：[{"path": "...", "backup": "..."}]
    backed_up_files: str = "[]"
    # JSON 字符串：[{"file": "...", "key": "...", "old_value": "..."}]
    config_writes: str = "[]"
    framework: str = ""
    plan_source: str = ""
    # JSON：[{"src","target","source","reason"}]
    plan_json: str = "[]"
    installed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    # 安装包校验信息
    source_file: str = ""
    source_hash: str = ""
