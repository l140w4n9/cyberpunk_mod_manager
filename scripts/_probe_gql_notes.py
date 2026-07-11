# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

GQL = "https://api.nexusmods.com/v2/graphql"
QUERY = """
query($modId: ID!, $gameId: ID!) {
  mod(modId: $modId, gameId: $gameId) {
    legacyModRequirementsEnabled
    modRequirements {
      nexusRequirements { nodes { modId modName notes externalRequirement url } }
    }
  }
}
"""


async def main() -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            GQL,
            headers=headers,
            json={"query": QUERY, "variables": {"modId": "9617", "gameId": "3333"}},
        )
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
