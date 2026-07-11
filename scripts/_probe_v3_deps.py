# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

V3 = "https://api.nexusmods.com/v3"


async def get(path: str) -> dict:
    headers = _build_headers(config.nexus_api_key)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{V3}{path}", headers=headers)
    print(path, r.status_code)
    if r.status_code >= 400:
        print(r.text[:500])
        return {}
    return r.json()


async def main() -> None:
    mod_id = 18777
    mod = await get(f"/games/{GAME_DOMAIN}/mods/{mod_id}")
    internal_id = mod.get("data", {}).get("id") if mod else None
    print("internal mod id", internal_id)

    for path in (
        f"/mods/{internal_id}/files" if internal_id else None,
        f"/mods/{mod_id}/files",
    ):
        if not path:
            continue
        files = await get(path)
        if not files:
            continue
        mod_files = files.get("data", {}).get("mod_files", [])
        print("mod_files", len(mod_files))
        primary = next((f for f in mod_files if f.get("is_primary")), mod_files[0] if mod_files else None)
        if not primary:
            continue
        print("primary", primary.get("id"), primary.get("name"))
        file_id = primary["id"]
        versions = await get(f"/mod-files/{file_id}/versions")
        vers = versions.get("data", {}).get("versions", [])
        print("versions", len(vers))
        if not vers:
            continue
        latest = max(vers, key=lambda v: v.get("uploaded_at", ""))
        print("latest", latest.get("id"), latest.get("version"), latest.get("category"))
        mat = await get(f"/mod-file-versions/{latest['id']}/dependencies/materialized")
        print(json.dumps(mat, indent=2, ensure_ascii=False)[:5000])
        break


if __name__ == "__main__":
    asyncio.run(main())
