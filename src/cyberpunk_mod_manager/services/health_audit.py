# -*- coding: utf-8 -*-
"""模组健康审查、更新检查与自动修复。"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

import httpx
from sqlmodel import select

from ..config import config
from ..locale import effective_locale, normalize_locale
from ..installer import get_uninstall_plan
from ..models import Mod, ModStatus
from ..nexus.client import NexusAPIError, NexusClient
from ..services import mod_ops
from ..services.concurrency import DEFAULT_CONCURRENCY, gather_bounded
from ..services.summary import _parse_chat_response, parse_llm_json_from_response
from ..storage.db import get_session

ProgressFn = Callable[[dict[str, Any]], None] | None

logger = logging.getLogger(__name__)


def _emit(on_progress: ProgressFn, **payload: Any) -> None:
    if on_progress:
        on_progress(payload)


def _load_all_mods() -> list[Mod]:
    with get_session() as session:
        return session.exec(select(Mod)).all()


def _filter_overviews(mods: list[Mod], mode: str) -> list[dict]:
    items = [mod_ops.build_mod_overview(m) for m in mods]
    if mode == "pending":
        return [item for item in items if item["status"] != ModStatus.INSTALLED.value]
    if mode == "incomplete":
        return [
            item
            for item in items
            if item["status"] == ModStatus.INSTALLED.value
            and not item.get("dependencies_satisfied", True)
        ]
    if mode == "installed":
        return [
            item
            for item in items
            if item["status"] == ModStatus.INSTALLED.value
            and item.get("dependencies_satisfied", True)
        ]
    return items


def list_pending_mods() -> str:
    """待安装模组（已入库但未装进游戏）。"""
    mods = _load_all_mods()
    items = _filter_overviews(mods, "pending")
    return json.dumps(
        {
            "count": len(items),
            "mods": items,
        },
        ensure_ascii=False,
    )


def list_incomplete_mods() -> str:
    """依赖不全模组（已安装但缺少必需依赖）。"""
    mods = _load_all_mods()
    items = _filter_overviews(mods, "incomplete")
    return json.dumps(
        {
            "count": len(items),
            "mods": items,
        },
        ensure_ascii=False,
    )


async def _check_single_mod_update(mod: Mod, client: NexusClient) -> dict[str, Any]:
    installed_version = (mod.version or "").strip()
    installed_file_id = mod.nexus_file_id
    installed_version_id = (mod.nexus_version_id or "").strip()
    try:
        details = await client.get_mod_details(mod.nexus_mod_id)
        latest = await client.resolve_target_version(mod.nexus_mod_id)
    except NexusAPIError as exc:
        return {
            "mod_id": mod.nexus_mod_id,
            "name": mod.name,
            "error": str(exc),
            "has_update": False,
        }

    if latest is None:
        return {
            "mod_id": mod.nexus_mod_id,
            "name": mod.name,
            "has_update": False,
            "reasons": ["未找到可用文件版本"],
        }

    latest_version = (latest.version or details.version or "").strip()
    latest_file_id = latest.file_id
    latest_version_id = latest.version_id
    has_update = False
    reasons: list[str] = []

    if latest_version_id and installed_version_id:
        if latest_version_id != installed_version_id:
            has_update = True
            reasons.append(
                f"版本 ID {installed_version_id} -> {latest_version_id}"
            )
    elif latest_file_id and installed_file_id and latest_file_id != installed_file_id:
        has_update = True
        reasons.append(f"文件 ID {installed_file_id} -> {latest_file_id}")
    if latest_version and installed_version and latest_version != installed_version:
        has_update = True
        reasons.append(f"版本 {installed_version} -> {latest_version}")
    elif latest_version and not installed_version:
        has_update = True
        reasons.append(f"未记录本地版本，Nexus 最新 {latest_version}")

    return {
        "mod_id": mod.nexus_mod_id,
        "name": mod.name or details.name,
        "has_update": has_update,
        "update_available": has_update,
        "reasons": reasons,
        "installed_version": installed_version,
        "latest_version": latest_version,
        "installed_file_id": installed_file_id,
        "latest_file_id": latest_file_id,
        "installed_version_id": installed_version_id,
        "latest_version_id": latest_version_id,
        "legacy_mod_requirements": details.legacy_mod_requirements,
    }


async def check_mod_updates(on_progress: ProgressFn = None) -> str:
    """检查已安装模组是否有 Nexus 更新。"""
    mods = [
        m
        for m in _load_all_mods()
        if mod_ops._status_str(m.status) == ModStatus.INSTALLED.value
    ]
    total = len(mods)
    _emit(
        on_progress,
        phase="updates",
        phase_label="检查模组更新",
        current=0,
        total=total,
        message="准备检查已安装模组更新…",
        percent=20 if total else 40,
    )
    results: list[dict[str, Any]] = []
    async with NexusClient() as client:
        async def check_one(mod: Mod) -> dict[str, Any]:
            return await _check_single_mod_update(mod, client)

        def on_checked(done: int, total_count: int, _result: dict[str, Any]) -> None:
            _emit(
                on_progress,
                phase="updates",
                phase_label="检查模组更新",
                current=done,
                total=total_count,
                message=f"已检查 {done}/{total_count} 个模组",
                percent=20 + int((done / max(total_count, 1)) * 55),
            )

        results = await gather_bounded(
            [check_one(mod) for mod in mods],
            concurrency=DEFAULT_CONCURRENCY,
            on_complete=on_checked,
        )

    updates = [item for item in results if item.get("update_available")]
    errors = [item for item in results if item.get("error")]
    _emit(
        on_progress,
        phase="done",
        phase_label="完成",
        message=f"检查完成，{len(updates)} 个模组有更新",
        percent=100,
        current=total,
        total=total,
    )
    return json.dumps(
        {
            "checked_count": len(results),
            "update_count": len(updates),
            "error_count": len(errors),
            "updates": updates,
            "errors": errors,
            "results": results,
        },
        ensure_ascii=False,
    )


def _collect_issues(mods: list[Mod]) -> dict[str, Any]:
    overviews = [mod_ops.build_mod_overview(m) for m in mods]
    pending = [o for o in overviews if o["status"] != ModStatus.INSTALLED.value]
    incomplete = [
        o
        for o in overviews
        if o["status"] == ModStatus.INSTALLED.value
        and not o.get("dependencies_satisfied", True)
    ]
    installed = [
        o
        for o in overviews
        if o["status"] == ModStatus.INSTALLED.value
    ]
    no_plan: list[dict] = []
    downloaded_not_installed: list[dict] = []
    disabled_installed: list[dict] = []
    overview_by_nexus_id = {o["nexus_mod_id"]: o for o in overviews}

    for mod in mods:
        overview = overview_by_nexus_id[mod.nexus_mod_id]
        if mod.status == ModStatus.INSTALLED and not mod.enabled:
            disabled_installed.append(overview)
        if mod.status == ModStatus.DOWNLOADED:
            downloaded_not_installed.append(overview)
        if mod.status == ModStatus.INSTALLED and mod.id is not None:
            if get_uninstall_plan(mod.id) is None:
                no_plan.append(overview)

    return {
        "pending": pending,
        "incomplete": incomplete,
        "installed_count": len(installed),
        "no_uninstall_plan": no_plan,
        "downloaded_not_installed": downloaded_not_installed,
        "disabled_installed": disabled_installed,
    }


def _rule_based_audit_summary(
    issues: dict[str, Any], updates: list[dict], *, locale: str = "zh"
) -> str:
    if normalize_locale(locale) == "en":
        return (
            f"Found {len(issues['incomplete'])} mod(s) with incomplete dependencies, "
            f"{len(issues['pending'])} pending, "
            f"{len(updates)} with updates available. "
            "Repair dependencies first, then update or install pending mods as needed."
        )
    return (
        f"检测到 {len(issues['incomplete'])} 个依赖不全、"
        f"{len(issues['pending'])} 个待安装、"
        f"{len(updates)} 个可更新模组。"
        "建议优先补全依赖，再按需更新或安装待装模组。"
    )


def _normalize_audit_report(parsed: dict[str, Any]) -> dict[str, Any]:
    summary = str(parsed.get("summary") or "").strip()
    risks = parsed.get("risks") or []
    if not isinstance(risks, list):
        risks = [str(risks)]
    recommendations = parsed.get("recommendations") or []
    if not isinstance(recommendations, list):
        recommendations = []
    return {
        "summary": summary,
        "risks": [str(item) for item in risks if item],
        "recommendations": [
            item for item in recommendations if isinstance(item, dict)
        ],
    }


async def _llm_audit_summary(
    issues: dict[str, Any],
    updates: list[dict],
    *,
    locale: str | None = None,
) -> dict[str, Any]:
    loc = effective_locale(locale)
    rule_summary = _rule_based_audit_summary(issues, updates, locale=loc)
    rule_recs = _rule_based_recommendations(issues, updates, locale=loc)

    if not config.openai_api_key:
        no_llm_msg = (
            "LLM not configured; returning rule-based results only."
            if loc == "en"
            else "未配置 LLM，仅返回规则检测结果。"
        )
        return {
            "summary": no_llm_msg,
            "recommendations": rule_recs,
            "source": "rules",
        }

    payload = {
        "pending_count": len(issues["pending"]),
        "incomplete_count": len(issues["incomplete"]),
        "no_uninstall_plan_count": len(issues["no_uninstall_plan"]),
        "downloaded_not_installed_count": len(issues["downloaded_not_installed"]),
        "disabled_installed_count": len(issues["disabled_installed"]),
        "updates_available_count": len(updates),
        "incomplete_mods": [
            {
                "mod_id": m["nexus_mod_id"],
                "name": m["name"],
                "missing": m["dependencies_missing_count"],
            }
            for m in issues["incomplete"][:12]
        ],
        "pending_mods": [
            {"mod_id": m["nexus_mod_id"], "name": m["name"], "status": m["status"]}
            for m in issues["pending"][:12]
        ],
        "updates": [
            {
                "mod_id": item.get("mod_id"),
                "name": item.get("name", ""),
                "reasons": (item.get("reasons") or [])[:2],
            }
            for item in updates[:12]
        ],
    }
    if loc == "en":
        system_prompt = (
            "You are a Cyberpunk 2077 mod management expert. "
            "Output a single JSON object only, no markdown, no extra text. "
            'Format: {"summary":"one English sentence","risks":["risk"],'
            '"recommendations":[{"action":"install_deps|reinstall|install_pending|manual",'
            '"mod_id":123,"reason":"reason in English"}]}'
        )
        user_prompt = f"Audit data: {json.dumps(payload, ensure_ascii=False)}"
    else:
        system_prompt = (
            "你是赛博朋克2077模组管理专家。"
            "只输出一个 JSON 对象，不要 markdown，不要解释。"
            '格式：{"summary":"中文一句话","risks":["风险"],"recommendations":[{"action":"install_deps|reinstall|install_pending|manual","mod_id":123,"reason":"原因"}]}'
        )
        user_prompt = f"审查数据：{json.dumps(payload, ensure_ascii=False)}"
    url = f"{config.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.openai_api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": config.model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": 1800,
        "temperature": 0.2,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = _parse_chat_response(resp)
        parsed = _normalize_audit_report(parse_llm_json_from_response(data))
        if not parsed["summary"]:
            parsed["summary"] = rule_summary
        if not parsed["recommendations"]:
            parsed["recommendations"] = rule_recs
        parsed["source"] = "ai"
        return parsed
    except Exception as exc:
        logger.warning("LLM audit failed: %s", exc)
        return {
            "summary": rule_summary,
            "recommendations": rule_recs,
            "source": "rules",
            "error": str(exc),
            "llm_fallback": True,
        }


def _rule_based_recommendations(
    issues: dict[str, Any], updates: list[dict], *, locale: str = "zh"
) -> list[dict[str, Any]]:
    loc = normalize_locale(locale)
    recs: list[dict[str, Any]] = []
    for mod in issues["incomplete"]:
        if loc == "en":
            reason = f"Missing {mod['dependencies_missing_count']} required dependencies"
        else:
            reason = f"缺少 {mod['dependencies_missing_count']} 个必需依赖"
        recs.append(
            {
                "action": "install_deps",
                "mod_id": mod["nexus_mod_id"],
                "reason": reason,
            }
        )
    for item in updates:
        default_reason = "Update available" if loc == "en" else "有可用更新"
        recs.append(
            {
                "action": "reinstall",
                "mod_id": item["mod_id"],
                "reason": "; ".join(item.get("reasons") or [default_reason]),
            }
        )
    pending_reason = "Downloaded but not installed" if loc == "en" else "已下载但未安装"
    for mod in issues["downloaded_not_installed"][:10]:
        recs.append(
            {
                "action": "install_pending",
                "mod_id": mod["nexus_mod_id"],
                "reason": pending_reason,
            }
        )
    return recs


async def _auto_fix_issues(
    issues: dict[str, Any],
    updates: list[dict],
    on_progress: ProgressFn = None,
) -> dict[str, Any]:
    fixed: list[dict] = []
    failed: list[dict] = []

    tasks: list[tuple[int, str, str]] = []
    for mod in issues["incomplete"]:
        tasks.append((mod["nexus_mod_id"], mod.get("name", ""), "install_deps"))
    for item in updates:
        if item.get("update_available"):
            tasks.append((int(item["mod_id"]), item.get("name", ""), "reinstall"))

    total = len(tasks)
    _emit(
        on_progress,
        phase="fix",
        phase_label="自动修复",
        current=0,
        total=total,
        message="准备自动修复…" if total else "无需自动修复",
        percent=88,
    )

    async def fix_one(mod_id: int, name: str, action: str) -> dict[str, Any]:
        raw = await mod_ops.install_mod_with_dependencies(
            mod_id,
            install_dependencies=True,
            allow_local_fallback=True,
            skip_installed=action == "install_deps",
        )
        data = json.loads(raw)
        entry = {"mod_id": mod_id, "action": action, "result": data}
        return entry

    def on_fixed(done: int, total_count: int, entry: dict[str, Any]) -> None:
        mod_id = entry["mod_id"]
        action = entry["action"]
        _emit(
            on_progress,
            phase="fix",
            phase_label="自动修复",
            current=done,
            total=total_count,
            message=f"已完成 {done}/{total_count}（#{mod_id} {action}）",
            percent=88 + int((done / max(total_count, 1)) * 10),
        )

    entries = await gather_bounded(
        [fix_one(mod_id, name, action) for mod_id, name, action in tasks],
        concurrency=DEFAULT_CONCURRENCY,
        on_complete=on_fixed,
    )
    for entry in entries:
        if entry["result"].get("error"):
            failed.append(entry)
        else:
            fixed.append(entry)

    return {"fixed": fixed, "failed": failed}


async def audit_installation(
    *,
    auto_fix: bool = False,
    on_progress: ProgressFn = None,
    locale: str | None = None,
) -> str:
    """审查当前模组安装健康状态，可选自动修复依赖与更新。"""
    loc = effective_locale(locale)
    _emit(
        on_progress,
        phase="scan",
        phase_label="扫描库存",
        message="正在分析本地模组状态…",
        percent=5,
    )
    mods = _load_all_mods()
    issues = _collect_issues(mods)
    _emit(
        on_progress,
        phase="scan",
        phase_label="扫描库存",
        message=(
            f"待安装 {len(issues['pending'])} 个，"
            f"依赖不全 {len(issues['incomplete'])} 个"
        ),
        percent=15,
    )

    updates_raw = await check_mod_updates(on_progress=on_progress)
    updates_data = json.loads(updates_raw)
    updates = updates_data.get("updates") or []

    _emit(
        on_progress,
        phase="llm",
        phase_label="AI 分析",
        message="正在生成审查建议…",
        percent=78,
    )
    llm_report = await _llm_audit_summary(issues, updates, locale=loc)
    auto_fix_result: dict[str, Any] | None = None
    if auto_fix:
        auto_fix_result = await _auto_fix_issues(issues, updates, on_progress=on_progress)

    healthy = (
        not issues["incomplete"]
        and not issues["no_uninstall_plan"]
        and not updates
        and not issues["downloaded_not_installed"]
    )

    _emit(
        on_progress,
        phase="done",
        phase_label="完成",
        message="审查完成",
        percent=100,
    )

    return json.dumps(
        {
            "healthy": healthy,
            "issues": {
                "pending_count": len(issues["pending"]),
                "incomplete_count": len(issues["incomplete"]),
                "no_uninstall_plan_count": len(issues["no_uninstall_plan"]),
                "downloaded_not_installed_count": len(issues["downloaded_not_installed"]),
                "disabled_installed_count": len(issues["disabled_installed"]),
                "update_count": len(updates),
            },
            "pending": issues["pending"],
            "incomplete": issues["incomplete"],
            "no_uninstall_plan": issues["no_uninstall_plan"],
            "downloaded_not_installed": issues["downloaded_not_installed"],
            "disabled_installed": issues["disabled_installed"],
            "updates": updates,
            "llm_report": llm_report,
            "auto_fix": auto_fix_result,
        },
        ensure_ascii=False,
    )
