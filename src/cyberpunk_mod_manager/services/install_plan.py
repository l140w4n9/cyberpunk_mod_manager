# -*- coding: utf-8 -*-
"""智能安装计划：检查压缩包结构 + LLM 阅读安装说明 → 生成映射并执行。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from ..config import config
from ..installer.inspect import inspect_archive
from ..installer.rules import match_rule, resolve_target
from .summary import (
    _parse_chat_response,
    _strip_html,
    parse_llm_json_from_response,
)

logger = logging.getLogger(__name__)

_INSTALL_SECTION_MARKERS = (
    "installation",
    "install",
    "安装",
    "how to install",
    "requirements",
    "依赖",
    "compatibility",
)


def _extract_install_instructions(description: str) -> str:
    """从 Nexus 描述中提取与安装相关的段落。"""
    clean = _strip_html(description)
    if not clean:
        return ""
    lower = clean.lower()
    start = -1
    for marker in _INSTALL_SECTION_MARKERS:
        idx = lower.find(marker)
        if idx >= 0 and (start < 0 or idx < start):
            start = idx
    if start >= 0:
        return clean[start : start + 2500].strip()
    return clean[:2000].strip()


def _validate_target_rel(target_rel: str, game_root: Path) -> str:
    rel = target_rel.replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("..") or "/../" in f"/{rel}/":
        raise ValueError(f"非法目标路径: {target_rel}")
    resolved = (game_root / rel).resolve()
    if not resolved.is_relative_to(game_root.resolve()):
        raise ValueError(f"目标路径逃出游戏目录: {target_rel}")
    return rel


def mappings_from_inspection(inspection: dict) -> dict[str, str]:
    """从规则检查结果生成初始文件映射。"""
    mappings: dict[str, str] = {}
    for entry in inspection.get("entries") or []:
        if entry.get("status") == "match" and entry.get("target"):
            mappings[entry["rel"]] = entry["target"]
    return mappings


def needs_llm_plan(inspection: dict) -> bool:
    """是否存在规则无法覆盖、需要 LLM 补充的安装项。"""
    skipped = int(inspection.get("skipped_count") or 0)
    matched = int(inspection.get("matched_count") or 0)
    if matched == 0 and skipped > 0:
        return True
    if skipped > 0:
        return True
    return False


def merge_plan_mappings(
    inspection: dict,
    llm_files: list[dict[str, Any]] | None,
    *,
    game_path: Path | None = None,
) -> tuple[dict[str, str], list[dict]]:
    """合并规则映射与 LLM 建议，返回 (src→target, plan_items)。"""
    game_root = (game_path or Path(config.game_path)).resolve()
    entry_set = {e["rel"] for e in (inspection.get("entries") or [])}
    mappings = mappings_from_inspection(inspection)
    plan_items: list[dict] = [
        {
            "src": rel,
            "target": tgt,
            "source": "rule",
            "reason": "规则匹配",
        }
        for rel, tgt in mappings.items()
    ]

    if not llm_files:
        return mappings, plan_items

    for item in llm_files:
        src = _normalize_rel(str(item.get("src") or ""))
        target = _normalize_rel(str(item.get("target") or ""))
        reason = str(item.get("reason") or "LLM 建议").strip()
        if not src or not target:
            continue
        if src not in entry_set:
            continue
        target = _validate_target_rel(target, game_root)
        mappings[src] = target
        plan_items = [p for p in plan_items if p["src"] != src]
        plan_items.append(
            {
                "src": src,
                "target": target,
                "source": "llm",
                "reason": reason,
            }
        )
    return mappings, plan_items


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


async def _llm_suggest_mappings(
    *,
    mod_name: str,
    mod_id: int,
    inspection: dict,
    instructions_text: str,
) -> tuple[list[dict[str, Any]], str]:
    """调用 LLM 为 skipped 文件生成安装映射。"""
    skipped_entries = [
        e for e in (inspection.get("entries") or []) if e.get("status") == "skip"
    ]
    if not skipped_entries:
        return [], ""

    skipped_preview = json.dumps(
        [{"rel": e["rel"]} for e in skipped_entries[:60]],
        ensure_ascii=False,
    )
    readme_bits = inspection.get("readme_excerpts") or []
    readme_text = "\n\n".join(
        f"[{item['path']}]\n{item['text'][:1500]}" for item in readme_bits[:3]
    )

    prompt = (
        "你是赛博朋克2077模组安装专家。根据压缩包结构、官方安装说明和 Nexus 描述，"
        "为「规则未匹配」的文件制定安装计划。\n\n"
        f"模组：{mod_name} (#{mod_id})\n"
        f"游戏根目录 game_path：{config.game_path}\n\n"
        "常见正确路径示例：\n"
        "- RED4ext 插件：red4ext/plugins/<ModName>/\n"
        "- redscript：r6/scripts/\n"
        "- TweakXL：r6/tweaks/\n"
        "- CET lua：bin/x64/plugins/cyber_engine_tweaks/mods/\n"
        "- 原生 archive：archive/pc/mod/\n"
        "- ArchiveXL 框架本体：red4ext/plugins/ArchiveXL/（含 Bundle 子目录）\n\n"
        f"Nexus 安装说明摘录：\n{instructions_text[:2000] or '（无）'}\n\n"
        f"压缩包内 readme：\n{readme_text or '（无）'}\n\n"
        f"目录树预览：\n{inspection.get('tree_preview', '')}\n\n"
        f"需要规划的文件（当前规则未匹配）：\n{skipped_preview}\n\n"
        "只输出 JSON 对象，格式：\n"
        '{"strategy":"一句话策略","files":[{"src":"压缩包内相对路径","target":"游戏目录相对路径","reason":"简短原因"}]}\n'
        "要求：src 必须来自上述列表；target 相对游戏根目录；不要包含 ..；"
        "可忽略 readme/license/图片；dll/reds/json/xml 等插件文件应给出正确目标。"
    )

    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = _parse_chat_response(resp)

    parsed = parse_llm_json_from_response(data)
    files = parsed.get("files") or []
    if not isinstance(files, list):
        files = []
    strategy = str(parsed.get("strategy") or "").strip()
    return files, strategy


async def build_install_plan(
    mod_id: int,
    archive_path: Path,
    *,
    mod_name: str = "",
    description: str = "",
    force_llm: bool = False,
) -> dict:
    """检查压缩包并生成安装计划（规则 + 可选 LLM）。"""
    inspection = inspect_archive(archive_path)
    instructions = _extract_install_instructions(description)
    for item in inspection.get("readme_excerpts") or []:
        instructions += f"\n\n[{item['path']}]\n{item['text'][:1200]}"

    llm_files: list[dict[str, Any]] = []
    strategy = ""
    plan_source = "rules"

    use_llm = bool(config.openai_api_key) and (
        force_llm or needs_llm_plan(inspection)
    )
    if use_llm:
        try:
            llm_files, strategy = await _llm_suggest_mappings(
                mod_name=mod_name or f"mod_{mod_id}",
                mod_id=mod_id,
                inspection=inspection,
                instructions_text=instructions,
            )
            if llm_files:
                plan_source = "hybrid" if inspection.get("matched_count") else "llm"
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("LLM install plan failed for mod %s: %s", mod_id, exc)
            strategy = f"LLM 规划失败，回退规则: {exc}"

    mappings, plan_items = merge_plan_mappings(inspection, llm_files)
    return {
        "mod_id": mod_id,
        "archive_path": str(archive_path),
        "plan_source": plan_source,
        "strategy": strategy,
        "inspection": {
            "entry_count": inspection.get("entry_count"),
            "matched_count": inspection.get("matched_count"),
            "skipped_count": inspection.get("skipped_count"),
            "tree_preview": inspection.get("tree_preview"),
        },
        "instructions_excerpt": instructions[:1500],
        "file_mappings": mappings,
        "plan_items": plan_items,
        "installable_count": len(mappings),
    }


async def explain_uninstall_plan(
    mod_id: int,
    plan: dict,
    *,
    mod_name: str = "",
) -> str:
    """用 LLM 解读卸载计划（执行前向用户说明）。"""
    if not config.openai_api_key:
        added = plan.get("added_files") or []
        backed = plan.get("backed_up_files") or []
        return (
            f"将删除 {len(added)} 个新增文件，"
            f"恢复 {len(backed)} 个被覆盖的原始文件。"
        )

    prompt = (
        "你是赛博朋克2077模组助手。根据以下卸载计划，用中文简要说明将执行的操作"
        "（删除哪些路径、恢复哪些备份），3-6 条 bullet，不要执行任何操作：\n"
        f"模组：{mod_name or mod_id} (#{mod_id})\n"
        f"计划 JSON：{json.dumps(plan, ensure_ascii=False)[:6000]}"
    )
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1024,
        "temperature": 0.2,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = _parse_chat_response(resp)
    from .summary import extract_llm_message_text

    return extract_llm_message_text(data, full_reasoning=False) or "（无解读）"
