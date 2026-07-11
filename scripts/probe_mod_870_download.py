# -*- coding: utf-8 -*-
import asyncio
import json

from cyberpunk_mod_manager.nexus.client import NexusClient


async def main() -> None:
    mod_id = 870
    async with NexusClient() as client:
        files = await client.get_mod_files(mod_id)
        print("files:", len(files))
        for f in files:
            print(
                f.file_id,
                f.is_primary,
                f.category_name,
                (f.file_name or "")[:60],
            )
            try:
                links = await client.get_download_links(mod_id, f.file_id)
                print("  download OK", len(links), links[0].URI[:60] if links else "")
            except Exception as exc:
                print("  download ERR", exc)

        primary = await client.pick_primary_file(mod_id)
        print("primary:", primary.file_id if primary else None, primary.file_name if primary else None)


if __name__ == "__main__":
    asyncio.run(main())
