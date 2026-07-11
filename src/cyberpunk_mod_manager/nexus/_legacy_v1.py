# -*- coding: utf-8 -*-
"""Nexus 尚未提供 v3 等效的极少数遗留 v1 接口。

仅用于：Premium 下载链接、API Key 校验、追踪列表、近期更新 feed。
其余能力一律走 v3 REST 或 GraphQL。
"""
from __future__ import annotations

from typing import Any

import aiofiles
import httpx

from ..config import config
from .schemas import DownloadLink, UserProfile

LEGACY_V1_BASE = "https://api.nexusmods.com/v1"
PREFERRED_CDN = "nexus cdn"


def _pick_download_link(links: list[DownloadLink]) -> DownloadLink:
    if not links:
        raise RuntimeError("Nexus 未返回可用下载链接")
    for link in links:
        name = (link.short_name or link.name or "").lower()
        if name == PREFERRED_CDN:
            return link
    return links[0]


async def validate_user(api_key: str, headers: dict[str, str]) -> UserProfile | None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{LEGACY_V1_BASE}/users/validate.json",
            headers=headers,
        )
    if response.status_code == 401:
        return None
    if response.is_error:
        response.raise_for_status()
    data = response.json()
    return UserProfile(
        user_id=int(data.get("user_id") or 0),
        name=str(data.get("name") or ""),
        is_premium=bool(data.get("is_premium") or data.get("is_premium?")),
        is_supporter=bool(data.get("is_supporter") or data.get("is_supporter?")),
        email=str(data.get("email") or ""),
        profile_url=str(data.get("profile_url") or ""),
    )


async def fetch_download_links(
    game_domain: str,
    mod_id: int,
    game_scoped_file_id: int,
    headers: dict[str, str],
) -> list[DownloadLink]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{LEGACY_V1_BASE}/games/{game_domain}/mods/{mod_id}/files/"
            f"{game_scoped_file_id}/download_link.json",
            headers=headers,
        )
    if response.is_error:
        body = response.text
        lower = body.lower()
        is_premium_only = (
            response.status_code == 403
            and "premium" in lower
            and "download" in lower
        )
        from .client import NexusAPIError

        if response.status_code == 401:
            message = "Nexus API 401：API Key 无效"
        elif is_premium_only:
            message = (
                "Nexus API 拒绝下载：非 Premium 账户无法通过 API 获取下载链接。"
            )
        else:
            message = f"Nexus API HTTP {response.status_code}: {body[:300]}"
        raise NexusAPIError(
            message,
            status_code=response.status_code,
            is_premium_only=is_premium_only,
        )
    return [DownloadLink(**item) for item in response.json()]


async def download_from_cdn(
    url: str,
    dest_path,
    headers: dict[str, str],
) -> None:
    async with httpx.AsyncClient(
        timeout=120.0,
        follow_redirects=True,
        headers=headers,
    ) as client:
        async with client.stream("GET", url) as response:
            if response.is_error:
                await response.aread()
                response.raise_for_status()
            async with aiofiles.open(dest_path, "wb") as fh:
                async for chunk in response.aiter_bytes():
                    await fh.write(chunk)


async def get_tracked_mod_ids(
    game_domain: str,
    headers: dict[str, str],
) -> list[int]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{LEGACY_V1_BASE}/user/tracked_mods.json",
            headers=headers,
        )
    if response.is_error:
        return []
    ids: list[int] = []
    for item in response.json():
        if (item.get("domain_name") or "").lower() != game_domain.lower():
            continue
        try:
            ids.append(int(item.get("mod_id")))
        except (TypeError, ValueError):
            continue
    return ids


async def get_updated_mods(
    game_domain: str,
    headers: dict[str, str],
    *,
    period: str = "1w",
) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{LEGACY_V1_BASE}/games/{game_domain}/mods/updated.json",
            headers=headers,
            params={"period": period},
        )
    if response.is_error:
        return []
    return list(response.json())
