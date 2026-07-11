# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def main() -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    query = """
    query {
      __type(name: "CollectionRevisionMod") {
        fields { name type { kind name ofType { kind name ofType { kind name } } } }
      }
    }
    """
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query})
        print(json.dumps(r.json(), indent=2))

    query2 = """
    query {
      collectionRevision(slug: "iszwwe", domainName: "cyberpunk2077") {
        revisionNumber
        modCount
        modFiles {
          optional
          mod { modId name }
          file { fileId name version }
        }
      }
    }
    """
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query2})
        text = json.dumps(r.json(), ensure_ascii=False, indent=2)
        print(text[:10000])


if __name__ == "__main__":
    asyncio.run(main())
