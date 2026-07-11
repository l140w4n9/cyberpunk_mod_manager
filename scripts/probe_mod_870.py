# -*- coding: utf-8 -*-
import asyncio

from cyberpunk_mod_manager.nexus.client import NexusClient


async def main() -> None:
    mod_id = 870
    async with NexusClient() as client:
        for path in (
            f"/games/cyberpunk2077/mods/{mod_id}.json",
            f"/games/cyberpunk2077/mods/{mod_id}/files.json",
            f"/games/cyberpunk2077/mods/{mod_id}/files.json?page=0&page_size=100",
        ):
            try:
                resp = await client._request("GET", path)
                data = resp.json()
                if isinstance(data, dict) and "files" in data:
                    print(path, "files", len(data.get("files") or []))
                else:
                    print(path, "keys", list(data.keys())[:8] if isinstance(data, dict) else type(data))
            except Exception as exc:
                print(path, "ERR", exc)

        try:
            details = await client.get_mod_details(mod_id)
            print("name:", details.name)
        except Exception as exc:
            print("details ERR", exc)

        try:
            files = await client.get_mod_files(mod_id)
            print("parsed files:", len(files))
        except Exception as exc:
            print("get_mod_files ERR", exc)


if __name__ == "__main__":
    asyncio.run(main())
