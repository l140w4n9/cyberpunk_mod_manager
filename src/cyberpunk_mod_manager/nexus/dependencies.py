# -*- coding: utf-8 -*-
"""模组依赖解析与同步。"""
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from sqlmodel import select

from ..config import config
from ..models import Mod, ModDependency
from ..services.concurrency import DEFAULT_CONCURRENCY, gather_bounded
from ..storage.db import get_session
from .client import GAME_DOMAIN, GRAPHQL_URL, _build_headers, NexusClient

MOD_REQUIREMENTS_QUERY = """
query ModRequirements($modId: ID!, $gameId: ID!) {
  mod(modId: $modId, gameId: $gameId) {
    legacyModRequirementsEnabled
    modRequirements {
      nexusRequirements {
        nodes {
          modId
          modName
          notes
          externalRequirement
          url
        }
      }
    }
  }
}
"""

OPTIONAL_NOTES_RE = re.compile(
    r"\b(optional|recommended|recommend|可选|推荐)\b",
    re.IGNORECASE,
)

_game_id_cache: int | None = None

NEXUS_MOD_LINK_RE = re.compile(
    r"nexusmods\.com/(?:games/)?cyberpunk2077/mods/(\d+)",
    re.IGNORECASE,
)

# 描述里指向其他模组但非前置依赖的语境（如前作、致谢、捐赠等）
NON_DEPENDENCY_CONTEXT_RE = re.compile(
    r"(successor\s+to|predecessor|replacing|replaced\s+by|old\s+version|"
    r"previous\s+version|also\s+see|my\s+other\s+mod|credit|thanks\s+to|"
    r"donat|buy\s*me\s*a\s*coffee|inspired\s+by|similar\s+to|"
    r"which\s+was\s+set\s+to\s+hidden|hidden\s+a\s+long\s+time\s+ago|"
    r"前身|旧版|捐赠|感谢)",
    re.IGNORECASE,
)

REQUIREMENT_CONTEXT_RE = re.compile(
    r"(require|required|dependency|dependencies|prerequisite|needs?|must\s+have|"
    r"install\s+first|before\s+install|mandatory|前置|依赖|必装|需要先安装)",
    re.IGNORECASE,
)

# 可选依赖（替代品/增强包，非必装）
OPTIONAL_DEPENDENCY_IDS: dict[int, set[int]] = {
    23032: {24453},  # NC Mediascape Enhancer 为替代增强，非硬前置
}

OPTIONAL_CONTEXT_RE = re.compile(
    r"(alternative|optional|instead|recommend(?:ed)?|enhancer|mediascape|"
    r"替代|可选|增强|推荐)",
    re.IGNORECASE,
)

# 社区常见前置（Nexus 无结构化依赖 API 时的补充）
KNOWN_MOD_DEPENDENCIES: dict[int, list[dict[str, str | int]]] = {
    27967: [
        {"mod_id": 107, "name": "Cyber Engine Tweaks"},
        {"mod_id": 7780, "name": "Codeware"},
        {"mod_id": 1511, "name": "redscript"},
    ],
}


@dataclass
class DependencyInfo:
    nexus_mod_id: int
    name: str
    source: str
    installed: bool = False
    status: str = "not_installed"

    def to_dict(self) -> dict:
        return {
            "nexus_mod_id": self.nexus_mod_id,
            "name": self.name,
            "source": self.source,
            "installed": self.installed,
            "status": self.status,
            "optional": self.source == "optional",
        }


@dataclass
class DependentInfo:
    """反向依赖：哪些模组依赖当前模组。"""

    nexus_mod_id: int
    name: str
    installed: bool = False
    status: str = "not_installed"

    def to_dict(self) -> dict:
        return {
            "nexus_mod_id": self.nexus_mod_id,
            "name": self.name,
            "installed": self.installed,
            "status": self.status,
        }


def _is_non_dependency_context(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 160): match_start + 40]
    return bool(NON_DEPENDENCY_CONTEXT_RE.search(window))


def _is_requirement_context(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - 200): match_start + 80]
    return bool(REQUIREMENT_CONTEXT_RE.search(window))


