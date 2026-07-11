# -*- coding: utf-8 -*-
"""Nexus Mods API 数据结构（v3 + GraphQL）。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel


class ModFile(BaseModel):
    """待下载文件（game_scoped file id 用于遗留下载端点）。"""

    file_id: int
    file_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    category_name: Optional[str] = None
    category_id: Optional[int] = None
    size: Optional[int] = None
    is_primary: bool = False
    uploaded_timestamp: Optional[int] = None
    # v3 扩展
    version_id: str = ""
    mod_file_id: str = ""
    internal_mod_id: str = ""
    category: str = ""
    uploaded_at: str = ""
    position: str = ""


class DownloadLink(BaseModel):
    URI: str
    name: Optional[str] = None
    short_name: Optional[str] = None
    size: Optional[int] = None


class ModDetails(BaseModel):
    mod_id: int
    name: str = ""
    summary: str = ""
    description: str = ""
    author: str = ""
    version: str = ""
    picture_url: str = ""
    mod_page_url: str = ""
    category_id: int = 0
    endorsement_count: int = 0
    # v3 / GraphQL 扩展
    internal_mod_id: str = ""
    status: str = ""
    adult_content: bool = False
    legacy_mod_requirements: bool = True


class UserProfile(BaseModel):
    user_id: int = 0
    name: str = ""
    is_premium: bool = False
    is_supporter: bool = False
    email: str = ""
    profile_url: str = ""


class ModBatchInfo(BaseModel):
    composite_id: str = ""
    game_id: str = ""
    mod_id: int = 0
    name: str = ""
    summary: str = ""
    status: str = ""
    adult_content: bool = False
    thumbnail_url: str = ""


class TrendingMod(BaseModel):
    name: str = ""
    author: str = ""
    summary: str = ""
    picture_url: str = ""
    mod_page_url: str = ""
    mod_id: int = 0


@dataclass
class FilePin:
    """安装时固定的文件版本（收藏夹 / 用户指定）。"""

    version_id: str = ""
    game_scoped_file_id: int = 0
    version_string: str = ""
    file_name: str = ""


@dataclass
class MaterializedDependency:
    definition_id: str
    mod_id: int
    name: str
    mod_file_id: str = ""
    version_id: str = ""
    version: str = ""
    optional: bool = False
