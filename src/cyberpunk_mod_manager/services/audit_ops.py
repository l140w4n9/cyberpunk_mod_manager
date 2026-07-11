# -*- coding: utf-8 -*-
"""审查任务（内存 job，供前端轮询进度）。"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import health_audit


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AuditJob:
    job_id: str
    kind: str
    state: str = "pending"
    auto_fix: bool = False
    progress: dict[str, Any] = field(
        default_factory=lambda: {
            "phase": "pending",
            "phase_label": "等待开始",
            "message": "任务排队中…",
            "percent": 0,
        }
    )
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "state": self.state,
            "auto_fix": self.auto_fix,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_jobs: dict[str, AuditJob] = {}


def get_job(job_id: str) -> AuditJob | None:
    return _jobs.get(job_id)


def _set_progress(job: AuditJob, payload: dict[str, Any]) -> None:
    job.progress = payload
    job.updated_at = _utc_now()


async def start_audit_job(*, auto_fix: bool = False) -> str:
    job_id = str(uuid.uuid4())
    now = _utc_now()
    job = AuditJob(
        job_id=job_id,
        kind="audit",
        auto_fix=auto_fix,
        created_at=now,
        updated_at=now,
    )
    _jobs[job_id] = job
    asyncio.create_task(_run_audit_job(job_id))
    return job_id


async def start_updates_job() -> str:
    job_id = str(uuid.uuid4())
    now = _utc_now()
    job = AuditJob(job_id=job_id, kind="updates", created_at=now, updated_at=now)
    _jobs[job_id] = job
    asyncio.create_task(_run_updates_job(job_id))
    return job_id


async def _run_audit_job(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job.state = "running"
    job.updated_at = _utc_now()
    try:
        raw = await health_audit.audit_installation(
            auto_fix=job.auto_fix,
            on_progress=lambda payload: _set_progress(job, payload),
        )
        job.result = json.loads(raw)
        job.state = "done"
        _set_progress(
            job,
            {
                "phase": "done",
                "phase_label": "完成",
                "message": "审查完成",
                "percent": 100,
            },
        )
    except Exception as exc:
        job.state = "failed"
        job.error = str(exc)
        _set_progress(
            job,
            {
                "phase": "failed",
                "phase_label": "失败",
                "message": str(exc),
                "percent": 0,
            },
        )
    job.updated_at = _utc_now()


async def _run_updates_job(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return
    job.state = "running"
    job.updated_at = _utc_now()
    try:
        raw = await health_audit.check_mod_updates(
            on_progress=lambda payload: _set_progress(job, payload),
        )
        job.result = json.loads(raw)
        job.state = "done"
        _set_progress(
            job,
            {
                "phase": "done",
                "phase_label": "完成",
                "message": f"检查完成，{job.result.get('update_count', 0)} 个模组有更新",
                "percent": 100,
            },
        )
    except Exception as exc:
        job.state = "failed"
        job.error = str(exc)
        _set_progress(
            job,
            {
                "phase": "failed",
                "phase_label": "失败",
                "message": str(exc),
                "percent": 0,
            },
        )
    job.updated_at = _utc_now()
