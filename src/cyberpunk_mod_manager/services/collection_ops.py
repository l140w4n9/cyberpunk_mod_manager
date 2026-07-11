# -*- coding: utf-8 -*-
"""收藏夹安装队列服务。"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from ..models import ModStatus
from ..nexus.collections import CollectionParseError, fetch_collection, parse_collection_url
from . import mod_ops
from .concurrency import DEFAULT_CONCURRENCY, gather_bounded


class QueueItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    mod_id: int
    name: str
    order: int
    optional: bool
    selected: bool = True
    installed: bool = False
    status: str = QueueItemStatus.PENDING.value
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mod_id": self.mod_id,
            "name": self.name,
            "order": self.order,
            "optional": self.optional,
            "selected": self.selected,
            "installed": self.installed,
            "status": self.status,
            "message": self.message,
        }


@dataclass
class CollectionJob:
    job_id: str
    slug: str
    domain: str
    title: str
    state: str = JobState.PENDING.value
    items: list[QueueItem] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    current_mod_id: int | None = None
    cancel_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        stats = _job_stats(self.items)
        return {
            "job_id": self.job_id,
            "slug": self.slug,
            "domain": self.domain,
            "title": self.title,
            "state": self.state,
            "current_mod_id": self.current_mod_id,
            "progress": stats,
            "items": [item.to_dict() for item in self.items],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_jobs: dict[str, CollectionJob] = {}
_jobs_lock = asyncio.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_stats(items: list[QueueItem]) -> dict[str, int]:
    selected = [item for item in items if item.selected]
    return {
        "total": len(selected),
        "done": sum(
            1
            for item in selected
            if item.status
            in (
                QueueItemStatus.SUCCESS.value,
                QueueItemStatus.SKIPPED.value,
                QueueItemStatus.FAILED.value,
                QueueItemStatus.CANCELLED.value,
            )
        ),
        "success": sum(
            1 for item in selected if item.status == QueueItemStatus.SUCCESS.value
        ),
        "skipped": sum(
            1 for item in selected if item.status == QueueItemStatus.SKIPPED.value
        ),
        "failed": sum(
            1 for item in selected if item.status == QueueItemStatus.FAILED.value
        ),
        "pending": sum(
            1 for item in selected if item.status == QueueItemStatus.PENDING.value
        ),
        "running": sum(
            1 for item in selected if item.status == QueueItemStatus.RUNNING.value
        ),
    }


async def parse_collection_url_to_queue(url: str) -> dict[str, Any]:
    """解析 URL 并生成安装队列预览。"""
    parsed = parse_collection_url(url)
    info = await fetch_collection(parsed.slug, parsed.domain)

    queue: list[QueueItem] = []
    installed_count = 0
    status_map = mod_ops.batch_mod_status_info([entry.mod_id for entry in info.mods])
    for entry in info.mods:
        status, installed = status_map.get(
            entry.mod_id, (ModStatus.NOT_INSTALLED.value, False)
        )
        if installed:
            installed_count += 1
        queue.append(
            QueueItem(
                mod_id=entry.mod_id,
                name=entry.name,
                order=entry.order,
                optional=entry.optional,
                selected=not entry.optional,
                installed=installed,
                status=QueueItemStatus.PENDING.value,
                message="已安装，将跳过" if installed else "",
            )
        )

    pending_count = sum(1 for item in queue if item.selected and not item.installed)
    optional_count = sum(1 for item in queue if item.optional)

    return {
        "collection": {
            "title": info.title,
            "slug": info.slug,
            "domain": info.domain,
            "revision_number": info.revision_number,
            "mod_count": info.mod_count,
            "unique_mod_count": len(queue),
            "url": info.url,
            "source_url": parsed.source_url,
        },
        "queue": [item.to_dict() for item in queue],
        "stats": {
            "total": len(queue),
            "installed": installed_count,
            "pending": pending_count,
            "optional": optional_count,
            "selected": sum(1 for item in queue if item.selected),
        },
    }


async def start_collection_install(
    *,
    slug: str,
    domain: str,
    title: str,
    mod_ids: list[int],
    install_dependencies: bool = True,
    skip_installed: bool = True,
) -> str:
    """创建后台安装任务并返回 job_id。"""
    if not mod_ids:
        raise CollectionParseError("安装队列为空，请至少选择一个模组")

    job_id = str(uuid.uuid4())
    items = [
        QueueItem(
            mod_id=mod_id,
            name="",
            order=index + 1,
            optional=False,
            selected=True,
        )
        for index, mod_id in enumerate(mod_ids)
    ]
    job = CollectionJob(
        job_id=job_id,
        slug=slug,
        domain=domain,
        title=title,
        items=items,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    async with _jobs_lock:
        _jobs[job_id] = job

    asyncio.create_task(
        _run_job(
            job_id,
            install_dependencies=install_dependencies,
            skip_installed=skip_installed,
        )
    )
    return job_id


def get_job(job_id: str) -> CollectionJob | None:
    return _jobs.get(job_id)


async def _run_job(
    job_id: str,
    *,
    install_dependencies: bool,
    skip_installed: bool,
) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return

    job.state = JobState.RUNNING.value
    job.updated_at = _utc_now()
    state_lock = asyncio.Lock()

    async def process_item(item: QueueItem) -> None:
        if not item.selected:
            return
        if job.cancel_requested:
            item.status = QueueItemStatus.CANCELLED.value
            item.message = "已取消"
            return
        if item.status not in (
            QueueItemStatus.PENDING.value,
            QueueItemStatus.SKIPPED.value,
        ):
            return

        async with state_lock:
            job.current_mod_id = item.mod_id
            item.status = QueueItemStatus.RUNNING.value
            item.message = "安装中..."
            job.updated_at = _utc_now()

        try:
            if install_dependencies:
                raw = await mod_ops.install_mod_with_dependencies(
                    item.mod_id,
                    install_dependencies=True,
                    allow_local_fallback=True,
                    skip_installed=skip_installed,
                )
            else:
                raw = await mod_ops.install_mod(
                    item.mod_id,
                    allow_local_fallback=True,
                    skip_installed=skip_installed,
                )
            data = json.loads(raw)
            item.name = data.get("name") or item.name
            if data.get("skipped"):
                item.status = QueueItemStatus.SKIPPED.value
                item.message = data.get("message") or "已安装，已跳过"
            elif data.get("error"):
                item.status = QueueItemStatus.FAILED.value
                item.message = str(data.get("error"))
            else:
                item.status = QueueItemStatus.SUCCESS.value
                item.message = "安装完成"
        except Exception as exc:
            item.status = QueueItemStatus.FAILED.value
            item.message = str(exc)

        async with state_lock:
            job.updated_at = _utc_now()

    await gather_bounded(
        [process_item(item) for item in job.items],
        concurrency=DEFAULT_CONCURRENCY,
    )

    job.current_mod_id = None
    job.state = (
        JobState.CANCELLED.value if job.cancel_requested else JobState.DONE.value
    )
    job.updated_at = _utc_now()


def cancel_job(job_id: str) -> bool:
    job = _jobs.get(job_id)
    if job is None or job.state in (JobState.DONE.value, JobState.CANCELLED.value):
        return False
    job.cancel_requested = True
    job.updated_at = _utc_now()
    return True
