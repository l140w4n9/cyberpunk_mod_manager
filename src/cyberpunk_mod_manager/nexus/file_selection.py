# -*- coding: utf-8 -*-
"""Nexus 模组文件选择：过滤指南/可选包，必要时用 LLM 结合描述挑选安装文件。"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import config
from ..services.summary import (
    _parse_chat_response,
    _strip_html,
    parse_llm_json_from_response,
)
from .client import NexusClient, _pick_latest_version, _version_to_mod_file
from .schemas import ModDetails, ModFile

logger = logging.getLogger(__name__)

SKIP_VERSION_CATEGORIES = frozenset(
    {"optional", "miscellaneous", "old_version", "archived", "removed"}
)

NON_INSTALLABLE_NAME_RE = re.compile(
    r"(guide|manual|readme|tutorial|customer.?s?\s*guide|"
    r"localization|localisation|language\s*pack|preset|"
    r"translating|hd\s*pack|additional\s*stuff|dev\s*build|\bdev\b|"
    r"compatibility|hotfix|alternative\s*storage|online\s*features|"
    r"dark\s*future|custom\s*music|custom\s*characters?|"
    r"character\s*preset|only\s*.+\s*staff|old\s*method|"
    r"alternative\s*method|amm\s*song|dqc|"
    r"使用指南|说明|教程|本地化|语言包|预设|兼容包|热修复)",
    re.IGNORECASE,
)

PREFER_VERSION_CATEGORIES = ("main", "update")


@dataclass
class FileSlotCandidate:
    """一个 mod_files 槽位及其最新可安装版本。"""

    slot_name: str
    mod_file_id: str
    version: ModFile
    version_raw: dict[str, Any]

    @property
    def display_name(self) -> str:
        return self.version.file_name or self.slot_name


def _name_blob(candidate: FileSlotCandidate) -> str:
    return f"{candidate.slot_name} {candidate.display_name}".lower()


def _effective_category(candidate: FileSlotCandidate) -> str:
    return (
        candidate.version.category or candidate.version.category_name or ""
    ).lower()


def is_non_installable_candidate(candidate: FileSlotCandidate) -> bool:
    """启发式：指南、本地化、可选内容等非实际安装包。"""
    category = _effective_category(candidate)
    if category in SKIP_VERSION_CATEGORIES:
        return True
    if NON_INSTALLABLE_NAME_RE.search(_name_blob(candidate)):
        return True
    return False


def _title_similarity(mod_name: str, candidate: FileSlotCandidate) -> int:
    """模组名与文件槽名越接近分数越高。"""
    mod_tokens = set(re.findall(r"[a-z0-9]+", (mod_name or "").lower()))
    slot_tokens = set(re.findall(r"[a-z0-9]+", (candidate.slot_name or "").lower()))
    if not mod_tokens or not slot_tokens:
        return 0
    overlap = len(mod_tokens & slot_tokens)
    extra = max(0, len(slot_tokens) - len(mod_tokens))
    penalty = 10 if "guide" in _name_blob(candidate) else 0
    return overlap * 10 - extra * 3 - penalty


def _category_rank(candidate: FileSlotCandidate) -> int:
    cat = _effective_category(candidate)
    if cat == "main":
        return 3
    if cat == "update":
        return 2
    return 1


def rank_candidates(
    mod_name: str, candidates: list[FileSlotCandidate]
) -> list[FileSlotCandidate]:
    return sorted(
        candidates,
        key=lambda c: (
            _category_rank(c),
            _title_similarity(mod_name, c),
            c.version.uploaded_timestamp or 0,
        ),
        reverse=True,
    )


async def list_file_slot_candidates(
    client: NexusClient,
    mod_id: int,
) -> list[FileSlotCandidate]:
    internal = await client.resolve_mod_internal_id(mod_id)
    if not internal:
        return []
    slots = await client.get_mod_files_v3(internal)
    candidates: list[FileSlotCandidate] = []
    for slot in slots:
        slot_name = str(slot.get("name") or "").strip()
        mod_file_id = str(slot.get("id") or "")
        if not mod_file_id:
            continue
        versions = await client.get_mod_file_versions(mod_file_id)
        pool = [
            v
            for v in versions
            if (v.get("category") or "").lower() in PREFER_VERSION_CATEGORIES
        ] or versions
        pool = [
            v
            for v in pool
            if (v.get("category") or "").lower() not in SKIP_VERSION_CATEGORIES
        ]
        latest = _pick_latest_version(pool)
        if not latest:
            continue
        mf = _version_to_mod_file(latest)
        mf.internal_mod_id = internal
        candidates.append(
            FileSlotCandidate(
                slot_name=slot_name,
                mod_file_id=mod_file_id,
                version=mf,
                version_raw=latest,
            )
        )
    return candidates


def filter_install_candidates(
    candidates: list[FileSlotCandidate],
) -> list[FileSlotCandidate]:
    return [c for c in candidates if not is_non_installable_candidate(c)]


async def _llm_pick_version_ids(
    *,
    mod_id: int,
    mod_name: str,
    description: str,
    candidates: list[FileSlotCandidate],
) -> list[str]:
    if not config.openai_api_key or not candidates:
        return []

    options = [
        {
            "version_id": c.version.version_id,
            "slot_name": c.slot_name,
            "file_name": c.display_name,
            "version": c.version.version,
            "category": c.version.category,
            "file_id": c.version.file_id,
        }
        for c in candidates
    ]
    clean = _strip_html(description)[:2500]
    prompt = (
        "你是赛博朋克2077模组安装助手。根据模组信息与 Nexus 文件列表，"
        "选择应下载并安装到游戏的文件（可多选）。\n\n"
        "规则：\n"
        "- 选择实际模组内容包，不要选使用指南、README、本地化包、预设、HD 包、兼容补丁、DEV 包\n"
        "- category 为 main 的通常是主文件；update 可能是增量补丁，仅当描述要求时选\n"
        "- 若模组明确需要多个主文件（如 core + extension），可返回多个\n"
        "- 只从下列 version_id 中选择\n\n"
        f"模组：{mod_name} (#{mod_id})\n"
        f"描述摘要：{clean or '（无）'}\n\n"
        f"候选文件：{options}\n\n"
        "只输出 JSON："
        '{"files":[{"version_id":"...","reason":"..."}],"strategy":"一句话"}'
    )
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.1,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as http:
            resp = await http.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = _parse_chat_response(resp)
        parsed = parse_llm_json_from_response(data)
        picked: list[str] = []
        for item in parsed.get("files") or []:
            vid = str(item.get("version_id") or "").strip()
            if vid:
                picked.append(vid)
        return picked
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("LLM file pick failed for mod %s: %s", mod_id, exc)
        return []


async def pick_install_versions(
    client: NexusClient,
    mod_id: int,
    *,
    details: ModDetails | None = None,
) -> list[ModFile]:
    """挑选应下载安装的版本（可多个主文件）。"""
    if details is None:
        details = await client.get_mod_details(mod_id)

    all_slots = await list_file_slot_candidates(client, mod_id)
    if not all_slots:
        return []

    installable = filter_install_candidates(all_slots)
    pool = installable or [
        c for c in all_slots if _effective_category(c) == "main"
    ]
    if not pool:
        pool = rank_candidates(details.name, all_slots)[:1]

    ranked = rank_candidates(details.name, pool)
    main_like = [
        c
        for c in ranked
        if _effective_category(c) in PREFER_VERSION_CATEGORIES
    ]
    shortlist = main_like or ranked[:5]

    selected: list[FileSlotCandidate] = []
    if len(shortlist) == 1:
        selected = shortlist
    elif config.openai_api_key:
        picked_ids = await _llm_pick_version_ids(
            mod_id=mod_id,
            mod_name=details.name,
            description=details.description,
            candidates=shortlist,
        )
        by_id = {c.version.version_id: c for c in shortlist}
        for vid in picked_ids:
            if vid in by_id:
                selected.append(by_id[vid])
    if not selected:
        top = ranked[0]
        same_name = [
            c
            for c in ranked
            if _effective_category(c) == "main"
            and _title_similarity(details.name, c) >= _title_similarity(details.name, top) - 5
        ]
        selected = same_name[:3] if same_name else [top]

    return [c.version for c in selected]


def select_download_file(
    files: list[ModFile],
    *,
    mod_name: str = "",
) -> ModFile | None:
    """从扁平 ModFile 列表中选主文件（兼容旧调用）。"""
    if not files:
        return None
    for mod_file in files:
        if mod_file.is_primary:
            return mod_file
    slots = [
        FileSlotCandidate(
            slot_name=f.file_name or "",
            mod_file_id=f.mod_file_id,
            version=f,
            version_raw={},
        )
        for f in files
    ]
    installable = filter_install_candidates(slots)
    pool = installable or slots
    ranked = rank_candidates(mod_name, pool)
    return ranked[0].version if ranked else None
