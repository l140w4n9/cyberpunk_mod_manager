# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def gql(query: str, variables: dict | None = None) -> dict:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query, "variables": variables or {}})
        print("status", r.status_code)
        data = r.json()
        print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
        return data


async def main() -> None:
    await gql("""
    query {
      __type(name: "Collection") {
        name
        fields { name type { kind name ofType { kind name ofType { kind name } } } }
      }
    }
    """)

    await gql("""
    query {
      collection(slug: "iszwwe", domainName: "cyberpunk2077") {
        name
        slug
        domainName
        collectionStatus
        overallRating
        revision { revisionNumber mods { modId optional name } }
        currentRevision { revisionNumber mods { modId optional name } }
        latestPublishedRevision { revisionNumber mods { modId optional name } }
      }
    }
    """)


if __name__ == "__main__":
    asyncio.run(main())
