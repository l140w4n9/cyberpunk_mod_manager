# -*- coding: utf-8 -*-
"""Nexus OAuth 应用凭据（仅开发者配置，不暴露给终端用户）。
"""
from __future__ import annotations

import os

# 开发者：Nexus 审批通过后在此填入 Client ID。
# 公开仓库可留空，在发布流水线或本机用环境变量注入。
NEXUS_OAUTH_CLIENT_ID = ""


def get_oauth_client_id() -> str:
    """返回当前应用的 OAuth Client ID。"""
    return (
        os.environ.get("NEXUS_OAUTH_CLIENT_ID", NEXUS_OAUTH_CLIENT_ID) or ""
    ).strip()
