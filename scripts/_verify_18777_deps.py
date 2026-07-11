# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.dependencies import collect_dependencies


async def main() -> None:
    deps = await collect_dependencies(18777)
    print("deps for 18777:")
    for d in sorted(deps, key=lambda x: x["mod_id"]):
        print(d)


if __name__ == "__main__":
    asyncio.run(main())
