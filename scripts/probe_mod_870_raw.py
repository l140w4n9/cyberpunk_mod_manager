# -*- coding: utf-8 -*-
import asyncio
import json

from cyberpunk_mod_manager.nexus.client import NexusClient


async def main() -> None:
    async with NexusClient() as client:
        resp = await client._request("GET", "/games/cyberpunk2077/mods/870/files.json")
        files = resp.json().get("files", [])
        print(json.dumps(files[0], indent=2))
        print("---")
        print(json.dumps(files[5], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
