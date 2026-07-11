# -*- coding: utf-8 -*-
"""收藏夹解析端到端诊断。"""
from __future__ import annotations

import json
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx

URL = "https://www.nexusmods.com/games/cyberpunk2077/collections/iszwwe/mods"
PARSE_BODY = {"url": URL}


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def test_port(port: int) -> dict:
    base = f"http://127.0.0.1:{port}"
    out: dict = {"port": port, "open": port_open(port)}
    if not out["open"]:
        return out
    try:
        t0 = time.time()
        with httpx.Client(timeout=60.0) as c:
            health = c.get(f"{base}/api/health")
            out["health_ms"] = round((time.time() - t0) * 1000)
            out["health_status"] = health.status_code

            t1 = time.time()
            resp = c.post(f"{base}/api/collections/parse", json=PARSE_BODY)
            out["parse_ms"] = round((time.time() - t1) * 1000)
            out["parse_status"] = resp.status_code
            out["parse_bytes"] = len(resp.content)
            if resp.status_code == 200:
                data = resp.json()
                out["queue_count"] = len(data.get("queue") or [])
                out["title"] = (data.get("collection") or {}).get("title")
            else:
                out["parse_error"] = resp.text[:300]

            t2 = time.time()
            index = c.get(f"{base}/")
            out["index_ms"] = round((time.time() - t2) * 1000)
            out["index_status"] = index.status_code
            if index.status_code == 200:
                html = index.text
                if "index-" in html and ".js" in html:
                    start = html.find("/assets/index-")
                    end = html.find(".js", start)
                    js_path = html[start : end + 3] if start >= 0 else ""
                    out["js_bundle"] = js_path
                    if js_path:
                        t3 = time.time()
                        js = c.get(f"{base}{js_path}")
                        out["js_ms"] = round((time.time() - t3) * 1000)
                        out["js_status"] = js.status_code
                        out["js_bytes"] = len(js.content)
                        out["has_timeout_fix"] = b"timedOut" in js.content
                        out["has_watchdog"] = "parseWatchdog" in js.text or "解析超时" in js.text
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def test_json_parse_speed() -> dict:
    from cyberpunk_mod_manager.services.collection_ops import parse_collection_url_to_queue
    import asyncio

    async def run() -> dict:
        t0 = time.time()
        data = await parse_collection_url_to_queue(URL)
        api_ms = round((time.time() - t0) * 1000)
        raw = json.dumps(data, ensure_ascii=False)
        t1 = time.time()
        json.loads(raw)
        parse_ms = round((time.time() - t1) * 1000)
        return {
            "direct_api_ms": api_ms,
            "json_bytes": len(raw.encode("utf-8")),
            "json_parse_ms": parse_ms,
            "queue_count": len(data.get("queue") or []),
        }

    return asyncio.run(run())


def main() -> None:
    print("=== 端口扫描 (8000-8012) ===")
    ports = range(8000, 8013)
    results = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(test_port, p): p for p in ports}
        for fut in as_completed(futs):
            results.append(fut.result())
    for row in sorted(results, key=lambda r: r["port"]):
        if not row.get("open"):
            continue
        print(json.dumps(row, ensure_ascii=False, indent=2))

    print("\n=== 直连服务层 ===")
    print(json.dumps(test_json_parse_speed(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
