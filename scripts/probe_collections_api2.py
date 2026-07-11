# -*- coding: utf-8 -*-
import asyncio
import json

import httpx

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.nexus.client import _build_headers


async def main() -> None:
    slug = "iszwwe"
    headers = _build_headers(config.nexus_api_key)
    queries = [
        (
            "https://api.nexusmods.com/v2/graphql",
            {
                "query": """
                query CollectionMods($slug: String!, $domain: String!) {
                  collection(slug: $slug, domainName: $domain) {
                    name
                    slug
                    modCount
                    mods { modId name optional }
                  }
                }
                """,
                "variables": {"slug": slug, "domain": "cyberpunk2077"},
            },
        ),
        (
            "https://graphql.nexusmods.com/graphql",
            {
                "query": """
                query { collection(slug: "iszwwe", domainName: "cyberpunk2077") { name mods { modId } } }
                """
            },
        ),
    ]
    extra_paths = [
        "https://api.nexusmods.com/v1/games/cyberpunk2077/collections.json",
        f"https://api.nexusmods.com/v1/games/cyberpunk2077/collections/{slug}/revision/latest/mods.json",
        f"https://api.nexusmods.com/v1/games/cyberpunk2077/collection/{slug}.json",
    ]
    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        for url, body in queries:
            try:
                r = await client.post(url, headers={**headers, "Content-Type": "application/json"}, json=body)
                print("GQL", url, r.status_code, r.text[:500])
            except Exception as exc:
                print("GQL FAIL", url, exc)
        for url in extra_paths:
            try:
                r = await client.get(url, headers=headers)
                print("GET", url, r.status_code, r.text[:500])
            except Exception as exc:
                print("GET FAIL", url, exc)


if __name__ == "__main__":
    asyncio.run(main())
