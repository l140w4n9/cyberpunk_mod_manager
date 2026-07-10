# -*- coding: utf-8 -*-
"""模组描述一句话摘要（LLM 生成 + 本地回退）。"""
from __future__ import annotations

import asyncio
import json
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


def _parse_sse_response(text: str) -> dict:
    """将 text/event-stream 响应聚合为类 OpenAI JSON 结构。"""
    content_parts: list[str] = []
    for line in text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            continue
        choice = (chunk.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        message = choice.get("message") or {}
        piece = delta.get("content") or message.get("content") or ""
        if piece:
            content_parts.append(piece)
    return {"choices": [{"message": {"content": "".join(content_parts)}}]}


def _parse_chat_response(resp: httpx.Response) -> dict:
    """解析 LLM 响应（兼容 JSON 与 SSE）。"""
    ctype = (resp.headers.get("content-type") or "").lower()
    if not resp.content:
        raise ValueError("LLM 返回空响应")

    if "text/event-stream" in ctype:
        return _parse_sse_response(resp.text)

    try:
        return resp.json()
    except json.JSONDecodeError as exc:
        snippet = resp.text[:200].replace("\n", " ")
        raise ValueError(f"LLM 响应不是有效 JSON: {snippet}") from exc


def _extract_message_content(data: dict) -> str:
    """从 chat completion 结果提取文本（兼容 reasoning 模型）。"""
    message = (data.get("choices") or [{}])[0].get("message") or {}
    content = (message.get("content") or "").strip()
    if content:
        return content
    # 部分推理模型仅填充 reasoning_content，最终 content 为空
    reasoning = (message.get("reasoning_content") or "").strip()
    if reasoning:
        for sep in ("。", ". ", "\n"):
            if sep in reasoning:
                return reasoning.split(sep, 1)[0].strip()
        return reasoning[:96].rstrip() + ("…" if len(reasoning) > 96 else "")
    return ""


async def generate_ai_summary(name: str, description: str) -> tuple[str, str]:
    """调用 LLM 生成中文一句话摘要，返回 (摘要, 来源 ai|fallback)。"""
    if not config.openai_api_key:
        return fallback_summary(description, name=name), "fallback"

    clean = _strip_html(description)
    if not clean:
        return name, "fallback"

    prompt = (
        "你是赛博朋克2077模组助手。请用一句简洁的中文（不超过40字）概括以下模组的功能，"
        "只输出这一句，不要解释：\n"
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
        "max_tokens": 512,
        "temperature": 0.3,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = _parse_chat_response(resp)

    content = _extract_message_content(data)
    if not content:
        logger.warning(
            "LLM returned empty summary for %s (model=%s), using fallback",
            name,
            config.model_name,
        )
        return fallback_summary(description, name=name), "fallback"
    if len(content) > 96:
        return content[:95].rstrip() + "…", "ai"
    return content, "ai"


def display_summary(mod: Mod) -> tuple[str, str]:
    """返回 (摘要文本, 来源 ai|fallback|empty)。"""
    if mod.summary_line:
        return mod.summary_line, mod.summary_source or "ai"
    if mod.description:
        return fallback_summary(mod.description, name=mod.name), "fallback"
    return "", "empty"


def _load_mod_for_summary(mod_id: int) -> tuple[int | None, str, str, str]:
    with get_session() as session:
        mod = session.exec(select(Mod).where(Mod.nexus_mod_id == mod_id)).first()
        if mod is None:
            return (None, "", "", "")
        return (mod.id, mod.name, mod.description, mod.summary_line)


def _save_mod_summary(internal_id: int, summary: str, source: str) -> None:
    with get_session() as session:
        mod = session.get(Mod, internal_id)
        if mod is not None:
            mod.summary_line = summary
            mod.summary_source = source
            session.add(mod)
            session.commit()


async def ensure_mod_summary(mod_id: int, *, force: bool = False) -> str:
    """确保模组有一句话摘要并写入数据库。"""
    internal_id, name, description, existing = await asyncio.to_thread(
        _load_mod_for_summary, mod_id
    )
    if internal_id is None:
        return ""
    if existing and not force:
        return existing

    try:
        summary, source = await generate_ai_summary(name, description)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("AI summary failed for mod %s: %s", mod_id, exc)
        summary = fallback_summary(description, name=name)
        source = "fallback"
    except Exception as exc:
        logger.warning("AI summary unexpected error for mod %s: %s", mod_id, exc)
        summary = fallback_summary(description, name=name)
        source = "fallback"

    await asyncio.to_thread(_save_mod_summary, internal_id, summary, source)
    return summary