async def _get_game_id() -> int | None:
    """查询 cyberpunk2077 的 GraphQL gameId（带内存缓存）。"""
    global _game_id_cache
    if _game_id_cache is not None:
        return _game_id_cache
    headers = {
        **_build_headers(config.nexus_api_key),
        "Content-Type": "application/json",
    }
    query = """
    query GameId($domain: String!) {
      game(domainName: $domain) {
        id
        domainName
      }
    }
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                GRAPHQL_URL,
                headers=headers,
                json={"query": query, "variables": {"domain": GAME_DOMAIN}},
            )
        if response.is_error:
            return None
        body = response.json()
        node = body.get("data", {}).get("game")
        if node and (node.get("domainName") or "").lower() == GAME_DOMAIN:
            _game_id_cache = int(node["id"])
            return _game_id_cache
    except Exception:
        return None
    return None


def _nexus_requirement_source(notes: str, external: bool) -> str:
    if external:
        return "external"
    if OPTIONAL_NOTES_RE.search(notes or ""):
        return "optional"
    return "nexus"


async def fetch_materialized_mod_dependencies(
    game_scoped_mod_id: int,
    *,
    version_id: str | None = None,
) -> list[dict]:
    """通过 v3 物化依赖 API 获取文件级前置。"""
    try:
        async with NexusClient() as client:
            target_version = version_id
            if not target_version:
                primary = await client.resolve_target_version(game_scoped_mod_id)
                target_version = primary.version_id if primary else None
            if not target_version:
                return []
            deps = await client.get_materialized_dependencies(target_version)
    except Exception:
        return []

    return [
        {
            "mod_id": dep.mod_id,
            "name": dep.name,
            "source": "materialized",
            "definition_id": dep.definition_id,
            "version_id": dep.version_id,
            "version": dep.version,
        }
        for dep in deps
    ]


async def fetch_materialized_dependencies_batch(
    version_ids: list[str],
) -> dict[str, list[dict]]:
    if not version_ids:
        return {}
    try:
        async with NexusClient() as client:
            grouped = await client.get_materialized_dependencies_batch(version_ids)
    except Exception:
        return {}
    result: dict[str, list[dict]] = {}
    for source_id, deps in grouped.items():
        result[source_id] = [
            {
                "mod_id": dep.mod_id,
                "name": dep.name,
                "source": "materialized",
                "definition_id": dep.definition_id,
                "version_id": dep.version_id,
            }
            for dep in deps
        ]
    return result


async def fetch_nexus_mod_requirements(mod_id: int) -> list[dict]:
    """从 Nexus GraphQL 拉取作者在页面上登记的 Nexus requirements（legacy 模型）。"""
    game_id = await _get_game_id()
    if game_id is None:
        return []
    headers = {
        **_build_headers(config.nexus_api_key),
        "Content-Type": "application/json",
    }
    payload = {
        "query": MOD_REQUIREMENTS_QUERY,
        "variables": {"modId": str(mod_id), "gameId": str(game_id)},
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(GRAPHQL_URL, headers=headers, json=payload)
        if response.is_error:
            return []
        body = response.json()
        if body.get("errors"):
            return []
        mod_node = body.get("data", {}).get("mod") or {}
        nodes = (
            mod_node.get("modRequirements", {})
            .get("nexusRequirements", {})
            .get("nodes", [])
        )
        legacy_enabled = mod_node.get("legacyModRequirementsEnabled")
    except Exception:
        return []

    deps: list[dict] = []
    for node in nodes:
        if node.get("externalRequirement"):
            continue
        dep_id = int(node.get("modId") or 0)
        if not dep_id or dep_id == mod_id:
            continue
        notes = str(node.get("notes") or "")
        deps.append(
            {
                "mod_id": dep_id,
                "name": str(node.get("modName") or "").strip(),
                "source": _nexus_requirement_source(notes, False),
                "notes": notes,
                "legacy_requirements": legacy_enabled,
            }
        )
    return deps


def _resolve_dep_source(owner_mod_id: int, dep_id: int, text: str, match_start: int) -> str:
    if dep_id in OPTIONAL_DEPENDENCY_IDS.get(owner_mod_id, set()):
        return "optional"
    window = text[max(0, match_start - 240): match_start + 120]
    if OPTIONAL_CONTEXT_RE.search(window):
        return "optional"
    return "parsed"


def parse_dependencies_from_text(
    text: str,
    *,
    exclude_mod_id: int | None = None,
    owner_mod_id: int | None = None,
    strict: bool = False,
) -> list[dict]:
    """从描述/HTML 文本中解析 Nexus 模组链接。"""
    found: dict[int, dict] = {}
    for match in NEXUS_MOD_LINK_RE.finditer(text or ""):
        dep_id = int(match.group(1))
        if exclude_mod_id and dep_id == exclude_mod_id:
            continue
        match_start = match.start()
        if _is_non_dependency_context(text or "", match_start):
            continue
        if strict and not _is_requirement_context(text or "", match_start):
            continue
        source = "parsed"
        if owner_mod_id is not None:
            source = _resolve_dep_source(
                owner_mod_id, dep_id, text or "", match_start
            )
        found.setdefault(
            dep_id,
            {"mod_id": dep_id, "name": "", "source": source},
        )
    return list(found.values())


def _lookup_mod_name(session, nexus_mod_id: int) -> str:
    mod = session.exec(
        select(Mod).where(Mod.nexus_mod_id == nexus_mod_id)
    ).first()
    if mod is None:
        return ""
    return (mod.name or "").strip()


def enrich_dependency_names_sync() -> int:
    """从库存模组表补全空的依赖名称。"""
    updated = 0
    with get_session() as session:
        records = session.exec(select(ModDependency)).all()
        for rec in records:
            if (rec.dep_name or "").strip():
                continue
            name = _lookup_mod_name(session, rec.dep_nexus_mod_id)
            if name:
                rec.dep_name = name
                session.add(rec)
                updated += 1
        if updated:
            session.commit()
    return updated


async def enrich_dependency_names_from_nexus() -> int:
    """通过 Nexus API 补全仍无名称的依赖。"""
    with get_session() as session:
        missing_ids = {
            rec.dep_nexus_mod_id
            for rec in session.exec(select(ModDependency)).all()
            if not (rec.dep_name or "").strip()
        }
    if not missing_ids:
        return 0

    names: dict[int, str] = {}
    try:
        async with NexusClient() as client:
            async def fetch_name(dep_id: int) -> tuple[int, str]:
                try:
                    details = await client.get_mod_details(dep_id)
                    return dep_id, (details.name or "").strip()
                except Exception:
                    return dep_id, ""

            pairs = await gather_bounded(
                [fetch_name(dep_id) for dep_id in missing_ids],
                concurrency=DEFAULT_CONCURRENCY,
            )
            names = {dep_id: name for dep_id, name in pairs if name}
    except Exception:
        return 0

    updated = 0
    with get_session() as session:
        for rec in session.exec(select(ModDependency)).all():
            if (rec.dep_name or "").strip():
                continue
            name = names.get(rec.dep_nexus_mod_id, "")
            if name:
                rec.dep_name = name
                session.add(rec)
                updated += 1
        if updated:
            session.commit()
    return updated


def _resolve_dep_name(session, rec: ModDependency, dep_mod: Mod | None) -> str:
    name = (rec.dep_name or "").strip()
    if name:
        return name
    if dep_mod is not None and (dep_mod.name or "").strip():
        name = dep_mod.name.strip()
        rec.dep_name = name
        session.add(rec)
        return name
    name = _lookup_mod_name(session, rec.dep_nexus_mod_id)
    if name:
        rec.dep_name = name
        session.add(rec)
    return name


async def collect_dependencies(
    mod_id: int,
    description: str = "",
    summary: str = "",
    *,
    version_id: str | None = None,
) -> list[dict]:
    """汇总 v3 物化依赖、GraphQL legacy requirements、描述解析与内置已知依赖。

    优先级（高 → 低）：
    1. v3 ``getModFileVersionDependencyMaterialized``（文件级新模型）
    2. GraphQL ``nexusRequirements``（legacy 模组级要求）
    3. ``KNOWN_MOD_DEPENDENCIES`` 硬编码补充
    4. 描述文本链接解析（有过结构化数据时启用 strict 模式）
    """
    deps: dict[int, dict] = {}

    materialized = await fetch_materialized_mod_dependencies(
        mod_id, version_id=version_id
    )
    structured_sources = bool(materialized)

    for item in materialized:
        deps[int(item["mod_id"])] = item

    if not structured_sources:
        for item in await fetch_nexus_mod_requirements(mod_id):
            dep_id = int(item.get("mod_id") or 0)
            if not dep_id:
                continue
            deps[dep_id] = item
        structured_sources = any(
            d.get("source") in ("nexus", "optional", "materialized")
            for d in deps.values()
        )

    combined_text = f"{summary}\n{description}"
    for item in parse_dependencies_from_text(
        combined_text,
        exclude_mod_id=mod_id,
        owner_mod_id=mod_id,
        strict=structured_sources,
    ):
        dep_id = int(item["mod_id"])
        if dep_id in deps:
            continue
        deps[dep_id] = item

    for item in KNOWN_MOD_DEPENDENCIES.get(mod_id, []):
        dep_id = int(item["mod_id"])
        deps[dep_id] = {
            "mod_id": dep_id,
            "name": str(item.get("name", "")),
            "source": "known",
        }

    # 尝试为无名称依赖补全（Nexus API + 本地库存）
    missing_names = [d for d in deps.values() if not d.get("name")]
    if missing_names:
        with get_session() as session:
            for item in missing_names:
                name = _lookup_mod_name(session, int(item["mod_id"]))
                if name:
                    item["name"] = name
        missing_names = [d for d in deps.values() if not d.get("name")]
    if missing_names:
        try:
            async with NexusClient() as client:
                async def fetch_name(item: dict) -> None:
                    try:
                        details = await client.get_mod_details(int(item["mod_id"]))
                        item["name"] = details.name
                    except Exception:
                        return

                await gather_bounded(
                    [fetch_name(item) for item in missing_names],
                    concurrency=DEFAULT_CONCURRENCY,
                )
        except Exception:
            pass

    return list(deps.values())


def sync_dependencies(owner_internal_id: int, dep_items: list[dict]) -> None:
    """将依赖列表写入数据库（先清后写）。"""
    with get_session() as session:
        for old in session.exec(
            select(ModDependency).where(ModDependency.owner_mod_id == owner_internal_id)
        ).all():
            session.delete(old)
        for item in dep_items:
            dep_id = int(item.get("mod_id") or 0)
            if dep_id <= 0:
                continue
            session.add(
                ModDependency(
                    owner_mod_id=owner_internal_id,
                    dep_nexus_mod_id=int(item["mod_id"]),
                    dep_name=str(item.get("name", "")),
                    source=str(item.get("source", "parsed")),
                )
            )
        session.commit()


def get_dependency_infos(owner_nexus_mod_id: int) -> list[DependencyInfo]:
    """读取依赖及安装状态。"""
    with get_session() as session:
        owner = session.exec(
            select(Mod).where(Mod.nexus_mod_id == owner_nexus_mod_id)
        ).first()
        if owner is None:
            return []
        records = session.exec(
            select(ModDependency).where(ModDependency.owner_mod_id == owner.id)
        ).all()
        result: list[DependencyInfo] = []
        dirty = False
        for rec in records:
            dep_mod = session.exec(
                select(Mod).where(Mod.nexus_mod_id == rec.dep_nexus_mod_id)
            ).first()
            installed = False
            status = "not_installed"
            if dep_mod is not None:
                status = (
                    dep_mod.status.value
                    if hasattr(dep_mod.status, "value")
                    else str(dep_mod.status)
                )
                installed = status == "installed"
            had_name = bool((rec.dep_name or "").strip())
            name = _resolve_dep_name(session, rec, dep_mod)
            if not had_name and name:
                dirty = True
            result.append(
                DependencyInfo(
                    nexus_mod_id=rec.dep_nexus_mod_id,
                    name=name,
                    source=rec.source,
                    installed=installed,
                    status=status,
                )
            )
        if dirty:
            session.commit()
        return result


def missing_dependencies(owner_nexus_mod_id: int) -> list[DependencyInfo]:
    """未安装的必装前置依赖（不含 optional / external）。"""
    return [
        d
        for d in get_dependency_infos(owner_nexus_mod_id)
        if not d.installed and d.source not in ("optional", "external")
    ]


def optional_dependency_infos(owner_nexus_mod_id: int) -> list[DependencyInfo]:
    return [d for d in get_dependency_infos(owner_nexus_mod_id) if d.source == "optional"]


def get_dependent_infos(target_nexus_mod_id: int) -> list[DependentInfo]:
    """查询依赖此模组的其他模组（反向依赖）。"""
    from ..models import ModStatus

    with get_session() as session:
        records = session.exec(
            select(ModDependency).where(
                ModDependency.dep_nexus_mod_id == target_nexus_mod_id
            )
        ).all()
        result: list[DependentInfo] = []
        for rec in records:
            owner = session.get(Mod, rec.owner_mod_id)
            if owner is None:
                continue
            status = (
                owner.status.value
                if hasattr(owner.status, "value")
                else str(owner.status)
            )
            result.append(
                DependentInfo(
                    nexus_mod_id=owner.nexus_mod_id,
                    name=owner.name,
                    installed=status == ModStatus.INSTALLED.value,
                    status=status,
                )
            )
        return result


def installed_dependents(target_nexus_mod_id: int) -> list[DependentInfo]:
    return [d for d in get_dependent_infos(target_nexus_mod_id) if d.installed]
