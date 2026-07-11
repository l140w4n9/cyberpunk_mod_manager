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
        r = await c.get(f"{V3}/games/{GAME_DOMAIN}/mods/18777")
        print("v3 mod", json.dumps(r.json(), indent=2)[:1500])
        r = await c.post(
            GQL,
            headers=gh,
            json={
                "query": """
                query($modId: ID!, $gameId: ID!) {
                  mod(modId: $modId, gameId: $gameId) {
                    name summary description author version pictureUrl
                    legacyModRequirementsEnabled
                  }
                }
                """,
                "variables": {"modId": "18777", "gameId": "3333"},
            },
        )
        print("gql mod", json.dumps(r.json(), indent=2)[:1500])


if __name__ == "__main__":
    asyncio.run(main())
