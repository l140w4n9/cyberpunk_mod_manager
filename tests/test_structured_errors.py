# -*- coding: utf-8 -*-
"""结构化 API 错误与 mod_ops 错误码测试。"""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from cyberpunk_mod_manager.api.routes_mods import _parse_result
from cyberpunk_mod_manager.nexus.client import NexusAPIError
from cyberpunk_mod_manager.services.mod_ops import error_json, nexus_error_json


def test_error_json_includes_code() -> None:
    payload = json.loads(error_json("failed", code="MOD_TEST"))
    assert payload["error"] == "failed"
    assert payload["code"] == "MOD_TEST"


def test_nexus_error_json_maps_api_error_code() -> None:
    payload = json.loads(
        nexus_error_json(
            NexusAPIError(
                "premium required",
                code="NEXUS_PREMIUM_REQUIRED",
                status_code=403,
                is_premium_only=True,
            )
        )
    )
    assert payload["code"] == "NEXUS_PREMIUM_REQUIRED"
    assert payload["premium_only"] is True


def test_parse_result_raises_structured_http_exception() -> None:
    result = error_json(
        "需要 Premium",
        code="NEXUS_PREMIUM_REQUIRED",
        premium_only=True,
    )
    with pytest.raises(HTTPException) as exc:
        _parse_result(result)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "NEXUS_PREMIUM_REQUIRED"
    assert exc.value.detail["message"] == "需要 Premium"
    assert exc.value.detail["premium_only"] is True
