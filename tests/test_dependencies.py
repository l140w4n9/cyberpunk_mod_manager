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
    collect_dependencies,
    parse_dependencies_from_text,
    sync_dependencies,
)
from cyberpunk_mod_manager.nexus.schemas import ModDetails
from cyberpunk_mod_manager.services import mod_ops
from cyberpunk_mod_manager.storage.db import get_session, init_db
from sqlmodel import select


def test_parse_dependencies_from_text() -> None:
    text = (
        'Requires <a href="https://www.nexusmods.com/cyberpunk2077/mods/107">CET</a> '
        'and https://www.nexusmods.com/cyberpunk2077/mods/1511'
    )
    deps = parse_dependencies_from_text(text, exclude_mod_id=27967)
    ids = {d["mod_id"] for d in deps}
    assert ids == {107, 1511}


@pytest.mark.asyncio
async def test_collect_dependencies_includes_known() -> None:
    deps = await collect_dependencies(27967, "", "")
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


def test_fallback_summary() -> None:
    from cyberpunk_mod_manager.services.summary import fallback_summary

    text = fallback_summary(
        "<p>Provides shared runtime layer for CET mods.</p>",
        name="0-Engine",
    )
    assert "runtime" in text.lower() or "0-Engine" in text


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
    mock_client.pick_primary_file = AsyncMock(return_value=None)
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
