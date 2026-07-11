# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

V3 = "https://api.nexusmods.com/v3"
GQL = "https://api.nexusmods.com/v2/graphql"


async def v3_get(path: str) -> dict:
    headers = _build_headers(config.nexus_api_key)
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.get(f"{V3}{path}", headers=headers)
    return r.json() if r.status_code < 400 else {}


async def materialized_for_mod(mod_id: int) -> dict:
    mod = await v3_get(f"/games/{GAME_DOMAIN}/mods/{mod_id}")
    internal = mod.get("data", {}).get("id")
    if not internal:
        return {"mod_id": mod_id, "error": "no internal id"}
    files = await v3_get(f"/mods/{internal}/files")
    mod_files = files.get("data", {}).get("mod_files", [])
    if not mod_files:
        return {"mod_id": mod_id, "error": "no files"}
    primary = next((f for f in mod_files if f.get("is_primary")), mod_files[0])
    vers = (await v3_get(f"/mod-files/{primary['id']}/versions")).get("data", {}).get("versions", [])
    if not vers:
        return {"mod_id": mod_id, "error": "no versions"}
    latest = max(vers, key=lambda v: v.get("uploaded_at", ""))
    mat = await v3_get(f"/mod-file-versions/{latest['id']}/dependencies/materialized")
    return {
        "mod_id": mod_id,
        "version_id": latest["id"],
        "version": latest.get("version"),
        "materialized_count": len(mat.get("dependencies", [])),
        "materialized": mat,
    }


async def gql_legacy(mod_id: int) -> list:
    from cyberpunk_mod_manager.nexus.dependencies import fetch_nexus_mod_requirements

    return await fetch_nexus_mod_requirements(mod_id)


async def main() -> None:
    ids = [18777, 27967, 9617, 23032, 21422]
    for mid in ids:
        mat = await materialized_for_mod(mid)
        legacy = await gql_legacy(mid)
        print(f"\n#{mid}")
        print("  materialized defs:", mat.get("materialized_count"), mat.get("error", ""))
        if mat.get("materialized_count"):
            for dep in mat["materialized"].get("dependencies", []):
                for cand in dep.get("candidate_mod_files", []):
                    m = cand.get("mod", {})
                    print(
                        "   -",
                        m.get("game_scoped_id") or m.get("id"),
                        m.get("name"),
                        "candidates",
                        len(cand.get("candidate_versions", [])),
                    )
        print("  legacy gql:", [(d["mod_id"], d.get("name")) for d in legacy])


if __name__ == "__main__":
    asyncio.run(main())
