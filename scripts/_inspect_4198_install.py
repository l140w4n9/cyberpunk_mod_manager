# -*- coding: utf-8 -*-
"""检查 4198 安装状态与规则匹配。"""
from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.installer.rules import match_rule, resolve_target

DB = config.data_dir_path / "manager.db"
GAME = Path(config.game_path)


def main() -> None:
    print("data_dir:", config.data_dir)
    print("game_path:", config.game_path, "exists:", GAME.is_dir())
    axl = GAME / "red4ext" / "plugins" / "ArchiveXL"
    print("ArchiveXL dir exists:", axl.is_dir(), axl)

    if not DB.exists():
        print("no db")
        return

    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    for row in c.execute(
        "SELECT id, nexus_mod_id, name, status, local_path FROM mods WHERE nexus_mod_id=4198"
    ):
        print("mod:", dict(row))

    for row in c.execute(
        """
        SELECT ir.mod_id, ir.added_files, ir.source_file
        FROM install_records ir
        JOIN mods m ON m.id = ir.mod_id
        WHERE m.nexus_mod_id = 4198
        """
    ):
        added = json.loads(row["added_files"] or "[]")
        print(
            "record mod_id=",
            row["mod_id"],
            "added_count=",
            len(added),
            "source=",
            row["source_file"],
        )
        print("  added sample:", added[:10])
        print("  skipped would be in install result only")

    print("\n=== zero-file installed mods ===")
    for row in c.execute(
        """
        SELECT m.nexus_mod_id, m.name, ir.added_files
        FROM install_records ir
        JOIN mods m ON m.id = ir.mod_id
        WHERE m.status = 'installed'
        """
    ):
        added = json.loads(row["added_files"] or "[]")
        if not added:
            print(" ", row["nexus_mod_id"], row["name"])

    c.close()

    downloads = config.downloads_dir
    print("\n=== downloads ===")
    if downloads.is_dir():
        for p in sorted(downloads.glob("*4198*"))[:5]:
            print(" ", p.name, p.stat().st_size)
        archives = list(downloads.glob("*4198*")) or list(downloads.glob("*.zip"))[:3]
    else:
        archives = []

    for arc in archives[:2]:
        print(f"\n=== archive listing: {arc.name} ===")
        try:
            with zipfile.ZipFile(arc) as zf:
                names = zf.namelist()[:30]
                for n in names:
                    rule = match_rule(n.replace("\\", "/"))
                    if rule:
                        target = resolve_target(n.replace("\\", "/"), rule)
                        print(f"  MATCH {n} -> {target}")
                    else:
                        print(f"  SKIP  {n}")
                if len(zf.namelist()) > 30:
                    print(f"  ... +{len(zf.namelist()) - 30} more")
        except Exception as exc:
            print("  cannot read:", exc)


if __name__ == "__main__":
    main()
