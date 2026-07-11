# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

V3 = "https://api.nexusmods.com/v3"
V1 = "https://api.nexusmods.com/v1"


async def main() -> None:
    h = _build_headers(config.nexus_api_key)
    version_id = "14315126125769"
    async with httpx.AsyncClient(timeout=60) as c:
        for url in (
            f"{V3}/mod-file-versions/{version_id}",
            f"{V3}/mod-file-versions/{version_id}/download",
            f"{V3}/mod-file-versions/{version_id}/download_link",
        ):
            r = await c.get(url, headers=h)
            print(url, r.status_code, r.text[:400])

        r = await c.get(
            f"{V1}/games/{GAME_DOMAIN}/mods/18777/files/128201/download_link.json",
            headers=h,
        )
        print("v1 download", r.status_code, r.text[:300])


if __name__ == "__main__":
    asyncio.run(main())
