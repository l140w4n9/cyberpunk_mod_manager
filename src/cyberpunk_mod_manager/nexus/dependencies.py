# -*- coding: utf-8 -*-
"""模组依赖解析与同步。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlmodel import select

from ..models import Mod, ModDependency
from ..storage.db import get_session
from .client import NexusClient

NEXUS_MOD_LINK_RE = re.compile(
    r"nexusmods\.com/cyberpunk2077/mods/(\d+)",
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


def parse_dependencies_from_text(text: str, *, exclude_mod_id: int | None = None) -> list[dict]:
    """从描述/HTML 文本中解析 Nexus 模组链接。"""
    found: dict[int, dict] = {}
    for match in NEXUS_MOD_LINK_RE.finditer(text or ""):
        dep_id = int(match.group(1))
        if exclude_mod_id and dep_id == exclude_mod_id:
            continue
        found.setdefault(dep_id, {"mod_id": dep_id, "name": "", "source": "parsed"})
    return list(found.values())


async def collect_dependencies(mod_id: int, description: str = "", summary: str = "") -> list[dict]:
    """汇总解析结果与内置已知依赖。"""
    deps: dict[int, dict] = {}

    for item in parse_dependencies_from_text(
        f"{summary}\n{description}", exclude_mod_id=mod_id
    ):
        deps[int(item["mod_id"])] = item

    for item in KNOWN_MOD_DEPENDENCIES.get(mod_id, []):
        dep_id = int(item["mod_id"])
        deps[dep_id] = {
            "mod_id": dep_id,
            "name": str(item.get("name", "")),
            "source": "known",
        }

    # 尝试为无名称依赖补全
    missing_names = [d for d in deps.values() if not d.get("name")]
    if missing_names:
        try:
            async with NexusClient() as client:
                for item in missing_names:
                    details = await client.get_mod_details(int(item["mod_id"]))
                    item["name"] = details.name
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
            result.append(
                DependencyInfo(
                    nexus_mod_id=rec.dep_nexus_mod_id,
                    name=rec.dep_name,
                    source=rec.source,
                    installed=installed,
                    status=status,
                )
            )
        return result


def missing_dependencies(owner_nexus_mod_id: int) -> list[DependencyInfo]:
    return [d for d in get_dependency_infos(owner_nexus_mod_id) if not d.installed]


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
