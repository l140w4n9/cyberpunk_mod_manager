# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

from cyberpunk_mod_manager.nexus.client import NexusClient
from cyberpunk_mod_manager.nexus.dependencies import NEXUS_MOD_LINK_RE, parse_dependencies_from_text


async def main() -> None:
    async with NexusClient() as client:
        d = await client.get_mod_details(18777)
    text = f"{d.summary}\n{d.description}"
    deps = parse_dependencies_from_text(text, exclude_mod_id=18777, owner_mod_id=18777)
    print("=== Parsed deps ===")
    for x in sorted(deps, key=lambda i: i["mod_id"]):
        print(x)
    print("=== All mod links in text ===")
    for m in NEXUS_MOD_LINK_RE.finditer(text):
        start = m.start()
        ctx = text[max(0, start - 80) : start + len(m.group(0)) + 40].replace("\n", " ")
        print(m.group(1), "|", ctx[:220].encode("ascii", "replace").decode())
    print("summary len", len(d.summary or ""), "desc len", len(d.description or ""))
    for needle in ("107", "21422", "4198", "7871", "18777", "require", "depend"):
        print(f"--- contains {needle!r}: {needle.lower() in text.lower()}")
    out = Path(__file__).with_name("_18777_description.txt")
    out.write_text(text, encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    asyncio.run(main())
