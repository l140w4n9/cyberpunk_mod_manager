# -*- coding: utf-8 -*-
from cyberpunk_mod_manager.installer.rules import match_rule, resolve_target

cet_files = [
    "bin/x64/version.dll",
    "bin/x64/global.ini",
    "bin/x64/LICENSE",
    "bin/x64/plugins/cyber_engine_tweaks.asi",
    "bin/x64/plugins/cyber_engine_tweaks/config.json",
    "bin/x64/plugins/cyber_engine_tweaks/bindings.json",
    "bin/x64/plugins/cyber_engine_tweaks/scripts/json/json.lua",
    "bin/x64/plugins/cyber_engine_tweaks/fonts/NotoSans-Regular.ttf",
    "bin/x64/plugins/cyber_engine_tweaks/tweakdb/epoll.epoll",
    "bin/x64/plugins/cyber_engine_tweaks/mods/empty/init.lua",
]
for rel in cet_files:
    rule = match_rule(rel)
    if rule:
        tgt = resolve_target(rel, rule)
        ok = tgt == rel
        flag = "OK" if ok else "WRONG"
        print(f"{flag:5} {rel} -> {tgt} [{rule.description}]")
    else:
        print(f"SKIP  {rel}")
