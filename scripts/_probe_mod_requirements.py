# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"

QUERY = """
query ModReqs($modId: ID!, $gameId: ID!) {
  mod(modId: $modId, gameId: $gameId) {
    modId
    name
    legacyModRequirementsEnabled
    modRequirements {
      nexusRequirements {
        nodesCount
        nodes {
          modId
          modName
          notes
          externalRequirement
          url
        }
      }
    }
  }
}
"""


async def main() -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        games = await client.post(
            URL,
            headers=headers,
            json={"query": "query { games { nodes { id domainName name } } }"},
        )
        print("games", games.status_code, games.text[:500])
        r = await client.post(
            URL,
            headers=headers,
            json={
                "query": QUERY,
                "variables": {"modId": "18777", "gameId": "3333"},
            },
        )
    print(r.status_code)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
