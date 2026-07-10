# -*- coding: utf-8 -*-
"""模组描述一句话摘要（LLM 生成 + 本地回退）。"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx
from sqlmodel import select

from ..config import config
from ..models import Mod
from ..storage.db import get_session

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text or "").strip()


def fallback_summary(
    description: str,
    *,
    name: str = "",
    max_len: int = 96,
) -> str:
    """无 LLM 时从描述截取一句话。"""
    text = _strip_html(description)
    if not text:
        return name
    for sep in ("。", ". ", "！", "! ", "\n"):
        if sep in text:
            text = text.split(sep, 1)[0].strip()
            break
    if len(text) > max_len:
        return text[: max_len - 1].rstrip() + "…"
    return text


async def generate_ai_summary(name: str, description: str) -> tuple[str, str]:
    """调用 LLM 生成中文一句话摘要，返回 (摘要, 来源 ai|fallback)。"""
    if not config.openai_api_key:
        return fallback_summary(description, name=name), "fallback"

    clean = _strip_html(description)
    if not clean:
        return name, "fallback"

    prompt = (
        "你是赛博朋克2077模组助手。请用一句简洁的中文（不超过40字）概括以下模组的功能，"
        "不要加引号或前缀：\n"
        f"模组名：{name}\n"
        f"描述：{clean[:1200]}"
    )
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 80,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    content = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not content:
        return fallback_summary(description, name=name), "fallback"
    if len(content) > 96:
        return content[:95].rstrip() + "…", "ai"
    return content, "ai"


def display_summary(mod: Mod) -> tuple[str, str]:
    """返回 (摘要文本, 来源 ai|fallback|empty)。"""
    if mod.summary_line:
        # summary_source 为空时向后兼容已有数据，默认视为 ai
        return mod.summary_line, mod.summary_source or "ai"
    if mod.description:
        return fallback_summary(mod.description, name=mod.name), "fallback"
    return "", "empty"


def _load_mod_for_summary(
    mod_id: int,
) -> tuple[int | None, str, str, str]:
    """同步读取摘要生成所需字段。

    返回 (internal_id, name, description, existing_summary)。
    internal_id 为 None 表示模组不存在。
    """
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == mod_id)).first()
        if mod is None:
            return (None, "", "", "")
        return (mod.id, mod.name, mod.description, mod.summary_line)


def _save_mod_summary(internal_id: int, summary: str, source: str) -> None:
    """同步写入摘要及其来源到数据库。"""
    with get_session() as session:
        mod = session.get(Mod, internal_id)
        if mod is not None:
            mod.summary_line = summary
            mod.summary_source = source
            session.add(mod)
            session.commit()


async def ensure_mod_summary(mod_id: int, *, force: bool = False) -> str:
    """确保模组有一句话摘要并写入数据库。"""
    # 通过线程执行同步 DB 操作，避免在事件循环上阻塞
    internal_id, name, description, existing = await asyncio.to_thread(
        _load_mod_for_summary, mod_id
    )
    if internal_id is None:
        return ""
    if existing and not force:
        return existing

    try:
        summary, source = await generate_ai_summary(name, description)
    except httpx.HTTPError as exc:
        logger.warning("AI summary generation failed for mod %s: %s", mod_id, exc)
        summary = fallback_summary(description, name=name)
        source = "fallback"
    except Exception:
        logger.exception(
            "Unexpected error generating AI summary for mod %s", mod_id
        )
        summary = fallback_summary(description, name=name)
        source = "fallback"

    await asyncio.to_thread(_save_mod_summary, internal_id, summary, source)
    return summary
