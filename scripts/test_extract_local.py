# -*- coding: utf-8 -*-
from pathlib import Path
import shutil

from cyberpunk_mod_manager.installer.archives import (
    detect_archive_kind,
    extract_archive,
    _find_7z_exe,
)

downloads = Path(r"C:\Users\liaowang\.cyberpunk_mod_manager\downloads")
names = [
    "Alternative Skin Material-7341-1-0-1675607841.rar",
    "E3 2018 LUT-5154-1-0-1662710773.rar",
    "Alt Character Lighting-237-1-0-1608087138.zip",
]
print("7z exe:", _find_7z_exe())
for name in names:
    p = downloads / name
    print(name, "kind=", detect_archive_kind(p))
    out = downloads / ("_test_" + name)
    if out.exists():
        shutil.rmtree(out)
    try:
        k = extract_archive(p, out)
        files = [f for f in out.rglob("*") if f.is_file()]
        print("  OK", k, "files", len(files))
        for f in sorted(files)[:8]:
            print("   ", f.relative_to(out))
    except Exception as exc:
        print("  FAIL", exc)
