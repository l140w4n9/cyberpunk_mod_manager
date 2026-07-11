# -*- coding: utf-8 -*-
"""卸载记录查询工具，供 Agent 与 API 共用。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlmodel import select

from ..models import InstallRecord
from ..storage.db import get_session


@dataclass
class UninstallPlan:
    """卸载计划的可读视图。"""

    mod_id: int
    added_files: list[str]
    created_dirs: list[str]
    backed_up_files: list[dict]
    installed_at: Optional[str] = None
    source_file: str = ""
    plan_source: str = ""
    plan_items: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def get_uninstall_plan(mod_id: int) -> Optional[UninstallPlan]:
    """读取指定模组的卸载计划。"""
    with get_session() as session:
        record = session.exec(
            select(InstallRecord).where(
                InstallRecord.mod_id == mod_id
            )
        ).first()
        if record is None:
            return None
        return UninstallPlan(
            mod_id=record.mod_id,
            added_files=json.loads(record.added_files),
            created_dirs=json.loads(record.created_dirs),
            backed_up_files=json.loads(record.backed_up_files),
            installed_at=str(record.installed_at),
            source_file=record.source_file,
            plan_source=record.plan_source or "",
            plan_items=json.loads(record.plan_json or "[]"),
        )
