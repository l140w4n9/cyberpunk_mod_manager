# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.client import NexusClient


async def main() -> None:
    slug = "iszwwe"
    paths = [
        f"/games/cyberpunk2077/collections/{slug}.json",
        f"/games/cyberpunk2077/collections/{slug}/mods.json",
        f"/games/cyberpunk2077/collections/slug/{slug}.json",
        f"/games/cyberpunk2077/collections/slug/{slug}/mods.json",
    ]
    async with NexusClient() as client:
        for path in paths:
            try:
                resp = await client._request("GET", path)
                data = resp.json()
                print("OK", path)
                if isinstance(data, dict):
                    print(" keys:", list(data.keys())[:15])
                    for key, value in data.items():
                        if isinstance(value, list) and value:
                            print("  list", key, "len", len(value), "sample keys", list(value[0].keys())[:10] if isinstance(value[0], dict) else value[0])
                elif isinstance(data, list):
                    print(" list len", len(data))
                    if data:
                        print(" sample", data[0])
            except Exception as exc:
                print("FAIL", path, exc)


if __name__ == "__main__":
    asyncio.run(main())
