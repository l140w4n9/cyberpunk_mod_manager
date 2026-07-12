# -*- coding: utf-8 -*-
"""压缩包外层目录剥离测试。"""
from __future__ import annotations

from cyberpunk_mod_manager.installer.layout import (
    build_path_normalizer,
    detect_wrapper_strip_depth,
)


def test_strip_cet_wrapper_folder() -> None:
    entries = [
        "cet_1.37.1/bin/x64/version.dll",
        "cet_1.37.1/bin/x64/plugins/cyber_engine_tweaks.asi",
    ]
    prefixes = ["bin/x64/"]
    assert detect_wrapper_strip_depth(entries, prefixes) == 1
    normalizer = build_path_normalizer(entries, prefixes)
    assert normalizer(entries[0]) == "bin/x64/version.dll"


def test_no_strip_when_paths_already_correct() -> None:
    entries = [
        "bin/x64/version.dll",
        "bin/x64/global.ini",
    ]
    prefixes = ["bin/x64/"]
    assert detect_wrapper_strip_depth(entries, prefixes) == 0
    normalizer = build_path_normalizer(entries, prefixes)
    assert normalizer(entries[0]) == entries[0]
