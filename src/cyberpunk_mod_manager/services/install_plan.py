# -*- coding: utf-8 -*-
"""智能安装计划：LLM 阅读压缩包结构与安装说明生成映射；规则仅作回退。"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

import httpx

from ..config import config
from ..installer.inspect import inspect_archive
from ..installer.profile import get_install_profile
from .summary import (
    _parse_chat_response,
    _strip_html,
    parse_llm_json_from_response,
)

logger = logging.getLogger(__name__)

InstallPlanMode = Literal["llm_first", "hybrid", "rules_only"]

_INSTALL_SECTION_MARKERS = (
    "installation",
    "install",
    "安装",
    "how to install",
    "requirements",
    "依赖",
    "compatibility",
    "manual",
    "readme",
)

_SKIP_NAME_HINTS = (
    "readme",
    "changelog",
    "credits",
    "license",
    "screenshot",
    "preview",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
)


def effective_install_plan_mode() -> InstallPlanMode:
    """解析实际安装计划模式（未配置 LLM 时强制 rules_only）。"""
    mode = str(getattr(config, "install_plan_mode", "llm_first") or "llm_first")
    if mode not in ("llm_first", "hybrid", "rules_only"):
        mode = "llm_first"
    if not config.openai_api_key:
        return "rules_only"
    return mode  # type: ignore[return-value]


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
        return clean[start : start + 3000].strip()
    return clean[:2500].strip()


def _normalize_rel(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _validate_target_rel(target_rel: str, game_root: Path) -> str:
    rel = target_rel.replace("\\", "/").lstrip("/")
    if not rel or rel.startswith("..") or "/../" in f"/{rel}/":
        raise ValueError(f"非法目标路径: {target_rel}")
    resolved = (game_root / rel).resolve()
    if not resolved.is_relative_to(game_root.resolve()):
        raise ValueError(f"目标路径逃出游戏目录: {target_rel}")
    return rel


def mappings_from_inspection(inspection: dict) -> dict[str, str]:
    """从规则检查结果生成文件映射（回退用）。"""
    mappings: dict[str, str] = {}
    for entry in inspection.get("entries") or []:
        if entry.get("status") == "match" and entry.get("target"):
            mappings[entry["rel"]] = entry["target"]
    return mappings


def needs_llm_plan(inspection: dict) -> bool:
    """hybrid 模式：是否存在规则未覆盖的文件。"""
    return int(inspection.get("skipped_count") or 0) > 0


def _archive_inventory_for_llm(inspection: dict, *, limit: int = 180) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in inspection.get("entries") or []:
        rel = str(entry.get("rel") or "")
        if not rel:
            continue
        rows.append(
            {
                "src": rel,
                "normalized": str(entry.get("normalized_rel") or rel),
                "rule_status": str(entry.get("status") or ""),
                "rule_target": str(entry.get("target") or ""),
            }
        )
    if len(rows) > limit:
        return rows[:limit]
    return rows


def _build_llm_prompt(
    *,
    mod_name: str,
    mod_id: int,
    inspection: dict,
    instructions_text: str,
    scope: Literal["full", "skipped"],
) -> str:
    profile = get_install_profile()
    preserve_hint = "\n".join(
        f"- {prefix}" for prefix in profile.preserve_prefix_strings[:16]
    )
    readme_bits = inspection.get("readme_excerpts") or []
    readme_text = "\n\n".join(
        f"[{item['path']}]\n{item['text'][:2000]}" for item in readme_bits[:4]
    )
    inventory = _archive_inventory_for_llm(inspection)
    if scope == "skipped":
        inventory = [row for row in inventory if row["rule_status"] == "skip"]
    inventory_json = json.dumps(inventory, ensure_ascii=False)

    return (
        "你是赛博朋克2077模组安装专家。请根据压缩包结构、Nexus 描述与 readme，"
        "制定**完整、可执行**的安装计划（将压缩包内文件复制到游戏目录）。\n\n"
        "原则：\n"
        "1. 以官方安装说明为准；说明要求「解压到游戏根目录」或「拖入 bin 文件夹」时，"
        "保留压缩包内已有目录结构（如 bin/x64/、red4ext/、archive/pc/mod/）。\n"
        "2. 框架包（CET、RED4ext、ArchiveXL 等）不要只复制零散文件，应保留子目录。\n"
        "3. 仅跳过纯文档/截图/宣传图；dll、asi、archive、xl、reds、lua、json、ini、toml 等"
        "游戏相关文件必须安装。\n"
        "4. src 必须使用下列 inventory 中的原始 src 路径（不是 normalized）。\n"
        "5. target 为相对游戏根目录的路径，不要含 ..。\n\n"
        f"模组：{mod_name} (#{mod_id})\n"
        f"游戏根目录：{config.game_path}\n"
        f"游戏档案：{profile.game_domain} ({profile.display_name})\n"
        f"已检测外层目录剥离层数：{inspection.get('wrapper_strip_depth', 0)} "
        "（normalized 列已考虑该剥离，规划时 src 仍用原始路径）\n\n"
        "常见目录参考（说明与结构冲突时以说明为准）：\n"
        f"{preserve_hint or '（无）'}\n\n"
        f"Nexus 描述/安装说明：\n{instructions_text[:3500] or '（无）'}\n\n"
        f"压缩包 readme：\n{readme_text or '（无）'}\n\n"
        f"目录树：\n{inspection.get('tree_preview', '')}\n\n"
        f"文件清单（共 {len(inventory)} 项展示，包内总计 {inspection.get('entry_count', 0)}）：\n"
        f"{inventory_json}\n\n"
        "只输出 JSON，不要 markdown：\n"
        '{"strategy":"一句话策略","files":[{"src":"压缩包内原始路径","target":"游戏内相对路径","reason":"原因"}]}\n'
        "可选字段 skip_files: string[] 列出明确不安装的 src。"
    )


async def _call_llm_install_plan(prompt: str) -> tuple[list[dict[str, Any]], str, list[str]]:
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": config.model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 8192,
        "temperature": 0.15,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = _parse_chat_response(resp)

    parsed = parse_llm_json_from_response(data)
    files = parsed.get("files") or []
    if not isinstance(files, list):
        files = []
    skip_files = parsed.get("skip_files") or []
    if not isinstance(skip_files, list):
        skip_files = []
    strategy = str(parsed.get("strategy") or "").strip()
    return files, strategy, [str(s) for s in skip_files]


def apply_llm_file_mappings(
    inspection: dict,
    llm_files: list[dict[str, Any]],
    *,
    game_path: Path | None = None,
) -> tuple[dict[str, str], list[dict]]:
    """校验并应用 LLM 输出的安装映射。"""
    game_root = (game_path or Path(config.game_path)).resolve()
    entry_set = {e["rel"] for e in (inspection.get("entries") or [])}
    mappings: dict[str, str] = {}
    plan_items: list[dict] = []

    for item in llm_files:
        src = _normalize_rel(str(item.get("src") or ""))
        target = _normalize_rel(str(item.get("target") or ""))
        reason = str(item.get("reason") or "LLM 规划").strip()
        if not src or not target:
            continue
        if src not in entry_set:
            logger.debug("LLM src not in archive, ignored: %s", src)
            continue
        try:
            target = _validate_target_rel(target, game_root)
        except ValueError as exc:
            logger.warning("LLM target rejected for %s: %s", src, exc)
            continue
        mappings[src] = target
        plan_items.append(
            {"src": src, "target": target, "source": "llm", "reason": reason}
        )
    return mappings, plan_items


def merge_plan_mappings(
    inspection: dict,
    llm_files: list[dict[str, Any]] | None,
    *,
    game_path: Path | None = None,
    prefer_llm: bool = False,
) -> tuple[dict[str, str], list[dict]]:
    """合并规则与 LLM 映射。prefer_llm=True 时 LLM 覆盖同 src 的规则。"""
    game_root = (game_path or Path(config.game_path)).resolve()
    entry_set = {e["rel"] for e in (inspection.get("entries") or [])}
    rule_mappings = mappings_from_inspection(inspection)
    plan_items: list[dict] = [
        {
            "src": rel,
            "target": tgt,
            "source": "rule",
            "reason": "规则匹配",
        }
        for rel, tgt in rule_mappings.items()
    ]
    mappings = dict(rule_mappings)

    if not llm_files:
        return mappings, plan_items

    llm_mappings, llm_items = apply_llm_file_mappings(
        inspection, llm_files, game_path=game_root
    )
    if prefer_llm:
        mappings = llm_mappings
        plan_items = llm_items
        return mappings, plan_items

    for src, tgt in llm_mappings.items():
        mappings[src] = tgt
    for item in llm_items:
        plan_items = [p for p in plan_items if p["src"] != item["src"]]
        plan_items.append(item)
    return mappings, plan_items


async def _llm_plan_install(
    *,
    mod_name: str,
    mod_id: int,
    inspection: dict,
    instructions_text: str,
    scope: Literal["full", "skipped"],
) -> tuple[list[dict[str, Any]], str]:
    prompt = _build_llm_prompt(
        mod_name=mod_name,
        mod_id=mod_id,
        inspection=inspection,
        instructions_text=instructions_text,
        scope=scope,
    )
    files, strategy, _skip = await _call_llm_install_plan(prompt)
    return files, strategy


async def build_install_plan(
    mod_id: int,
    archive_path: Path,
    *,
    mod_name: str = "",
    description: str = "",
    force_llm: bool = False,
) -> dict:
    """检查压缩包并生成安装计划。默认 LLM 主导，规则仅作回退。"""
    inspection = inspect_archive(archive_path)
    instructions = _extract_install_instructions(description)
    for item in inspection.get("readme_excerpts") or []:
        instructions += f"\n\n[{item['path']}]\n{item['text'][:1500]}"

    mode = effective_install_plan_mode()
    if force_llm and config.openai_api_key:
        mode = "llm_first"

    llm_files: list[dict[str, Any]] = []
    strategy = ""
    plan_source = "rules"
    llm_error = ""

    use_llm = mode in ("llm_first", "hybrid")
    if use_llm:
        scope: Literal["full", "skipped"] = (
            "full" if mode == "llm_first" else "skipped"
        )
        try:
            llm_files, strategy = await _llm_plan_install(
                mod_name=mod_name or f"mod_{mod_id}",
                mod_id=mod_id,
                inspection=inspection,
                instructions_text=instructions,
                scope=scope,
            )
        except (httpx.HTTPError, ValueError) as exc:
            llm_error = str(exc)
            logger.warning("LLM install plan failed for mod %s: %s", mod_id, exc)

    if mode == "llm_first" and llm_files:
        mappings, plan_items = apply_llm_file_mappings(inspection, llm_files)
        plan_source = "llm"
    elif mode == "llm_first" and not llm_files:
        mappings = mappings_from_inspection(inspection)
        plan_items = [
            {
                "src": rel,
                "target": tgt,
                "source": "rule",
                "reason": "LLM 未返回有效计划，回退规则",
            }
            for rel, tgt in mappings.items()
        ]
        plan_source = "rules_fallback"
        if llm_error:
            strategy = f"LLM 规划失败，已回退规则: {llm_error}"
        elif not config.openai_api_key:
            strategy = "未配置 LLM API Key，使用规则安装"
        else:
            strategy = strategy or "LLM 未返回可安装文件，已回退规则"
    elif mode == "hybrid" and llm_files:
        mappings, plan_items = merge_plan_mappings(inspection, llm_files)
        plan_source = "hybrid" if inspection.get("matched_count") else "llm"
    else:
        mappings, plan_items = merge_plan_mappings(inspection, llm_files or None)
        plan_source = "rules" if not llm_files else "hybrid"

    return {
        "mod_id": mod_id,
        "archive_path": str(archive_path),
        "plan_mode": mode,
        "plan_source": plan_source,
        "strategy": strategy,
        "inspection": {
            "entry_count": inspection.get("entry_count"),
            "matched_count": inspection.get("matched_count"),
            "skipped_count": inspection.get("skipped_count"),
            "wrapper_strip_depth": inspection.get("wrapper_strip_depth"),
            "tree_preview": inspection.get("tree_preview"),
            "profile_source": inspection.get("profile_source"),
        },
        "instructions_excerpt": instructions[:2000],
        "file_mappings": mappings,
        "plan_items": plan_items,
        "installable_count": len(mappings),
        "llm_error": llm_error or None,
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
