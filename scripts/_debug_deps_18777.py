# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import collect_dependencies


async def main() -> None:
    async with NexusClient() as client:
        details = await client.get_mod_details(18777)
    deps = await collect_dependencies(18777)
    print("mod:", details.name)
    print("official deps:", [(d["mod_id"], d.get("source"), d.get("name")) for d in deps])


if __name__ == "__main__":
    asyncio.run(main())
