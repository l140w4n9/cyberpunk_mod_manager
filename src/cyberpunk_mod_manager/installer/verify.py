# -*- coding: utf-8 -*-
"""安装后验收：检查关键文件是否落在游戏目录。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import config
from ..installer import get_uninstall_plan
from .profile import FrameworkCheck, GameInstallProfile, get_install_profile


def _framework_checks_for_mod(
    profile: GameInstallProfile,
    nexus_mod_id: int,
) -> list[FrameworkCheck]:
    matched: list[FrameworkCheck] = []
    for check in profile.framework_checks:
        if not check.mod_ids or nexus_mod_id in check.mod_ids:
            matched.append(check)
    return matched


def verify_installed_files(
    *,
    internal_mod_id: int,
    nexus_mod_id: int,
    game_path: Path | None = None,
    profile: GameInstallProfile | None = None,
) -> dict[str, Any]:
    """对照安装档案与 InstallRecord 验收安装结果。"""
    root = (game_path or Path(config.game_path)).resolve()
    prof = profile or get_install_profile()
    missing_required: list[dict[str, str]] = []
    missing_recorded: list[str] = []
    checks_run: list[str] = []

    for check in _framework_checks_for_mod(prof, nexus_mod_id):
        checks_run.append(check.name)
        for rel in check.required_paths:
            target = root / rel.replace("\\", "/")
            if not target.is_file():
                missing_required.append(
                    {
                        "check": check.name,
                        "path": rel,
                        "reason": "框架必需文件缺失",
                    }
                )

    plan = get_uninstall_plan(internal_mod_id)
    if plan is not None:
        for rel in plan.added_files:
            target = root / rel.replace("\\", "/")
            if not target.is_file():
                missing_recorded.append(rel)

    ok = not missing_required and not missing_recorded
    warnings: list[str] = []
    if missing_required:
        warnings.append(
            "缺少框架关键文件: "
            + ", ".join(item["path"] for item in missing_required[:5])
        )
    if missing_recorded:
        warnings.append(
            f"安装记录中有 {len(missing_recorded)} 个文件在游戏目录中不存在"
        )

    return {
        "ok": ok,
        "verified": ok,
        "game_domain": prof.game_domain,
        "profile_source": prof.source_path,
        "checks_run": checks_run,
        "missing_required": missing_required,
        "missing_recorded": missing_recorded,
        "warnings": warnings,
    }


def verify_installed_files_json(
    *,
    internal_mod_id: int,
    nexus_mod_id: int,
) -> str:
    return json.dumps(
        verify_installed_files(
            internal_mod_id=internal_mod_id,
            nexus_mod_id=nexus_mod_id,
        ),
        ensure_ascii=False,
    )
