# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.dependencies import _get_game_id, fetch_nexus_mod_requirements


async def main() -> None:
    gid = await _get_game_id()
    print("game_id", gid)
    reqs = await fetch_nexus_mod_requirements(18777)
    print("reqs", reqs)


if __name__ == "__main__":
    asyncio.run(main())
