# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def gql(query: str, variables: dict | None = None) -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query, "variables": variables or {}})
    print(r.status_code)
    print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:3000])


async def main() -> None:
    await gql(
        """
        query {
          games(filter: {domainName: {eq: "cyberpunk2077"}}) {
            nodes { id domainName name }
          }
        }
        """
    )
    await gql(
        """
        query {
          game(domainName: "cyberpunk2077") { id domainName name }
        }
        """
    )


if __name__ == "__main__":
    asyncio.run(main())
