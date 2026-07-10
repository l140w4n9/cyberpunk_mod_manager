# -*- coding: utf-8 -*-
"""模组管理 REST 路由：CRUD、安装、卸载、依赖、卸载计划查询。"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from ..config import config
from ..installer import get_uninstall_plan
from ..models import Mod, ModStatus
from ..services import mod_ops
from ..storage.db import get_session

router = APIRouter()


class ModInstallRequest(BaseModel):
    mod_id: int


class LocalInstallRequest(BaseModel):
    mod_id: int
    archive_name: str


class ModOut(BaseModel):
    id: int
    nexus_mod_id: int
    name: str
    version: str
    status: str
    enabled: bool
    installed_at: Optional[str] = None
    thumbnail_url: str = ""
    mod_page_url: str = ""


def _parse_result(result: str) -> dict:
    try:
        data = json.loads(result)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Invalid service response: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        status = 403 if data.get("premium_only") else 502
        raise HTTPException(status, data["error"])
    return data


@router.get("", response_model=list[ModOut])
def list_mods() -> list[ModOut]:
    """列出所有库存模组。"""
    with get_session() as session:
        mods = session.exec(select(Mod)).all()
    return [
        ModOut(
            id=m.id,
            nexus_mod_id=m.nexus_mod_id,
            name=m.name,
            version=m.version,
            status=m.status.value if isinstance(m.status, ModStatus) else str(m.status),
            enabled=m.enabled,
            installed_at=str(m.installed_at) if m.installed_at else None,
            thumbnail_url=m.thumbnail_url,
            mod_page_url=m.mod_page_url,
        )
        for m in mods
    ]


@router.get("/{mod_id}/dependencies")
async def mod_dependencies(mod_id: int) -> dict:
    """查询模组前置依赖及安装状态。"""
    await mod_ops.refresh_dependencies(mod_id)
    report = json.loads(mod_ops.check_dependencies_report(mod_id))
    return report


@router.get("/{mod_id}/uninstall-plan")
def uninstall_plan(mod_id: int) -> dict:
    """查看指定模组的卸载计划。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            raise HTTPException(404, f"Mod {mod_id} not found")
        internal_id = mod.id
    plan = get_uninstall_plan(internal_id)
    if plan is None:
        raise HTTPException(404, "No install record")
    return plan.to_dict()


@router.post("/install")
async def install_mod(req: ModInstallRequest) -> dict:
    """下载并安装模组（Premium 限制时尝试本地压缩包）。"""
    return _parse_result(
        await mod_ops.install_mod(req.mod_id, allow_local_fallback=True)
    )


@router.post("/install-with-deps")
async def install_mod_with_deps(req: ModInstallRequest) -> dict:
    """安装模组并自动安装缺失的前置依赖。"""
    return _parse_result(
        await mod_ops.install_mod_with_dependencies(
            req.mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
        )
    )


@router.post("/install-local")
async def install_local_mod(req: LocalInstallRequest) -> dict:
    """从 downloads 目录的本地压缩包安装模组。"""
    archive_path = config.downloads_dir / req.archive_name
    await mod_ops.ensure_mod_in_inventory(req.mod_id)
    return _parse_result(mod_ops.install_from_archive(req.mod_id, archive_path))


@router.post("/uninstall")
def uninstall_mod(req: ModInstallRequest) -> dict:
    """按卸载计划移除模组。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == req.mod_id)
        ).first()
        if mod is None:
            raise HTTPException(404, f"Mod {req.mod_id} not found")
        internal_id = mod.id
    from ..installer import Installer

    installer = Installer()
    result = installer.uninstall(internal_id)
    return {
        "mod_id": req.mod_id,
        "removed_files_count": len(result.added_files),
        "restored_backups": len(result.backed_up_files),
    }


@router.delete("/{mod_id}")
def delete_mod(mod_id: int) -> dict:
    """从库存删除模组记录。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            raise HTTPException(404, f"Mod {mod_id} not found")
        session.delete(mod)
        session.commit()
    return {"deleted": mod_id}
