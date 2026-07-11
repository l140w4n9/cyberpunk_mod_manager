# -*- coding: utf-8 -*-
import asyncio
import json
from pathlib import Path

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import parse_dependencies_from_text


async def inspect_mod(mod_id: int) -> None:
    async with NexusClient() as client:
        resp = await client._request(
            "GET", f"/games/cyberpunk2077/mods/{mod_id}.json"
        )
        raw = resp.json()
        details = await client.get_mod_details(mod_id)
        files = await client.get_mod_files(mod_id)

    text = f"{details.summary}\n{details.description}"
    deps = parse_dependencies_from_text(text, exclude_mod_id=mod_id, owner_mod_id=mod_id)
    print(f"=== mod {mod_id}: {details.name} ===")
    print("parsed from description:", [d["mod_id"] for d in deps])
    print("raw keys:", sorted(raw.keys()))
    for key in ("requirements", "dependencies", "nexus_requirements"):
        if key in raw:
            print(key, raw[key])
    print("files:")
    for f in files[:5]:
        print(
            " ",
            f.file_id,
            f.is_primary,
            (f.description or "")[:300].replace("\n", " "),
        )
    out = Path(__file__).with_name(f"_{mod_id}_raw.json")
    out.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out)


async def main() -> None:
    for mid in (18777, 107, 21422, 4198, 7871):
        await inspect_mod(mid)
        print()


if __name__ == "__main__":
    asyncio.run(main())
