# -*- coding: utf-8 -*-
"""收藏夹安装 API。"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..config import config
from ..nexus.client import NexusAPIError
from ..nexus.collections import CollectionParseError, fetch_collection
from ..services import collection_ops
from .errors import api_error, nexus_exception_to_http

router = APIRouter()
logger = logging.getLogger(__name__)


def _ensure_data_dir() -> None:
    if not config.has_data_dir:
        raise HTTPException(
            503,
            detail="data_dir 未配置，请先在「设置」页指定数据存放目录",
        )


class CollectionParseRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Nexus Collection 页面 URL")


class CollectionInstallRequest(BaseModel):
    slug: str = Field(..., min_length=1)
    domain: str = "cyberpunk2077"
    title: str = ""
    mod_ids: list[int] = Field(..., min_length=1)
    install_dependencies: bool = True
    skip_installed: bool = True


class CollectionQueueStatusRequest(BaseModel):
    mod_ids: list[int] = Field(..., min_length=1)


@router.post("/parse")
async def parse_collection(req: CollectionParseRequest) -> dict:
    """解析收藏夹 URL，生成安装队列预览。"""
    _ensure_data_dir()
    logger.info("collection parse start: %s", req.url[:120])
    try:
        result = await asyncio.wait_for(
            collection_ops.parse_collection_url_to_queue(req.url),
            timeout=75.0,
        )
    except asyncio.TimeoutError as exc:
        logger.warning("collection parse timeout: %s", req.url[:120])
        raise api_error(
            504,
            "NEXUS_COLLECTION_TIMEOUT",
            "解析收藏夹超时，请检查网络或稍后重试",
        ) from exc
    except CollectionParseError as exc:
        raise api_error(400, "NEXUS_COLLECTION_INVALID", str(exc)) from exc
    except NexusAPIError as exc:
        raise nexus_exception_to_http(exc) from exc
    except Exception as exc:
        logger.exception("collection parse failed")
        raise api_error(502, "NEXUS_COLLECTION_FAILED", f"拉取收藏夹失败: {exc}") from exc
    logger.info(
        "collection parse done: slug=%s mods=%s",
        (result.get("collection") or {}).get("slug"),
        len(result.get("queue") or []),
    )
    return result


@router.post("/queue-status")
async def collection_queue_status(req: CollectionQueueStatusRequest) -> dict:
    """批量刷新收藏夹队列项的本地安装状态。"""
    _ensure_data_dir()
    rows = collection_ops.refresh_queue_install_status(req.mod_ids)
    return {"count": len(rows), "mods": rows}


@router.post("/install")
async def install_collection(req: CollectionInstallRequest) -> dict:
    """启动收藏夹批量安装任务。"""
    _ensure_data_dir()
    try:
        job_id = await collection_ops.start_collection_install(
            slug=req.slug,
            domain=req.domain,
            title=req.title,
            mod_ids=req.mod_ids,
            install_dependencies=req.install_dependencies,
            skip_installed=req.skip_installed,
        )
    except CollectionParseError as exc:
        raise api_error(400, "NEXUS_COLLECTION_INVALID", str(exc)) from exc

    job = collection_ops.get_job(job_id)
    return job.to_dict() if job else {"job_id": job_id}


@router.get("/jobs/{job_id}")
async def get_collection_job(job_id: str) -> dict:
    """查询安装任务进度。"""
    job = collection_ops.get_job(job_id)
    if job is None:
        raise HTTPException(404, "安装任务不存在或已过期（服务重启后会清空）")
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
async def cancel_collection_job(job_id: str) -> dict:
    """请求取消安装任务（当前项完成后停止）。"""
    if not collection_ops.cancel_job(job_id):
        raise HTTPException(404, "任务不存在或已结束")
    job = collection_ops.get_job(job_id)
    return job.to_dict() if job else {"cancelled": True}


@router.get("/revision")
async def check_collection_revision(
    slug: str = Query(..., min_length=1),
    domain: str = Query("cyberpunk2077"),
    known_revision: int | None = Query(None, description="本地已知的修订号"),
) -> dict:
    """检测收藏夹修订是否变更。"""
    try:
        info = await fetch_collection(slug, domain)
    except CollectionParseError as exc:
        raise api_error(400, "NEXUS_COLLECTION_INVALID", str(exc)) from exc
    except NexusAPIError as exc:
        raise nexus_exception_to_http(exc) from exc
    except Exception as exc:
        raise api_error(502, "NEXUS_COLLECTION_FAILED", f"拉取收藏夹失败: {exc}") from exc

    changed = (
        known_revision is not None
        and int(known_revision) != int(info.revision_number)
    )
    return {
        "slug": info.slug,
        "domain": info.domain,
        "title": info.title,
        "revision_number": info.revision_number,
        "mod_count": info.mod_count,
        "known_revision": known_revision,
        "changed": changed,
        "url": info.url,
    }
