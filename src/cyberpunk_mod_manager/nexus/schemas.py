# -*- coding: utf-8 -*-
"""Nexus Mods API 数据结构。"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class ModFile(BaseModel):
    """Nexus 模组文件（参考 Stardrop Models/Nexus/Web/ModFile.cs）。"""

    file_id: int
    file_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    category_name: Optional[str] = None
    category_id: Optional[int] = None
    size: Optional[int] = None
    is_primary: bool = False
    uploaded_timestamp: Optional[int] = None


class ModFilesResponse(BaseModel):
    files: list[ModFile] = []


class DownloadLink(BaseModel):
    """Nexus 下载链接条目。"""

    URI: str
    name: Optional[str] = None
    short_name: Optional[str] = None
    size: Optional[int] = None


class ModDetails(BaseModel):
    """模组详情。"""

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
