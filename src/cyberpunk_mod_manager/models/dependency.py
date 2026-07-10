# -*- coding: utf-8 -*-
"""模组依赖关系表。"""
from __future__ import annotations

from sqlmodel import SQLModel, Field


class ModDependency(SQLModel, table=True):
    """模组依赖 — 记录某模组需要的前置模组。"""

    __tablename__ = "mod_dependencies"

    id: int | None = Field(default=None, primary_key=True)
    # 所属模组（mods 表主键）
    owner_mod_id: int = Field(foreign_key="mods.id", index=True)
    # 依赖的 Nexus mod_id
    dep_nexus_mod_id: int = Field(index=True)
    dep_name: str = ""
    # parsed: 从描述解析 | known: 内置库 | manual: 用户添加
    source: str = "parsed"
