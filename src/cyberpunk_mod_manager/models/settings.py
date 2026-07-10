# -*- coding: utf-8 -*-
"""键值配置表，用于持久化游戏路径、API Key 等。"""
from __future__ import annotations

from sqlmodel import SQLModel, Field


class Setting(SQLModel, table=True):
    __tablename__ = "settings"

    key: str = Field(primary_key=True)
    value: str = ""
