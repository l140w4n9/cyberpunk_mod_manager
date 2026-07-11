# -*- coding: utf-8 -*-
import asyncio
import json

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import (
    collect_dependencies,
    fetch_materialized_mod_dependencies,
    fetch_nexus_mod_requirements,
)


async def inspect_mod(mod_id: int) -> None:
    async with NexusClient() as client:
        resp = await client._request(
            "GET", f"/games/cyberpunk2077/mods/{mod_id}.json"
        )
        raw = resp.json()
        details = await client.get_mod_details(mod_id)
        files = await client.get_mod_files(mod_id)

    materialized = await fetch_materialized_mod_dependencies(mod_id)
    graphql = await fetch_nexus_mod_requirements(mod_id)
    collected = await collect_dependencies(mod_id)

    print(f"=== mod {mod_id}: {details.name} ===")
    print("materialized:", [d["mod_id"] for d in materialized])
    print("graphql:", [d["mod_id"] for d in graphql])
    print("collect_dependencies:", [d["mod_id"] for d in collected])
    print("raw keys:", sorted(raw.keys()))
    for key in ("requirements", "dependencies", "nexus_requirements"):
        if key in raw:
            print(key, raw[key])
    print("files:")
    for f in files[:5]:
        print(
            " ",
            f.file_id,
            f.file_name,
            f.version,
            f.category,
        )
    print("description excerpt:", (details.description or "")[:400])


async def main() -> None:
    import sys

    mod_id = int(sys.argv[1]) if len(sys.argv) > 1 else 11077
    await inspect_mod(mod_id)


if __name__ == "__main__":
    asyncio.run(main())
