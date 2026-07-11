# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import GAME_DOMAIN, _build_headers

GQL = "https://api.nexusmods.com/v2/graphql"


async def main() -> None:
    gh = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(
            GQL,
            headers=gh,
            json={
                "query": """
                query($slug: String!, $domain: String!) {
                  collectionRevision(slug: $slug, domainName: $domain) {
                    revisionNumber
                    modFiles { optional file { fileId uid name version mod { modId name } } }
                  }
                }
                """,
                "variables": {"slug": "iszwwe", "domain": "cyberpunk2077"},
            },
        )
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    asyncio.run(main())
