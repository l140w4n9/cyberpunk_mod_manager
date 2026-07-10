# -*- coding: utf-8 -*-
"""模组库存模型。"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field


class ModStatus(str, enum.Enum):
    """模组状态。

    启用/禁用不由状态枚举表示，而由 ``enabled`` 字段单独控制，
    以避免 ``status == DISABLED`` 与 ``enabled`` 两套机制产生歧义。
    """

    NOT_INSTALLED = "not_installed"
    DOWNLOADED = "downloaded"
    INSTALLED = "installed"
    ERROR = "error"


class Mod(SQLModel, table=True):
    """模组库存表 — 记录已知的模组及其安装状态。"""

    __tablename__ = "mods"

    id: int | None = Field(default=None, primary_key=True)
    # Nexus Mods 的 mod_id
    nexus_mod_id: int = Field(index=True, unique=True)
    name: str = ""
    version: str = ""
    author: str = ""
    description: str = ""
    # Nexus 文件 id（最近一次下载的文件）
    nexus_file_id: int | None = None
    file_name: str = ""
    # 本地下载文件路径（相对 downloads_dir）
    local_path: str = ""
    status: ModStatus = Field(default=ModStatus.NOT_INSTALLED, index=True)
    # 启用/禁用开关（独立于 status，避免与状态枚举重复表达"禁用"语义）
    enabled: bool = True
    installed_at: datetime | None = None
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
    # 依赖的框架，如 CET / redscript / RED4ext
    framework: str = ""
    # 缩略图 URL
    thumbnail_url: str = ""
    # 模组主页 URL
    mod_page_url: str = ""
    # 备注
    note: str = ""
