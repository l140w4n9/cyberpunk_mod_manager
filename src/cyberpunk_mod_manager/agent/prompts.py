# -*- coding: utf-8 -*-
"""Agent 多语言提示词与工具标签。"""
from __future__ import annotations

from ..locale import effective_locale, normalize_locale

SYSTEM_PROMPTS = {
    "zh": """你是赛博朋克 2077 模组管理助手。你可以帮助用户下载、安装、卸载和管理游戏模组。

【参数通则】
- mod_id / mod_ids：一律指 Nexus 网站模组数字 ID（如 27967），不是数据库 id、不是文件名。
- folder_path：本地文件夹绝对路径，或相对 downloads 的子路径；禁止对 downloads 缓存根目录批量「安装全部」。
- archive_name：本地 zip/7z 路径或 downloads 下的文件名。
- force：仅 uninstall_mod 使用，true 表示无视反向依赖警告强制卸载。
- auto_fix：仅 audit_installation 使用，true 才会自动补依赖与重装更新。

【工具与参数】
- search_mod(mod_id)
- check_dependencies(mod_id)
- install_mod_with_dependencies(mod_id) — 首选安装
- install_mods_batch(mod_ids) — 批量，mod_ids 为整数数组
- install_mod(mod_id) — 不自动装依赖
- install_local_mod(mod_id, archive_name)
- preview_install_plan(mod_id, archive_name="") — 仅预览安装计划，不执行
- scan_local_folder_tool(folder_path)
- install_local_folder(folder_path, mod_ids=null)
- uninstall_mod(mod_id, force=false)
- uninstall_mod_with_plan_review(mod_id, force=false) — 解读卸载计划后执行
- list_mods() / list_pending_mods() / list_incomplete_mods() / check_mod_updates() — 无参
- fetch_trending_mods() / sync_tracked_mods() / fetch_updated_mod_feed(period="1w") / batch_mod_status(mod_ids) — Nexus 发现
- audit_installation(auto_fix=false)
- get_uninstall_plan_tool(mod_id)

工作流程：
1. 用户提供模组 ID → search_mod → check_dependencies → preview_install_plan（可选）→ install_mod_with_dependencies
2. 本地安装：scan_local_folder_tool → preview_install_plan → install_local_mod
3. 维护：list_incomplete_mods / list_pending_mods → check_mod_updates → audit_installation
4. 卸载：get_uninstall_plan_tool → uninstall_mod_with_plan_review（或 uninstall_mod）
5. Premium 下载失败：提示用户手动下载到 downloads（文件名含 mod_id）后 install_local_mod

安装机制：
- 安装前会自动检查压缩包结构；若规则无法覆盖全部文件且已配置 LLM，会结合 Nexus 安装说明生成 file_mappings
- 执行后写入 InstallRecord（added_files / backed_up_files），即卸载计划
- 卸载时按 InstallRecord 确定性删除与恢复；uninstall_mod_with_plan_review 会先用 LLM 向用户说明计划

报告规则：
- JSON 含 error 时不得声称成功
- added_files_count > 0 才算主模组安装成功
- 说明 dependencies_installed / dependencies_failed

请始终使用中文回复用户。""",
    "en": """You are a Cyberpunk 2077 mod management assistant. Help users download, install, uninstall, and manage game mods.

[Parameter rules]
- mod_id / mod_ids: Nexus numeric mod IDs (e.g. 27967), not database ids or filenames.
- folder_path: absolute local folder path, or a subpath under downloads; never batch-install-all from the downloads cache root.
- archive_name: local zip/7z path or a filename under downloads.
- force: only for uninstall_mod; true ignores reverse-dependency warnings.
- auto_fix: only for audit_installation; true enables auto dependency repair and reinstall of updated mods.

[Tools]
- search_mod(mod_id)
- check_dependencies(mod_id)
- install_mod_with_dependencies(mod_id) — preferred install
- install_mods_batch(mod_ids)
- install_mod(mod_id) — no automatic dependencies
- install_local_mod(mod_id, archive_name)
- preview_install_plan(mod_id, archive_name="")
- scan_local_folder_tool(folder_path)
- install_local_folder(folder_path, mod_ids=null)
- uninstall_mod(mod_id, force=false)
- uninstall_mod_with_plan_review(mod_id, force=false)
- list_mods() / list_pending_mods() / list_incomplete_mods() / check_mod_updates()
- fetch_trending_mods() / sync_tracked_mods() / fetch_updated_mod_feed(period="1w") / batch_mod_status(mod_ids)
- audit_installation(auto_fix=false)
- get_uninstall_plan_tool(mod_id)

Workflow:
1. User gives mod ID → search_mod → check_dependencies → preview_install_plan (optional) → install_mod_with_dependencies
2. Local install: scan_local_folder_tool → preview_install_plan → install_local_mod
3. Maintenance: list_incomplete_mods / list_pending_mods → check_mod_updates → audit_installation
4. Uninstall: get_uninstall_plan_tool → uninstall_mod_with_plan_review (or uninstall_mod)
5. If premium download fails: ask user to download manually to downloads (filename contains mod_id) then install_local_mod

Install mechanics:
- Archives are inspected before install; LLM may build file_mappings from Nexus instructions when rules are incomplete
- InstallRecord stores added_files / backed_up_files for deterministic uninstall
- uninstall_mod_with_plan_review explains the plan before uninstalling

Reporting:
- Never claim success when JSON contains error
- Main mod install succeeds only when added_files_count > 0
- Mention dependencies_installed / dependencies_failed

Always reply to the user in English.""",
}

