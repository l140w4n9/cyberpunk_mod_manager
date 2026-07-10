# -*- coding: utf-8 -*-
"""批量安装可选模组测试。"""
import asyncio
import json

from cyberpunk_mod_manager.services import mod_ops


async def main() -> None:
    mod_ids = [193, 7341, 237, 2195, 2170, 5154]
    for mod_id in mod_ids:
        print(f"\n=== Installing {mod_id} ===")
        result = await mod_ops.install_mod_with_dependencies(
            mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
        )
        data = json.loads(result)
        if data.get("error"):
            print("ERROR:", data["error"])
        else:
            print(
                "OK added_files_count=",
                data.get("added_files_count"),
                "deps_installed=",
                len(data.get("dependencies_installed", [])),
                "deps_failed=",
                len(data.get("dependencies_failed", [])),
            )
        if data.get("dependencies_failed"):
            for d in data["dependencies_failed"]:
                print("  dep fail:", d)


if __name__ == "__main__":
    asyncio.run(main())
