# -*- coding: utf-8 -*-
"""Nexus Mods API 客户端。

参考 Stardrop `Utilities/External/NexusClient.cs` 的实现模式：
- 使用 API Key 认证（API 与 CDN 下载均携带相同请求头）
- 通过 mod_id 查询模组详情与文件列表
- 获取下载链接并下载文件
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import aiofiles
import httpx

from ..config import config
from .schemas import ModDetails, ModFile, ModFilesResponse, DownloadLink

BASE_URL = "https://api.nexusmods.com/v1"
GAME_DOMAIN = "cyberpunk2077"
PREFERRED_CDN = "nexus cdn"


class NexusAPIError(RuntimeError):
    """Nexus API 请求失败。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        is_premium_only: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_premium_only = is_premium_only


def _build_headers(api_key: str) -> dict[str, str]:
    """构建 Nexus API 请求头。

    注意：不可同时发送 apikey 与 apiKey，Nexus 会因此返回 401。
    """
    return {
        "apikey": api_key,
        "Application-Name": config.app_name,
        "Application-Version": "0.1.0",
        "User-Agent": f"{config.app_name}/0.1.0",
        "Accept": "application/json",
    }


def _parse_api_error(response: httpx.Response) -> NexusAPIError:
    """将 HTTP 错误转为可读异常。"""
    body = response.text
    lower = body.lower()
    is_premium_only = (
        response.status_code == 403
        and "premium" in lower
        and "download" in lower
    )
    if response.status_code == 401:
        message = (
            "Nexus API 401：API Key 无效或未正确配置。"
            "请在 config.yaml 设置 nexus_api_key，或检查密钥是否已过期。"
        )
    elif is_premium_only:
        message = (
            "Nexus API 拒绝下载：非 Premium 账户无法通过 API 获取下载链接。"
            "请在 Nexus 网站手动下载后，将压缩包放入下载目录再安装。"
        )
    elif response.status_code == 403:
        message = f"Nexus API 403 Forbidden: {body or response.reason_phrase}"
    else:
        message = f"Nexus API HTTP {response.status_code}: {body or response.reason_phrase}"
    return NexusAPIError(
        message,
        status_code=response.status_code,
        is_premium_only=is_premium_only,
    )


def _pick_download_link(links: list[DownloadLink]) -> DownloadLink:
    """优先选择 Nexus CDN 下载链接。"""
    if not links:
        raise NexusAPIError("Nexus API 未返回可用下载链接")
    for link in links:
        name = (link.short_name or link.name or "").lower()
        if name == PREFERRED_CDN:
            return link
    return links[0]


class NexusClient:
    """Nexus Mods API 客户端。"""

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key or config.nexus_api_key
        if not self.api_key:
            raise NexusAPIError(
                "未配置 nexus_api_key，请在 config.yaml 或环境变量 NEXUS_API_KEY 中设置"
            )
        self._headers = _build_headers(self.api_key)
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=self._headers,
            timeout=60.0,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "NexusClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self._client.aclose()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        response = await self._client.request(method, url, **kwargs)
        if response.is_error:
            raise _parse_api_error(response)
        return response

    async def validate_key(self) -> bool:
        """校验 API Key 是否有效。

        仅当返回 401（密钥确实无效）时返回 ``False``；
        5xx 服务器错误或 429 限流等瞬态错误会重新抛出，
        避免误导用户以为密钥无效。
        """
        try:
            await self._request("GET", "/users/validate.json")
            return True
        except NexusAPIError as exc:
            if exc.status_code == 401:
                return False
            raise

    async def get_mod_details(self, mod_id: int) -> ModDetails:
        """获取模组详情。"""
        resp = await self._request(
            "GET",
            f"/games/{GAME_DOMAIN}/mods/{mod_id}.json",
        )
        data = resp.json()
        return ModDetails(
            mod_id=data.get("mod_id", mod_id),
            name=data.get("name", ""),
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            version=data.get("version", ""),
            picture_url=data.get("picture_url", ""),
            mod_page_url=(
                f"https://www.nexusmods.com/{GAME_DOMAIN}/mods/{mod_id}"
            ),
            category_id=data.get("category_id", 0),
            endorsement_count=data.get("endorsement_count", 0),
        )

    async def get_mod_files(self, mod_id: int) -> list[ModFile]:
        """获取模组的文件列表。"""
        resp = await self._request(
            "GET",
            f"/games/{GAME_DOMAIN}/mods/{mod_id}/files.json",
        )
        parsed = ModFilesResponse(**resp.json())
        return parsed.files

    async def pick_primary_file(self, mod_id: int) -> Optional[ModFile]:
        """选择主文件（优先 is_primary，否则取第一个文件）。"""
        files = await self.get_mod_files(mod_id)
        if not files:
            return None
        for f in files:
            if f.is_primary:
                return f
        return files[0]

    async def get_download_links(
        self, mod_id: int, file_id: int
    ) -> list[DownloadLink]:
        """获取指定文件的下载链接。"""
        resp = await self._request(
            "GET",
            f"/games/{GAME_DOMAIN}/mods/{mod_id}/files/{file_id}/download_link.json",
        )
        data = resp.json()
        return [DownloadLink(**item) for item in data]

    async def download_file(
        self, mod_id: int, file_id: int, dest_dir: Path,
        file_name: str | None = None,
    ) -> Path:
        """下载模组文件到 dest_dir，返回本地文件路径。

        若调用方已知 ``file_name``（例如来自 ``pick_primary_file``），
        可直接传入以避免一次多余的 ``get_mod_files`` 请求，节省 API 配额。
        """
        links = await self.get_download_links(mod_id, file_id)
        link = _pick_download_link(links)
        url = link.URI
        if not file_name:
            files = await self.get_mod_files(mod_id)
            file_name = next(
                (f.file_name for f in files if f.file_id == file_id),
                f"{mod_id}_{file_id}.zip",
            )
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(file_name or f"{mod_id}_{file_id}.zip").name
        if dest.exists():
            dest.unlink()

        # 与 Stardrop 一致：CDN 下载也使用带 apiKey 的同一客户端
        try:
            async with self._client.stream("GET", url) as response:
                if response.is_error:
                    # 流式响应体尚未读取，需先 aread() 才能访问 response.text
                    await response.aread()
                    raise _parse_api_error(response)
                async with aiofiles.open(dest, "wb") as fh:
                    async for chunk in response.aiter_bytes():
                        await fh.write(chunk)
        except Exception:
            # 下载中途失败时删除残留的半成品文件，防止后续误用
            if dest.exists():
                dest.unlink()
            raise
        return dest
