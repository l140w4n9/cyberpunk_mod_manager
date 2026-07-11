# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

V3 = "https://api.nexusmods.com/v3"
GQL = "https://api.nexusmods.com/v2/graphql"


async def main() -> None:
    h = _build_headers(config.nexus_api_key)
    gh = {**h, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{V3}/games/{GAME_DOMAIN}/trending-mods")
        print("trending", r.status_code, r.text[:800])

        # mods batch - composite uid = (gameId << 32) | modId
        uid = str((3333 << 32) | 18777)
        r = await c.post(f"{V3}/mods/batch", headers=h, json={"mod_ids": [uid, str((3333 << 32) | 999999)]})
        print("batch", r.status_code, r.text[:800])

        version_id = "14315126125769"
        r = await c.post(
            f"{V3}/mod-file-versions/dependencies/materialized/batch",
            headers=h,
            json={"version_ids": [version_id], "page": 1, "page_size": 100},
        )
        print("dep batch", r.status_code, r.text[:500])

        r = await c.post(
            f"{V3}/mod-file-versions/batch",
            headers=h,
            json={"version_ids": [version_id]},
        )
        print("ver batch", r.status_code, r.text[:500])

        r = await c.post(
            GQL,
            headers=gh,
            json={"query": "query { user { name isPremium memberId } }"},
        )
        print("gql user", r.text[:500])


if __name__ == "__main__":
    asyncio.run(main())
