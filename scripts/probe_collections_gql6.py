# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers

URL = "https://api.nexusmods.com/v2/graphql"


async def main() -> None:
    headers = {**_build_headers(config.nexus_api_key), "Content-Type": "application/json"}
    for type_name in ["ModFile", "Mod"]:
        q = f'query {{ __type(name: "{type_name}") {{ fields {{ name }} }} }}'
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(URL, headers=headers, json={"query": q})
            fields = [f["name"] for f in r.json()["data"]["__type"]["fields"]]
            print(type_name, fields)

    query = """
    query {
      collection(slug: "iszwwe", domainName: "cyberpunk2077") {
        name
        slug
      }
      collectionRevision(slug: "iszwwe", domainName: "cyberpunk2077") {
        revisionNumber
        modCount
        modFiles {
          optional
          fileId
          version
          updatePolicy
          file { fileId name version mod { modId name } }
        }
      }
    }
    """
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(URL, headers=headers, json={"query": query})
        data = r.json()
        print(json.dumps(data, ensure_ascii=False, indent=2)[:12000])
        if "data" in data and data["data"].get("collectionRevision"):
            mods = data["data"]["collectionRevision"].get("modFiles") or []
            print("count", len(mods))


if __name__ == "__main__":
    asyncio.run(main())
