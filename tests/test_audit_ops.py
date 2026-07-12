# -*- coding: utf-8 -*-
"""审查任务 API 测试。"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from cyberpunk_mod_manager.services import audit_ops


@pytest.mark.asyncio
@patch("cyberpunk_mod_manager.services.audit_ops.health_audit.audit_installation", new_callable=AsyncMock)
async def test_audit_job_reports_progress_and_result(mock_audit) -> None:
    progress_events: list[dict] = []

    async def fake_audit(*, auto_fix=False, on_progress=None, locale=None):
        if on_progress:
            on_progress({"phase": "scan", "phase_label": "扫描", "message": "扫描中", "percent": 10})
            on_progress({"phase": "done", "phase_label": "完成", "message": "完成", "percent": 100})
        return json.dumps({"healthy": True, "issues": {"update_count": 0}})

    mock_audit.side_effect = fake_audit

    job_id = await audit_ops.start_audit_job(auto_fix=False)
    await asyncio.sleep(0.05)

    job = audit_ops.get_job(job_id)
    assert job is not None
    assert job.state == "done"
    assert job.result is not None
    assert job.result.get("healthy") is True
    assert job.progress.get("phase") == "done"


@pytest.mark.asyncio
@patch("cyberpunk_mod_manager.services.audit_ops.health_audit.check_mod_updates", new_callable=AsyncMock)
async def test_updates_job_completes(mock_updates) -> None:
    mock_updates.return_value = json.dumps({"update_count": 2, "updates": [{"mod_id": 1}]})

    job_id = await audit_ops.start_updates_job()
    await asyncio.sleep(0.05)

    job = audit_ops.get_job(job_id)
    assert job is not None
    assert job.kind == "updates"
    assert job.state == "done"
    assert job.result.get("update_count") == 2
