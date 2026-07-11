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
    for type_name in ["CollectionRevisionModFile", "CollectionModFile", "ModFile"]:
        data = await gql(f"""
        query {{ __type(name: "{type_name}") {{
          fields {{ name type {{ kind name ofType {{ kind name }} }} }}
        }} }}
        """)
        print("TYPE", type_name, json.dumps(data, indent=2)[:3000])

    data = await gql("""
    query {
      collection(slug: "iszwwe", domainName: "cyberpunk2077") {
        name
        slug
        currentRevision { revisionNumber modCount }
        latestPublishedRevision { revisionNumber modCount }
      }
      collectionRevision(slug: "iszwwe", domainName: "cyberpunk2077") {
        revisionNumber
        modCount
        modFiles {
          modId
          optional
          fileId
          mod { modId name }
        }
      }
    }
    """)
    print(json.dumps(data, ensure_ascii=False, indent=2)[:12000])


if __name__ == "__main__":
    asyncio.run(main())
