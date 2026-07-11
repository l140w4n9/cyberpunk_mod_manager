# -*- coding: utf-8 -*-
"""依赖解析与本地安装回退测试。"""
from __future__ import annotations

import json
import zipfile
from unittest.mock import AsyncMock, patch

import pytest

from cyberpunk_mod_manager.config import config
from cyberpunk_mod_manager.models import Mod, ModDependency, ModStatus
from cyberpunk_mod_manager.nexus.dependencies import (
    KNOWN_MOD_DEPENDENCIES,
    _nexus_requirement_source,
    collect_dependencies,
    sync_dependencies,
)
from cyberpunk_mod_manager.nexus.client import parse_materialized_dependencies
from cyberpunk_mod_manager.nexus.schemas import ModDetails
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


@pytest.mark.asyncio
async def test_collect_dependencies_uses_nexus_requirements_only() -> None:
    mock_reqs = [
        {"mod_id": 107, "name": "Cyber Engine Tweaks", "source": "nexus"},
        {"mod_id": 21422, "name": "Native Interactions Framework", "source": "nexus"},
        {"mod_id": 4198, "name": "ArchiveXL", "source": "nexus"},
    ]
    with patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_materialized_mod_dependencies",
        new=AsyncMock(return_value=[]),
    ), patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_nexus_mod_requirements",
        new=AsyncMock(return_value=mock_reqs),
    ):
        deps = await collect_dependencies(18777)
    ids = {int(d["mod_id"]) for d in deps}
    assert ids == {107, 21422, 4198}


@pytest.mark.asyncio
async def test_collect_dependencies_ignores_description_links() -> None:
    """描述中的模组链接不再计入依赖。"""
    mock_reqs = [
        {"mod_id": 4198, "name": "ArchiveXL", "source": "nexus"},
        {"mod_id": 7780, "name": "Codeware", "source": "nexus"},
        {"mod_id": 2380, "name": "RED4ext", "source": "nexus"},
        {"mod_id": 1511, "name": "redscript", "source": "nexus"},
        {"mod_id": 4197, "name": "TweakXL", "source": "nexus"},
    ]
    with patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_materialized_mod_dependencies",
        new=AsyncMock(return_value=[]),
    ), patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_nexus_mod_requirements",
        new=AsyncMock(return_value=mock_reqs),
    ):
        deps = await collect_dependencies(11077)
    ids = {int(d["mod_id"]) for d in deps}
    assert ids == {4198, 7780, 2380, 1511, 4197}
    assert 790 not in ids
    assert 9812 not in ids


@pytest.mark.asyncio
async def test_collect_dependencies_empty_when_no_official_sources() -> None:
    with patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_materialized_mod_dependencies",
        new=AsyncMock(return_value=[]),
    ), patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_nexus_mod_requirements",
        new=AsyncMock(return_value=[]),
    ):
        deps = await collect_dependencies(99999)
    assert deps == []


def test_nexus_requirement_source_optional_notes() -> None:
    assert _nexus_requirement_source("Optional - preset", False) == "optional"
    assert _nexus_requirement_source("Mandatory", False) == "nexus"
    assert _nexus_requirement_source("", True) == "external"


def test_parse_materialized_dependencies() -> None:
    payload = {
        "dependencies": [
            {
                "id": "def-1",
                "candidate_mod_files": [
                    {
                        "id": "file-9",
                        "name": "CET",
                        "mod": {
                            "game_scoped_id": "107",
                            "name": "Cyber Engine Tweaks",
                        },
                        "candidate_versions": [
                            {
                                "id": "ver-1",
                                "version": "1.35.0",
                                "category": "main",
                                "uploaded_at": "2025-01-01T00:00:00Z",
                            }
                        ],
                    }
                ],
            }
        ]
    }
    parsed = parse_materialized_dependencies(payload)
    assert len(parsed) == 1
    assert parsed[0].mod_id == 107
    assert parsed[0].version == "1.35.0"
    assert parsed[0].version_id == "ver-1"


@pytest.mark.asyncio
async def test_collect_dependencies_prefers_materialized_over_legacy() -> None:
    with patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_materialized_mod_dependencies",
        new=AsyncMock(
            return_value=[
                {"mod_id": 107, "name": "CET", "source": "materialized"},
            ]
        ),
    ), patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_nexus_mod_requirements",
        new=AsyncMock(
            return_value=[{"mod_id": 9999, "name": "Legacy Only", "source": "nexus"}]
        ),
    ):
        deps = await collect_dependencies(12345)
    ids = {int(d["mod_id"]) for d in deps}
    assert ids == {107}
    assert deps[0]["source"] == "materialized"


