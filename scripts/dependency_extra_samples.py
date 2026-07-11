# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import (
    collect_dependencies,
    fetch_nexus_mod_requirements,
    parse_dependencies_from_text,
)

# 常见仅写在描述里的模组（无 Nexus requirements 表格）
EXTRA_IDS = [7903, 1511, 7780, 26500]


async def main() -> None:
    for mod_id in EXTRA_IDS:
        async with NexusClient() as client:
            d = await client.get_mod_details(mod_id)
        text = f"{d.summary}\n{d.description}"
        gql = await fetch_nexus_mod_requirements(mod_id)
        loose = parse_dependencies_from_text(text, exclude_mod_id=mod_id, owner_mod_id=mod_id)
        strict = parse_dependencies_from_text(
            text, exclude_mod_id=mod_id, owner_mod_id=mod_id, strict=True
        )
        final = await collect_dependencies(mod_id, d.description, d.summary)
        print(f"\n#{mod_id} {d.name}")
        print("  gql:", [(x["mod_id"], x.get("name")) for x in gql])
        print("  loose:", [x["mod_id"] for x in loose])
        print("  strict:", [x["mod_id"] for x in strict])
        print(
            "  final:",
            [(x["mod_id"], x.get("source"), x.get("name")) for x in final],
        )


if __name__ == "__main__":
    asyncio.run(main())
