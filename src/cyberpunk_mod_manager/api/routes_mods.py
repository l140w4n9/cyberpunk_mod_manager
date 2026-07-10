# -*- coding: utf-8 -*-
"""模组管理 REST 路由：CRUD、安装、卸载、依赖、卸载计划查询。"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from ..config import config
from ..installer import Installer, get_uninstall_plan
from ..models import Mod
from ..services import mod_ops
from ..services.summary import display_summary, ensure_mod_summary
from ..storage.db import get_session

router = APIRouter()


class ModInstallRequest(BaseModel):
    mod_id: int
    force: bool = False


class LocalInstallRequest(BaseModel):
    mod_id: int
    archive_name: str


class DependencyOut(BaseModel):
    nexus_mod_id: int
    name: str
    source: str = ""
    installed: bool = False
    status: str = "not_installed"


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
    summary_line: str = ""
    summary_source: str = "empty"
    dependencies: list[DependencyOut] = []
    dependents: list[DependencyOut] = []
    dependencies_missing_count: int = 0
    dependencies_satisfied: bool = True


def _parse_result(result: str) -> dict:
    try:
        data = json.loads(result)
    except json.JSONDecodeError as exc:
        raise HTTPException(500, f"Invalid service response: {exc}") from exc
    if isinstance(data, dict) and data.get("error"):
        status = 403 if data.get("premium_only") else 502
        raise HTTPException(status, data["error"])
    return data


def _load_all_mods() -> list[Mod]:
    """同步加载所有模组记录。"""
    with get_session() as session:
        return session.exec(select(Mod)).all()


@router.get("", response_model=list[ModOut])
async def list_mods(
    refresh_summaries: bool = Query(False, description="为缺少摘要的模组调用 LLM 生成"),
) -> list[ModOut]:
    """列出所有库存模组（含依赖关系与一句话摘要）。"""
    # 将同步 DB 操作卸载到线程池，避免阻塞事件循环
    mods = await asyncio.to_thread(_load_all_mods)

    if refresh_summaries and config.openai_api_key:
        await mod_ops.refresh_mod_summaries()

    return [ModOut(**mod_ops.build_mod_overview(m)) for m in mods]


@router.get("/{mod_id}/dependencies")
async def mod_dependencies(mod_id: int) -> dict:
    """查询模组前置依赖及安装状态。"""
    await mod_ops.refresh_dependencies(mod_id)
    return json.loads(mod_ops.check_dependencies_report(mod_id))


@router.get("/{mod_id}/uninstall-check")
def uninstall_check(mod_id: int) -> dict:
    """评估卸载是否安全（反向依赖检查）。"""
    return mod_ops.check_uninstall_report(mod_id)


@router.get("/{mod_id}/summary")
async def mod_summary(mod_id: int, refresh: bool = Query(False)) -> dict:
    """获取或刷新模组一句话摘要。"""
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()
        if mod is None:
            raise HTTPException(404, f"Mod {mod_id} not found")

    summary = await ensure_mod_summary(mod_id, force=refresh)
    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == mod_id)
        ).first()

    text, source = display_summary(mod) if mod else (summary, "ai")
    return {
        "mod_id": mod_id,
        "summary_line": text or summary,
        "summary_source": source,
    }


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
    """按卸载计划移除模组（默认检查反向依赖）。"""
    report = mod_ops.check_uninstall_report(req.mod_id)
    if not report.get("can_uninstall"):
        raise HTTPException(400, report.get("warnings", ["无法卸载"])[0])
    if not report.get("safe") and not req.force:
        raise HTTPException(
            409,
            detail={
                "message": "卸载可能影响其他已安装模组",
                "report": report,
            },
        )

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == req.mod_id)
        ).first()
        if mod is None:
            raise HTTPException(404, f"Mod {req.mod_id} not found")
        internal_id = mod.id

    installer = Installer()
    result = installer.uninstall(internal_id)
    return {
        "mod_id": req.mod_id,
        "removed_files_count": len(result.added_files),
        "restored_backups": len(result.backed_up_files),
        "forced": req.force,
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
