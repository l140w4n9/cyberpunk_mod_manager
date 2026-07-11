# -*- coding: utf-8 -*-
import asyncio
import json
import re

import httpx


async def main() -> None:
    url = "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
    async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
        resp = await client.get(url, headers={"User-Agent": "CyberpunkModManager/0.1.0"})
        print("status", resp.status_code, "len", len(resp.text))
        text = resp.text
        patterns = [
            r"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>",
            r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
            r"\"collectionRevisionMods\"",
            r"collectionRevision",
        ]
        for p in patterns:
            print("pattern", p, "found", bool(re.search(p, text, re.DOTALL)))
        m = re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", text, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            print("next keys", data.keys())
            props = data.get("props", {})
            print("props keys", props.keys())
            page = props.get("pageProps", {})
            print("pageProps keys", list(page.keys())[:20])
            # dump shallow structure
            for k, v in page.items():
                if isinstance(v, dict):
                    print(" page", k, list(v.keys())[:15])
                elif isinstance(v, list):
                    print(" page list", k, len(v))


if __name__ == "__main__":
    asyncio.run(main())
