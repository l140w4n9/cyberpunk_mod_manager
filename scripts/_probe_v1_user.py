# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

V1 = "https://api.nexusmods.com/v1"


async def main() -> None:
    h = _build_headers(config.nexus_api_key)
    async with httpx.AsyncClient(timeout=60) as c:
        for path in (
            "/users/validate.json",
            f"/games/cyberpunk2077/mods/updated.json?period=1w",
            "/user/tracked_mods.json",
            "/users/tracked_mods.json",
        ):
            r = await c.get(f"{V1}{path}", headers=h)
            print(path, r.status_code, r.text[:400])


if __name__ == "__main__":
    asyncio.run(main())
