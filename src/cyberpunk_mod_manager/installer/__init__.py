# -*- coding: utf-8 -*-
"""Installer 子包。"""
from .engine import Installer, InstallResult
from .rules import INSTALL_RULES, match_rule, resolve_target
from .uninstall import UninstallPlan, get_uninstall_plan

__all__ = [
    "Installer",
    "InstallResult",
    "INSTALL_RULES",
    "match_rule",
    "resolve_target",
    "UninstallPlan",
    "get_uninstall_plan",
]
