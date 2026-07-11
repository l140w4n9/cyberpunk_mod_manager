# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import (
    collect_dependencies,
    fetch_materialized_mod_dependencies,
    fetch_nexus_mod_requirements,
)

EXTRA_IDS = [7903, 1511, 7780, 26500, 11077]


async def main() -> None:
    for mod_id in EXTRA_IDS:
        async with NexusClient() as client:
            d = await client.get_mod_details(mod_id)
        mat = await fetch_materialized_mod_dependencies(mod_id)
        gql = await fetch_nexus_mod_requirements(mod_id)
        final = await collect_dependencies(mod_id)
        print(f"\n#{mod_id} {d.name}")
        print("  materialized:", [(x["mod_id"], x.get("name")) for x in mat])
        print("  graphql:", [(x["mod_id"], x.get("name")) for x in gql])
        print("  final:", [(x["mod_id"], x.get("source"), x.get("name")) for x in final])


if __name__ == "__main__":
    asyncio.run(main())
