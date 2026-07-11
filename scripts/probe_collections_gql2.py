# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def gql(query: str) -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query})
        print(json.dumps(r.json(), ensure_ascii=False, indent=2)[:8000])


async def main() -> None:
    for type_name in ["CollectionRevision", "CollectionRevisionMod", "CollectionRevisionModReference", "Mod"]:
        print("=== TYPE", type_name, "===")
        await gql(f"""
        query {{
          __type(name: "{type_name}") {{
            fields {{ name type {{ kind name ofType {{ kind name ofType {{ kind name }} }} }} }}
          }}
        }}
        """)

    print("=== QUERY collection ===")
    await gql("""
    query {
      collection(slug: "iszwwe", gameDomainName: "cyberpunk2077") {
        name
        slug
        collectionStatus
        currentRevision {
          revisionNumber
          revisionStatus
          modCount
          collectionRevisionMods {
            modId
            optional
            name
            mod { name modId }
          }
        }
        latestPublishedRevision {
          revisionNumber
          modCount
          collectionRevisionMods {
            modId
            optional
            name
          }
        }
      }
    }
    """)


if __name__ == "__main__":
    asyncio.run(main())
