# -*- coding: utf-8 -*-
"""健康审查与更新检查测试。"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cyberpunk_mod_manager.models.mod import ModStatus
from cyberpunk_mod_manager.services import health_audit


def _overview(mod_id: int, name: str, status: str, **extra) -> dict:
    base = {
        "id": mod_id,
        "nexus_mod_id": mod_id,
        "name": name,
        "version": "1.0",
        "status": status,
        "enabled": True,
        "dependencies_missing_count": extra.get("missing", 0),
        "dependencies_satisfied": extra.get("satisfied", True),
        "dependencies": [],
        "dependents": [],
    }
    base.update(extra)
    return base


@patch("cyberpunk_mod_manager.services.health_audit._load_all_mods")
@patch("cyberpunk_mod_manager.services.health_audit.mod_ops.build_mod_overview")
def test_list_pending_mods(mock_overview, mock_load) -> None:
    mod = MagicMock()
    mock_load.return_value = [mod]
    mock_overview.return_value = _overview(100, "Pending Mod", ModStatus.NOT_INSTALLED.value)

    data = json.loads(health_audit.list_pending_mods())
    assert data["count"] == 1
    assert data["mods"][0]["nexus_mod_id"] == 100


@patch("cyberpunk_mod_manager.services.health_audit._load_all_mods")
@patch("cyberpunk_mod_manager.services.health_audit.mod_ops.build_mod_overview")
def test_list_incomplete_mods(mock_overview, mock_load) -> None:
    mod = MagicMock()
    mock_load.return_value = [mod]
    mock_overview.return_value = _overview(
        200,
        "Broken Mod",
        ModStatus.INSTALLED.value,
        missing=2,
        satisfied=False,
    )

    data = json.loads(health_audit.list_incomplete_mods())
    assert data["count"] == 1
    assert data["mods"][0]["dependencies_satisfied"] is False


@pytest.mark.asyncio
@patch("cyberpunk_mod_manager.services.health_audit.NexusClient")
@patch("cyberpunk_mod_manager.services.health_audit._load_all_mods")
@patch("cyberpunk_mod_manager.services.health_audit.mod_ops._status_str")
async def test_check_mod_updates_detects_new_file(
    mock_status, mock_load, mock_client_cls
) -> None:
    mod = MagicMock()
    mod.nexus_mod_id = 300
    mod.name = "Test Mod"
    mod.version = "1.0"
    mod.nexus_file_id = 10
    mock_load.return_value = [mod]
    mock_status.return_value = ModStatus.INSTALLED.value

    details = MagicMock()
    details.version = "1.1"
    latest = MagicMock()
    latest.file_id = 20
    latest.version = "1.1"
    latest.file_name = "main.zip"

    client = AsyncMock()
    client.get_mod_details = AsyncMock(return_value=details)
    client.get_mod_files = AsyncMock(return_value=[latest])
    mock_client_cls.return_value.__aenter__.return_value = client

    data = json.loads(await health_audit.check_mod_updates())
    assert data["update_count"] == 1
    assert data["updates"][0]["mod_id"] == 300


@pytest.mark.asyncio
@patch("cyberpunk_mod_manager.services.health_audit._auto_fix_issues", new_callable=AsyncMock)
@patch("cyberpunk_mod_manager.services.health_audit._llm_audit_summary", new_callable=AsyncMock)
@patch("cyberpunk_mod_manager.services.health_audit.check_mod_updates", new_callable=AsyncMock)
@patch("cyberpunk_mod_manager.services.health_audit._collect_issues")
@patch("cyberpunk_mod_manager.services.health_audit._load_all_mods")
async def test_audit_installation_with_auto_fix(
    mock_load,
    mock_collect,
    mock_updates,
    mock_llm,
    mock_fix,
) -> None:
    mock_load.return_value = []
    mock_collect.return_value = {
        "pending": [],
        "incomplete": [_overview(1, "A", ModStatus.INSTALLED.value, missing=1, satisfied=False)],
        "installed_count": 1,
        "no_uninstall_plan": [],
        "downloaded_not_installed": [],
        "disabled_installed": [],
    }
    mock_updates.return_value = json.dumps({"updates": []})
    mock_llm.return_value = {"summary": "需要补依赖", "recommendations": [], "source": "rules"}
    mock_fix.return_value = {"fixed": [{"mod_id": 1}], "failed": []}

    data = json.loads(await health_audit.audit_installation(auto_fix=True))
    assert data["healthy"] is False
    assert data["issues"]["incomplete_count"] == 1
    assert data["auto_fix"]["fixed"]
    mock_fix.assert_awaited_once()
