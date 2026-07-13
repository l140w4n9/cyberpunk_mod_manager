# -*- coding: utf-8 -*-
"""Nexus Mods Collection（收藏夹）解析与 GraphQL 查询。"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from .client import GAME_DOMAIN, NexusAPIError, build_nexus_headers

GRAPHQL_URL = "https://api.nexusmods.com/v2/graphql"

_COLLECTION_URL_RE = re.compile(
    r"nexusmods\.com/games/(?P<domain>[^/]+)/collections/(?P<slug>[^/?#]+)",
    re.IGNORECASE,
)

COLLECTION_REVISION_QUERY = """
query CollectionRevision($slug: String!, $domainName: String!) {
  collection(slug: $slug, domainName: $domainName) {
    name
    slug
  }
  collectionRevision(slug: $slug, domainName: $domainName) {
    revisionNumber
    modCount
    modFiles {
      optional
      file {
        fileId
        uid
        name
        version
        mod {
          modId
          name
        }
      }
    }
  }
}
"""


@dataclass
class ParsedCollectionUrl:
    domain: str
    slug: str
    source_url: str


@dataclass
class CollectionModEntry:
    mod_id: int
    name: str
    order: int
    optional: bool
    collection_file_name: str = ""
    collection_file_version: str = ""
    collection_file_id: int = 0
    collection_version_id: str = ""


@dataclass
class CollectionInfo:
    title: str
    slug: str
    domain: str
    revision_number: int
    mod_count: int
    url: str
    mods: list[CollectionModEntry]


class CollectionParseError(ValueError):
    """Collection URL 或数据解析失败。"""


def parse_collection_url(url: str) -> ParsedCollectionUrl:
    """从 Nexus Collection 页面 URL 解析 slug 与游戏域。"""
    text = (url or "").strip()
    if not text:
        raise CollectionParseError("请提供收藏夹 URL")
    if not text.startswith(("http://", "https://")):
        text = "https://" + text.lstrip("/")
    match = _COLLECTION_URL_RE.search(text)
    if not match:
        raise CollectionParseError(
            "无法识别收藏夹 URL，示例："
            "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
        )
    domain = match.group("domain").lower()
    slug = match.group("slug").lower()
    if domain != GAME_DOMAIN:
        raise CollectionParseError(
            f"当前仅支持 {GAME_DOMAIN}，该链接属于 {domain}"
        )
    return ParsedCollectionUrl(domain=domain, slug=slug, source_url=text)


async def fetch_collection(slug: str, domain: str = GAME_DOMAIN) -> CollectionInfo:
    """通过 Nexus GraphQL 拉取收藏夹模组列表（按收藏夹顺序）。"""
    try:
        return await asyncio.wait_for(
            _fetch_collection_impl(slug, domain),
            timeout=60.0,
        )
    except asyncio.TimeoutError as exc:
        raise CollectionParseError(
            "请求 Nexus 收藏夹超时（60s），请检查网络或稍后重试"
        ) from exc


async def _fetch_collection_impl(slug: str, domain: str) -> CollectionInfo:
    headers = {
        **await build_nexus_headers(),
        "Content-Type": "application/json",
    }
    payload = {
        "query": COLLECTION_REVISION_QUERY,
        "variables": {"slug": slug, "domainName": domain},
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(GRAPHQL_URL, headers=headers, json=payload)
    if response.is_error:
        raise NexusAPIError(
            f"Nexus GraphQL HTTP {response.status_code}: {response.text[:300]}"
        )
    body = response.json()
    if body.get("errors"):
        messages = "; ".join(
            err.get("message", str(err)) for err in body["errors"]
        )
        raise CollectionParseError(f"Nexus GraphQL 错误: {messages}")

    data: dict[str, Any] = body.get("data") or {}
    collection = data.get("collection") or {}
    revision = data.get("collectionRevision")
    if not collection or revision is None:
        raise CollectionParseError("未找到该收藏夹，请检查链接或 Nexus 账户权限")

    seen: set[int] = set()
    mods: list[CollectionModEntry] = []
    order = 0
    for item in revision.get("modFiles") or []:
        file_obj = item.get("file") or {}
        mod_obj = file_obj.get("mod") or {}
        mod_id = int(mod_obj.get("modId") or 0)
        if mod_id <= 0 or mod_id in seen:
            continue
        seen.add(mod_id)
        order += 1
        mods.append(
            CollectionModEntry(
                mod_id=mod_id,
                name=str(mod_obj.get("name") or file_obj.get("name") or ""),
                order=order,
                optional=bool(item.get("optional")),
                collection_file_name=str(file_obj.get("name") or ""),
                collection_file_version=str(file_obj.get("version") or ""),
                collection_file_id=int(file_obj.get("fileId") or 0),
                collection_version_id=str(file_obj.get("uid") or ""),
            )
        )

    page_url = (
        f"https://www.nexusmods.com/games/{domain}/collections/{slug}/mods"
    )
    return CollectionInfo(
        title=str(collection.get("name") or slug),
        slug=str(collection.get("slug") or slug),
        domain=domain,
        revision_number=int(revision.get("revisionNumber") or 0),
        mod_count=int(revision.get("modCount") or len(mods)),
        url=page_url,
        mods=mods,
    )
