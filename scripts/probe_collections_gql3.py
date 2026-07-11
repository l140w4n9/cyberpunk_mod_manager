# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def gql(query: str) -> dict:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query})
        return r.json()


async def main() -> None:
    data = await gql("""
    query {
      __schema {
        queryType {
          fields {
            name
            args { name type { kind name ofType { kind name ofType { kind name } } } }
          }
        }
      }
    }
    """)
    for field in data["data"]["__schema"]["queryType"]["fields"]:
        if "collection" in field["name"].lower():
            print(json.dumps(field, indent=2))

    rev = await gql("""
    query { __type(name: "CollectionRevision") {
      fields { name type { kind name ofType { kind name ofType { kind name } } } }
    }}
    """)
    print("CollectionRevision fields:")
    for f in rev["data"]["__type"]["fields"]:
        print(f["name"], "->", f["type"]["name"] or f["type"]["ofType"])


if __name__ == "__main__":
    asyncio.run(main())
