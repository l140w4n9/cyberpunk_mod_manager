# -*- coding: utf-8 -*-
"""Installer 子包。"""
from .engine import Installer, InstallResult
from .profile import GameInstallProfile, get_install_profile
from .rules import match_rule, resolve_mapping, resolve_target
from .uninstall import UninstallPlan, get_uninstall_plan

__all__ = [
    "Installer",
    "InstallResult",
    "GameInstallProfile",
    "get_install_profile",
    "match_rule",
    "resolve_target",
    "resolve_mapping",
    "UninstallPlan",
    "get_uninstall_plan",
]
