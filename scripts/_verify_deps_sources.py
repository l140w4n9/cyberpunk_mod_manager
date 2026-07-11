# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.dependencies import collect_dependencies


async def main() -> None:
    for mid in (9617, 18777):
        deps = await collect_dependencies(mid, "", "")
        print(f"\n#{mid}")
        for d in sorted(deps, key=lambda x: x["mod_id"]):
            print(f"  {d['mod_id']:>6}  {d.get('source'):12}  {d.get('name')}")


if __name__ == "__main__":
    asyncio.run(main())