@pytest.mark.asyncio
async def test_collect_dependencies_includes_known() -> None:
    with patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_materialized_mod_dependencies",
        new=AsyncMock(return_value=[]),
    ), patch(
        "cyberpunk_mod_manager.nexus.dependencies.fetch_nexus_mod_requirements",
        new=AsyncMock(return_value=[]),
    ):
        deps = await collect_dependencies(27967)
    ids = {int(d["mod_id"]) for d in deps}
    for item in KNOWN_MOD_DEPENDENCIES[27967]:
        assert int(item["mod_id"]) in ids


def test_sync_and_report_dependencies() -> None:
    init_db()
    with get_session() as session:
        owner = Mod(nexus_mod_id=27967, name="0-Engine")
        dep_mod = Mod(nexus_mod_id=107, name="CET", status=ModStatus.INSTALLED)
        session.add(owner)
        session.add(dep_mod)
        session.commit()
        session.refresh(owner)

    sync_dependencies(
        owner.id,
        [{"mod_id": 107, "name": "CET", "source": "known"}],
    )

    report = json.loads(mod_ops.check_dependencies_report(27967))
    assert report["missing_count"] == 0
    assert report["dependencies"][0]["installed"] is True


def test_reverse_dependencies_and_uninstall_safety() -> None:
    init_db()
    with get_session() as session:
        base = Mod(nexus_mod_id=9107, name="BaseLib", status=ModStatus.INSTALLED)
        child = Mod(nexus_mod_id=927967, name="ChildMod", status=ModStatus.INSTALLED)
        session.add(base)
        session.add(child)
        session.commit()
        session.refresh(base)
        session.refresh(child)

    sync_dependencies(
        child.id,
        [{"mod_id": 9107, "name": "BaseLib", "source": "known"}],
    )

    from cyberpunk_mod_manager.nexus.dependencies import get_dependent_infos

    dependents = get_dependent_infos(9107)
    assert len(dependents) == 1
    assert dependents[0].nexus_mod_id == 927967

    report = mod_ops.check_uninstall_report(9107)
    assert report["safe"] is False
    assert len(report["blocking_dependents"]) == 1


def test_optional_dependency_not_counted_as_missing() -> None:
    init_db()
    with get_session() as session:
        owner = Mod(nexus_mod_id=23032, name="2nd Amendment Sign")
        session.add(owner)
        session.commit()
        session.refresh(owner)

    sync_dependencies(
        owner.id,
        [{"mod_id": 24453, "name": "NC Mediascape", "source": "optional"}],
    )

    report = json.loads(mod_ops.check_dependencies_report(23032))
    assert report["missing_count"] == 0
    assert len(report["optional_dependencies"]) == 1
    assert mod_ops.missing_dependencies(23032) == []


@pytest.mark.asyncio
async def test_install_mod_premium_local_fallback() -> None:
    init_db()
    config.downloads_dir.mkdir(parents=True, exist_ok=True)
    archive = config.downloads_dir / "27967_0-Engine.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("test.archive", b"content")

    details = ModDetails(
        mod_id=27967,
        name="0-Engine",
        summary="framework",
        description="",
        author="author",
        version="0.18.6",
        picture_url="",
        mod_page_url="https://example.com",
    )

    mock_client = AsyncMock()
    mock_client.get_mod_details = AsyncMock(return_value=details)
    mock_client.resolve_target_version = AsyncMock(return_value=None)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    from cyberpunk_mod_manager.nexus.client import NexusAPIError

    async def fail_download(*_args, **_kwargs):
        raise NexusAPIError("premium_only", status_code=403, is_premium_only=True)

    mock_client.download_file = AsyncMock(side_effect=fail_download)

    with patch("cyberpunk_mod_manager.services.mod_ops.NexusClient", return_value=mock_client):
        with patch(
            "cyberpunk_mod_manager.services.mod_ops.download_mod",
            new=AsyncMock(
                return_value=mod_ops.error_json(
                    "premium",
                    premium_only=True,
                    status_code=403,
                )
            ),
        ):
            result = json.loads(
                await mod_ops.install_mod(27967, allow_local_fallback=True)
            )

    assert "error" not in result
    assert result.get("used_local_fallback") is True
    assert result["added_files_count"] == 1

    with get_session() as session:
        mod = session.exec(
            select(Mod).where(Mod.nexus_mod_id == 27967)
        ).first()
        assert mod is not None
        assert mod.status == ModStatus.INSTALLED
        deps = session.exec(
            select(ModDependency).where(ModDependency.owner_mod_id == mod.id)
        ).all()
        assert len(deps) >= 1
