# -*- coding: utf-8 -*-
"""Nexus Mods API 客户端（v3 REST + GraphQL，下载走遗留 v1 shim）。"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

import httpx

from ..config import config
from ._legacy_v1 import (
    _pick_download_link,
    download_from_cdn,
    fetch_download_links,
    get_tracked_mod_ids,
    get_updated_mods,
    validate_user,
)
from .schemas import (
    FilePin,
    MaterializedDependency,
    ModBatchInfo,
    ModDetails,
    ModFile,
    TrendingMod,
    UserProfile,
)

V3_BASE_URL = "https://api.nexusmods.com/v3"
GRAPHQL_URL = "https://api.nexusmods.com/v2/graphql"
GAME_DOMAIN = "cyberpunk2077"
PREFERRED_CDN = "nexus cdn"

_MOD_URL_RE = re.compile(r"/mods/(\d+)", re.IGNORECASE)

_game_id_cache: int | None = None


class NexusAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        is_premium_only: bool = False,
        code: str = "NEXUS_API_ERROR",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.is_premium_only = is_premium_only
        self.code = code


def _app_headers() -> dict[str, str]:
    return {
        "Application-Name": config.app_name,
        "Application-Version": "0.1.0",
        "User-Agent": f"{config.app_name}/0.1.0",
        "Accept": "application/json",
    }


async def build_nexus_headers() -> dict[str, str]:
    from .oauth import ensure_access_token

    token = await ensure_access_token()
    return {
        **_app_headers(),
        "Authorization": f"Bearer {token}",
    }


def _parse_problem_details(response: httpx.Response) -> dict[str, Any] | None:
    content_type = (response.headers.get("content-type") or "").lower()
    if "json" not in content_type and response.status_code not in {
        400,
        401,
        403,
        404,
        422,
    }:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_api_error(response: httpx.Response) -> NexusAPIError:
    problem = _parse_problem_details(response)
    detail = str((problem or {}).get("detail") or "").strip()
    title = str((problem or {}).get("title") or "").strip()
    body = response.text
    lower = (detail or body).lower()
    is_premium_only = (
        response.status_code == 403
        and "premium" in lower
        and ("download" in lower or "subscription" in lower)
    )
    if response.status_code == 401:
        message = detail or title or "Nexus 授权无效或已过期，请重新连接账户。"
        code = "NEXUS_UNAUTHORIZED"
    elif is_premium_only:
        message = (
            detail
            or title
            or "非 Premium 账户无法通过 API 获取下载链接，请在网站手动下载后放入 downloads 目录。"
        )
        code = "NEXUS_PREMIUM_REQUIRED"
    elif response.status_code == 403:
        message = detail or title or "Nexus API 拒绝访问该资源。"
        code = "NEXUS_FORBIDDEN"
    elif response.status_code == 404:
        message = detail or title or "Nexus 资源不存在。"
        code = "NEXUS_NOT_FOUND"
    elif response.status_code == 422:
        message = detail or title or "Nexus 请求参数无效。"
        code = "NEXUS_VALIDATION_ERROR"
    else:
        message = (
            detail
            or title
            or f"Nexus API HTTP {response.status_code}: {body or response.reason_phrase}"
        )
        code = "NEXUS_API_ERROR"
    return NexusAPIError(
        message,
        status_code=response.status_code,
        is_premium_only=is_premium_only,
        code=code,
    )


def composite_mod_uid(game_scoped_mod_id: int, game_id: int | None = None) -> str:
    gid = game_id if game_id is not None else (_game_id_cache or 3333)
    return str((int(gid) << 32) | int(game_scoped_mod_id))


def parse_mod_id_from_url(url: str) -> int:
    match = _MOD_URL_RE.search(url or "")
    return int(match.group(1)) if match else 0


def _version_to_mod_file(version: dict[str, Any]) -> ModFile:
    game_scoped = version.get("game_scoped_id")
    try:
        file_id = int(game_scoped)
    except (TypeError, ValueError):
        file_id = 0
    uploaded = version.get("uploaded_at") or ""
    uploaded_ts = None
    if uploaded:
        try:
            from datetime import datetime

            uploaded_ts = int(
                datetime.fromisoformat(uploaded.replace("Z", "+00:00")).timestamp()
            )
        except ValueError:
            uploaded_ts = None
    file_obj = version.get("file") or {}
    return ModFile(
        file_id=file_id,
        file_name=version.get("name") or file_obj.get("name"),
        version=version.get("version"),
        category_name=(version.get("category") or "").upper(),
        is_primary=bool(version.get("is_primary")),
        uploaded_timestamp=uploaded_ts,
        version_id=str(version.get("id") or ""),
        mod_file_id=str(file_obj.get("id") or ""),
        category=str(version.get("category") or ""),
        uploaded_at=str(uploaded),
        position=str(version.get("position") or ""),
    )


def _pick_latest_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not versions:
        return None
    active = [
        v
        for v in versions
        if (v.get("category") or "").lower()
        in {"main", "update", "optional", "miscellaneous"}
    ]
    pool = active or versions
    return max(pool, key=lambda v: (v.get("uploaded_at") or "", v.get("position") or ""))


def parse_materialized_dependencies(payload: dict[str, Any]) -> list[MaterializedDependency]:
    results: list[MaterializedDependency] = []
    for definition in payload.get("dependencies") or []:
        definition_id = str(definition.get("id") or "")
        for candidate in definition.get("candidate_mod_files") or []:
            mod = candidate.get("mod") or {}
            game_scoped = mod.get("game_scoped_id")
            if not game_scoped:
                continue
            try:
                mod_id = int(game_scoped)
            except (TypeError, ValueError):
                continue
            best = _pick_latest_version(candidate.get("candidate_versions") or [])
            results.append(
                MaterializedDependency(
                    definition_id=definition_id,
                    mod_id=mod_id,
                    name=str(mod.get("name") or "").strip(),
                    mod_file_id=str(candidate.get("id") or ""),
                    version_id=str(best.get("id") or "") if best else "",
                    version=str(best.get("version") or "") if best else "",
                )
            )
            break
    return results


class NexusClient:
    """Nexus Mods 统一客户端。"""

    def __init__(self) -> None:
        from .auth_store import has_nexus_tokens

        if not has_nexus_tokens():
            raise NexusAPIError(
                "未连接 Nexus 账户，请在设置页通过 OAuth 登录",
                code="NEXUS_NOT_CONNECTED",
                status_code=401,
            )
        self._client = httpx.AsyncClient(
            base_url=V3_BASE_URL,
            timeout=60.0,
            follow_redirects=True,
        )

    async def __aenter__(self) -> "NexusClient":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _headers(self) -> dict[str, str]:
        return await build_nexus_headers()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        headers = await self._headers()
        merged = dict(kwargs.pop("headers", {}) or {})
        merged.update(headers)
        response = await self._client.request(method, url, headers=merged, **kwargs)
        if response.status_code == 404:
            return response
        if response.is_error:
            raise _parse_api_error(response)
        return response

    async def _get_json(self, path: str) -> dict[str, Any]:
        response = await self._request("GET", path)
        if response.status_code == 404:
            return {}
        return response.json()

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", path, json=body)
        return response.json()

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        headers = await self._headers()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                GRAPHQL_URL,
                headers={**headers, "Content-Type": "application/json"},
                json={"query": query, "variables": variables or {}},
            )
        if response.is_error:
            raise NexusAPIError(
                f"Nexus GraphQL HTTP {response.status_code}: {response.text[:300]}"
            )
        body = response.json()
        if body.get("errors"):
            messages = "; ".join(
                err.get("message", str(err)) for err in body["errors"]
            )
            raise NexusAPIError(f"Nexus GraphQL 错误: {messages}")
        return body.get("data") or {}

    async def get_game_id(self) -> int:
        global _game_id_cache
        if _game_id_cache is not None:
            return _game_id_cache
        data = await self._graphql(
            "query($d: String!) { game(domainName: $d) { id } }",
            {"d": GAME_DOMAIN},
        )
        node = data.get("game") or {}
        _game_id_cache = int(node.get("id") or 3333)
        return _game_id_cache

    async def validate_auth(self) -> bool:
        try:
            profile = await self.get_user_profile()
            return profile is not None
        except Exception:
            return False

    async def get_user_profile(self) -> UserProfile | None:
        return await validate_user(await self._headers())

    async def resolve_mod_internal_id(self, game_scoped_mod_id: int) -> str:
        data = await self._get_json(f"/games/{GAME_DOMAIN}/mods/{game_scoped_mod_id}")
        return str((data.get("data") or {}).get("id") or "")

    async def get_mod_details(self, mod_id: int) -> ModDetails:
        game_id = await self.get_game_id()
        gql = await self._graphql(
            """
            query ModDetail($modId: ID!, $gameId: ID!) {
              mod(modId: $modId, gameId: $gameId) {
                name summary description author version pictureUrl
                legacyModRequirementsEnabled
              }
            }
            """,
            {"modId": str(mod_id), "gameId": str(game_id)},
        )
        node = gql.get("mod") or {}
        batch = await self.get_mods_batch([mod_id])
        batch_info = batch.get(mod_id)
        internal_id = await self.resolve_mod_internal_id(mod_id)
        return ModDetails(
            mod_id=mod_id,
            name=str(node.get("name") or batch_info.name if batch_info else ""),
            summary=str(node.get("summary") or batch_info.summary if batch_info else ""),
            description=str(node.get("description") or ""),
            author=str(node.get("author") or ""),
            version=str(node.get("version") or ""),
            picture_url=str(node.get("pictureUrl") or ""),
            mod_page_url=f"https://www.nexusmods.com/{GAME_DOMAIN}/mods/{mod_id}",
            internal_mod_id=internal_id,
            status=batch_info.status if batch_info else "",
            adult_content=batch_info.adult_content if batch_info else False,
            legacy_mod_requirements=bool(node.get("legacyModRequirementsEnabled", True)),
        )

    async def get_mods_batch(
        self, mod_ids: list[int]
    ) -> dict[int, ModBatchInfo]:
        if not mod_ids:
            return {}
        game_id = await self.get_game_id()
        payload = await self._post_json(
            "/mods/batch",
            {"mod_ids": [composite_mod_uid(mid, game_id) for mid in mod_ids]},
        )
        result: dict[int, ModBatchInfo] = {}
        for row in (payload.get("data") or {}).get("mods") or []:
            composite = str(row.get("id") or "")
            try:
                scoped = int(composite) & 0xFFFFFFFF
            except ValueError:
                scoped = parse_mod_id_from_url(str(row.get("mod_page_url") or ""))
            if not scoped:
                continue
            result[scoped] = ModBatchInfo(
                composite_id=composite,
                game_id=str(row.get("game_id") or game_id),
                mod_id=scoped,
                name=str(row.get("name") or ""),
                summary=str(row.get("summary") or ""),
                status=str(row.get("status") or ""),
                adult_content=bool(row.get("adult_content")),
                thumbnail_url=str(row.get("thumbnail_url") or ""),
            )
        return result

    async def get_trending_mods(self) -> list[TrendingMod]:
        data = await self._get_json(f"/games/{GAME_DOMAIN}/trending-mods")
        items: list[TrendingMod] = []
        for row in (data.get("data") or {}).get("mods") or []:
            url = str(row.get("mod_page_url") or "")
            items.append(
                TrendingMod(
                    name=str(row.get("name") or ""),
                    author=str(row.get("author") or ""),
                    summary=str(row.get("summary") or ""),
                    picture_url=str(row.get("picture_url") or ""),
                    mod_page_url=url,
                    mod_id=parse_mod_id_from_url(url),
                )
            )
        return items

    async def get_tracked_mod_ids(self) -> list[int]:
        return await get_tracked_mod_ids(GAME_DOMAIN, await self._headers())

    async def get_updated_mod_feed(self, *, period: str = "1w") -> list[dict[str, Any]]:
        return await get_updated_mods(GAME_DOMAIN, await self._headers(), period=period)

    async def get_mod_files_v3(self, internal_mod_id: str) -> list[dict[str, Any]]:
        data = await self._get_json(f"/mods/{internal_mod_id}/files")
        return (data.get("data") or {}).get("mod_files") or []

    async def get_mod_file_versions(self, mod_file_id: str) -> list[dict[str, Any]]:
        data = await self._get_json(f"/mod-files/{mod_file_id}/versions")
        return (data.get("data") or {}).get("versions") or []

    async def get_mod_file_version(self, version_id: str) -> dict[str, Any]:
        data = await self._get_json(f"/mod-file-versions/{version_id}")
        return data.get("data") or {}

    async def get_mod_file_versions_batch(
        self, version_ids: list[str]
    ) -> list[dict[str, Any]]:
        if not version_ids:
            return []
        data = await self._post_json(
            "/mod-file-versions/batch",
            {"version_ids": version_ids},
        )
        return (data.get("data") or {}).get("versions") or []

    async def get_materialized_dependencies(
        self, version_id: str
    ) -> list[MaterializedDependency]:
        data = await self._get_json(
            f"/mod-file-versions/{version_id}/dependencies/materialized"
        )
        return parse_materialized_dependencies(data)

    async def get_dependency_ranges(self, version_id: str) -> dict[str, Any]:
        """获取指定文件版本的依赖范围定义（v3）。"""
        return await self._get_json(
            f"/mod-file-versions/{version_id}/dependencies/ranges"
        )

    async def get_materialized_dependencies_batch(
        self, version_ids: list[str]
    ) -> dict[str, list[MaterializedDependency]]:
        if not version_ids:
            return {}
        grouped: dict[str, list[MaterializedDependency]] = {vid: [] for vid in version_ids}
        page = 1
        while True:
            data = await self._post_json(
                "/mod-file-versions/dependencies/materialized/batch",
                {
                    "version_ids": version_ids,
                    "page": page,
                    "page_size": 1000,
                },
            )
            candidates = (data.get("data") or {}).get("candidates") or []
            if not candidates:
                break
            for row in candidates:
                source = str(row.get("source_version_id") or "")
                try:
                    mod_id = int(row.get("mod_id") or 0)
                except (TypeError, ValueError):
                    continue
                if not mod_id:
                    continue
                grouped.setdefault(source, []).append(
                    MaterializedDependency(
                        definition_id=str(row.get("definition_id") or ""),
                        mod_id=mod_id,
                        name="",
                        mod_file_id=str(row.get("mod_file_id") or ""),
                        version_id=str(row.get("version_id") or ""),
                        version="",
                    )
                )
            meta = data.get("meta") or {}
            total = int(meta.get("total_count") or 0)
            page_size = int(meta.get("page_size") or 1000)
            if page * page_size >= total:
                break
            page += 1
        return grouped

    async def resolve_target_version(
        self,
        mod_id: int,
        *,
        pin: FilePin | None = None,
        version_id: str | None = None,
    ) -> ModFile | None:
        if pin and pin.version_id:
            version = await self.get_mod_file_version(pin.version_id)
            if version:
                mf = _version_to_mod_file(version)
                mf.internal_mod_id = await self.resolve_mod_internal_id(mod_id)
                return mf
        if version_id:
            version = await self.get_mod_file_version(version_id)
            if version:
                mf = _version_to_mod_file(version)
                mf.internal_mod_id = await self.resolve_mod_internal_id(mod_id)
                return mf
        if pin and pin.game_scoped_file_id:
            internal = await self.resolve_mod_internal_id(mod_id)
            if not internal:
                return None
            for mod_file in await self.get_mod_files_v3(internal):
                versions = await self.get_mod_file_versions(str(mod_file["id"]))
                for ver in versions:
                    mf = _version_to_mod_file(ver)
                    if mf.file_id == pin.game_scoped_file_id:
                        if pin.version_string and mf.version != pin.version_string:
                            continue
                        mf.internal_mod_id = internal
                        return mf
        internal = await self.resolve_mod_internal_id(mod_id)
        if not internal:
            return None
        from .file_selection import pick_install_versions

        details = await self.get_mod_details(mod_id)
        versions = await pick_install_versions(self, mod_id, details=details)
        return versions[0] if versions else None

    async def resolve_install_versions(
        self,
        mod_id: int,
        *,
        pin: FilePin | None = None,
    ) -> list[ModFile]:
        """挑选应下载安装的版本列表（支持多主文件）。"""
        if pin and (pin.version_id or pin.game_scoped_file_id):
            single = await self.resolve_target_version(mod_id, pin=pin)
            return [single] if single and single.file_id else []
        from .file_selection import pick_install_versions

        details = await self.get_mod_details(mod_id)
        return await pick_install_versions(self, mod_id, details=details)

    async def pick_primary_file(self, mod_id: int) -> Optional[ModFile]:
        return await self.resolve_target_version(mod_id)

    async def download_file(
        self,
        mod_id: int,
        file_id: int,
        dest_dir: Path,
        file_name: str | None = None,
    ) -> Path:
        links = await fetch_download_links(
            GAME_DOMAIN, mod_id, file_id, await self._headers()
        )
        link = _pick_download_link(links)
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / Path(file_name or f"{mod_id}_{file_id}.zip").name
        if dest.exists():
            dest.unlink()
        try:
            await download_from_cdn(link.URI, dest, await self._headers())
        except Exception:
            if dest.exists():
                dest.unlink()
            raise
        return dest


def select_download_file(files: list[ModFile], *, mod_name: str = "") -> ModFile | None:
    """兼容旧调用：从 ModFile 列表选主文件。"""
    from .file_selection import select_download_file as _select

    return _select(files, mod_name=mod_name)
