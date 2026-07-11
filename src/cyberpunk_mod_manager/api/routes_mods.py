# -*- coding: utf-8 -*-
"""模组管理 REST 路由：CRUD、安装、卸载、依赖、卸载计划查询。"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from ..config import config
from ..installer import Installer, get_uninstall_plan
from ..models import Mod
from ..services import audit_ops, discovery, health_audit, mod_ops
from ..services.summary import display_summary, ensure_mod_summary
from ..storage.db import get_session

router = APIRouter()


def _ensure_data_dir() -> None:
    if not config.has_data_dir:
        raise HTTPException(
            503,
            detail="data_dir 未配置，请先在「设置」页指定数据存放目录",
        )


class ModInstallRequest(BaseModel):
    mod_id: int
    force: bool = False


class LocalInstallRequest(BaseModel):
    mod_id: int
    archive_name: str


class LocalFolderScanRequest(BaseModel):
    folder_path: str


class LocalFolderInstallRequest(BaseModel):
    folder_path: str
    mod_ids: list[int] | None = None
    install_dependencies: bool = True
    skip_installed: bool = True


class AuditRequest(BaseModel):
    auto_fix: bool = False


class CleanupPendingRequest(BaseModel):
    mod_ids: list[int] | None = None


class BatchStatusRequest(BaseModel):
    mod_ids: list[int] = Field(..., min_length=1)


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
    refresh_dep_names: bool = Query(
        False, description="从库存与 Nexus API 补全缺失的依赖名称"
    ),
) -> list[ModOut]:
    """列出所有库存模组（含依赖关系与一句话摘要）。"""
    _ensure_data_dir()
    from ..nexus.dependencies import (
        enrich_dependency_names_from_nexus,
        enrich_dependency_names_sync,
    )

    # 将同步 DB 操作卸载到线程池，避免阻塞事件循环
    mods = await asyncio.to_thread(_load_all_mods)
    if refresh_dep_names:
        await asyncio.to_thread(enrich_dependency_names_sync)
        await enrich_dependency_names_from_nexus()

    if refresh_summaries and config.openai_api_key:
        await mod_ops.refresh_mod_summaries()

    return [ModOut(**mod_ops.build_mod_overview(m)) for m in mods]


@router.get("/pending")
async def list_pending_mods() -> dict:
    """待安装模组（已入库但未装进游戏）。"""
    _ensure_data_dir()
    return json.loads(health_audit.list_pending_mods())


@router.get("/incomplete")
async def list_incomplete_mods() -> dict:
    """依赖不全模组（已安装但缺少必需依赖）。"""
    _ensure_data_dir()
    return json.loads(health_audit.list_incomplete_mods())


@router.post("/check-updates")
async def check_mod_updates() -> dict:
    """检查已安装模组在 Nexus 上是否有更新。"""
    _ensure_data_dir()
    return json.loads(await health_audit.check_mod_updates())


@router.post("/audit")
async def audit_installation(req: AuditRequest) -> dict:
    """审查模组安装健康状态，可选自动修复依赖与更新（同步，供 Agent 使用）。"""
    _ensure_data_dir()
    return json.loads(await health_audit.audit_installation(auto_fix=req.auto_fix))


@router.post("/audit/start")
async def start_audit_job(req: AuditRequest) -> dict:
    """启动审查任务（异步，供前端轮询进度）。"""
    _ensure_data_dir()
    job_id = await audit_ops.start_audit_job(auto_fix=req.auto_fix)
    job = audit_ops.get_job(job_id)
    if job is None:
        raise HTTPException(500, "审查任务创建失败")
    return job.to_dict()


@router.get("/audit/jobs/{job_id}")
async def get_audit_job(job_id: str) -> dict:
    """查询审查/更新检查任务进度与结果。"""
    job = audit_ops.get_job(job_id)
    if job is None:
        raise HTTPException(404, "任务不存在或已过期（服务重启后会清空）")
    return job.to_dict()


@router.post("/check-updates/start")
async def start_check_updates_job() -> dict:
    """启动更新检查任务（异步，供前端轮询进度）。"""
    _ensure_data_dir()
    job_id = await audit_ops.start_updates_job()
    job = audit_ops.get_job(job_id)
    if job is None:
        raise HTTPException(500, "更新检查任务创建失败")
    return job.to_dict()


@router.post("/cleanup-pending")
def cleanup_pending_mods(req: CleanupPendingRequest) -> dict:
    """批量从库存清理待安装模组（未安装状态）。"""
    _ensure_data_dir()
    return mod_ops.cleanup_pending_mods(req.mod_ids)


@router.get("/discovery/trending")
async def get_trending_mods() -> dict:
    """Nexus 热门模组（公开 feed）。"""
    _ensure_data_dir()
    mods = await discovery.fetch_trending_mods()
    return {"count": len(mods), "mods": mods}


@router.post("/discovery/sync-tracked")
async def sync_tracked_mods() -> dict:
    """将 Nexus 账户追踪的模组同步到本地库存。"""
    _ensure_data_dir()
    return await discovery.sync_tracked_mods_to_inventory()


@router.get("/discovery/updated-feed")
async def get_updated_feed(
    period: str = Query("1w", description="时间窗口：1d / 1w / 1m"),
    compare_local: bool = Query(False, description="是否与本地库存比对"),
) -> dict:
    """Nexus 近期有活动的模组 feed。"""
    _ensure_data_dir()
    feed = await discovery.fetch_updated_feed(period=period)
    payload: dict = {"count": len(feed), "period": period, "feed": feed}
    if compare_local:
        payload["local_hits"] = discovery.compare_local_with_updated_feed(feed)
    return payload


@router.post("/discovery/batch-status")
async def batch_mod_status(req: BatchStatusRequest) -> dict:
    """批量查询模组在 Nexus 上的可用性与状态。"""
    _ensure_data_dir()
    rows = await discovery.batch_mod_availability(req.mod_ids)
    return {"count": len(rows), "mods": rows}


@router.get("/{mod_id}/dependency-ranges")
async def mod_dependency_ranges(
    mod_id: int,
    version_id: str | None = Query(None, description="v3 文件版本 ID，省略则用已安装或最新"),
) -> dict:
    """查询模组文件版本的依赖范围定义（v3）。"""
    _ensure_data_dir()
    from ..nexus.client import NexusClient

    async with NexusClient() as client:
        target = version_id
        if not target:
            with get_session() as session:
                mod = session.exec(
                    select(Mod).where(Mod.nexus_mod_id == mod_id)
                ).first()
            if mod and mod.nexus_version_id:
                target = mod.nexus_version_id
            else:
                picked = await client.resolve_target_version(mod_id)
                target = picked.version_id if picked else ""
        if not target:
            raise HTTPException(404, f"未找到模组 {mod_id} 的可用文件版本")
        data = await client.get_dependency_ranges(target)
    return {
        "mod_id": mod_id,
        "version_id": target,
        "ranges": data.get("data") or data,
    }


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
        await mod_ops.install_mod(
            req.mod_id,
            allow_local_fallback=True,
            skip_installed=not req.force,
        )
    )


@router.post("/install-with-deps")
async def install_mod_with_deps(req: ModInstallRequest) -> dict:
    """安装模组并自动安装缺失的前置依赖。"""
    return _parse_result(
        await mod_ops.install_mod_with_dependencies(
            req.mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
            skip_installed=not req.force,
        )
    )


@router.post("/install-local")
async def install_local_mod(req: LocalInstallRequest) -> dict:
    """从本地压缩包安装模组（downloads 或绝对路径）。"""
    path = Path(req.archive_name)
    archive_path = path if path.is_absolute() else config.downloads_dir / req.archive_name
    await mod_ops.ensure_mod_in_inventory(req.mod_id)
    return _parse_result(mod_ops.install_from_archive(req.mod_id, archive_path))


@router.post("/scan-local")
async def scan_local_folder(req: LocalFolderScanRequest) -> dict:
    """扫描文件夹，识别压缩包中的模组 ID。"""
    return _parse_result(mod_ops.scan_local_folder(req.folder_path))


@router.post("/install-local-folder")
async def install_local_folder(req: LocalFolderInstallRequest) -> dict:
    """从文件夹批量本地安装（自动识别 ID 与依赖）。"""
    return _parse_result(
        await mod_ops.install_local_folder(
            req.folder_path,
            mod_ids=req.mod_ids,
            install_dependencies=req.install_dependencies,
            skip_installed=req.skip_installed,
        )
    )


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
    """从库存删除模组记录（仅允许未安装状态）。"""
    _ensure_data_dir()
    result = mod_ops.delete_mod_from_inventory(mod_id)
    if result.get("error"):
        if "not found" in result["error"].lower():
            raise HTTPException(404, result["error"])
        raise HTTPException(400, result["error"])
    return result