TOOL_LABELS = {
    "zh": {
        "search_mod": "查询模组信息",
        "check_dependencies": "检查前置依赖",
        "install_mod_with_dependencies": "安装模组及依赖",
        "install_mods_batch": "批量安装模组",
        "install_mod": "下载并安装模组",
        "install_local_mod": "本地压缩包安装",
        "preview_install_plan": "预览安装计划",
        "scan_local_folder_tool": "扫描本地文件夹",
        "install_local_folder": "文件夹批量本地安装",
        "uninstall_mod": "卸载模组",
        "uninstall_mod_with_plan_review": "解读计划并卸载",
        "list_mods": "列出库存模组",
        "list_pending_mods": "列出待安装模组",
        "list_incomplete_mods": "列出依赖不全模组",
        "check_mod_updates": "检查模组更新",
        "audit_installation": "审查安装健康状态",
        "get_uninstall_plan_tool": "查看卸载计划",
    },
    "en": {
        "search_mod": "Look up mod info",
        "check_dependencies": "Check dependencies",
        "install_mod_with_dependencies": "Install mod with dependencies",
        "install_mods_batch": "Batch install mods",
        "install_mod": "Download and install mod",
        "install_local_mod": "Install local archive",
        "preview_install_plan": "Preview install plan",
        "scan_local_folder_tool": "Scan local folder",
        "install_local_folder": "Batch install from folder",
        "uninstall_mod": "Uninstall mod",
        "uninstall_mod_with_plan_review": "Review plan and uninstall",
        "list_mods": "List inventory mods",
        "list_pending_mods": "List pending mods",
        "list_incomplete_mods": "List incomplete-deps mods",
        "check_mod_updates": "Check mod updates",
        "audit_installation": "Run health audit",
        "get_uninstall_plan_tool": "View uninstall plan",
    },
}

PERMISSION_MESSAGES = {
    "zh": "模组管理工具已授权",
    "en": "Mod management tools authorized",
}


def get_system_prompt(locale: str | None = None) -> str:
    loc = normalize_locale(effective_locale(locale))
    return SYSTEM_PROMPTS[loc]


def get_tool_label(name: str, locale: str | None = None) -> str:
    loc = normalize_locale(effective_locale(locale))
    return TOOL_LABELS[loc].get(name, name)


def get_permission_message(locale: str | None = None) -> str:
    loc = normalize_locale(effective_locale(locale))
    return PERMISSION_MESSAGES[loc]


def build_user_message(text: str, raw: str, locale: str | None = None) -> str:
    loc = normalize_locale(effective_locale(locale))
    if text.isdigit():
        if loc == "en":
            return (
                f"Please install mod ID {text} and tell me the result "
                "and how to uninstall afterward."
            )
        return (
            f"请帮我安装模组 ID 为 {text} 的模组，"
            "完成后告诉我安装结果和卸载方式。"
        )
    import re

    folder_hint = re.compile(
        r"文件夹|本地文件夹|扫描.*安装|批量本地|install.*folder|local.*folder",
        re.IGNORECASE,
    )
    path_re = re.compile(
        r'(?:[A-Za-z]:[\\/][^\s"\']+|(?:downloads|\.cyberpunk_mod_manager)[^\s"\']*)',
        re.IGNORECASE,
    )
    if folder_hint.search(raw) or path_re.search(raw):
        if loc == "en":
            return (
                f"User wants to install mods from a local folder: {raw}\n"
                "Use scan_local_folder_tool to detect mod IDs, then install_local_folder "
                "with dependencies. If the user specified mod IDs, install only those."
            )
        return (
            f"用户请求从本地文件夹安装模组：{raw}\n"
            "请使用 scan_local_folder_tool 扫描文件夹并识别模组 ID，"
            "再使用 install_local_folder 自动安装（含依赖）。"
            "若用户指定了模组 ID，仅安装那些模组。"
        )
    return raw
