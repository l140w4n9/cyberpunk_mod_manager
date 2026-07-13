# -*- coding: utf-8 -*-
"""Nexus OAuth JWT 校验（RFC 7519 + Nexus 公钥）。"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# https://modding.wiki/en/api/oauth2-guide
NEXUS_JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDhKHxCWOeUy38S3UOBOB11SNd/
wyL9TVvzxePkEsZb4fEVGp0U5MEcDcJgXUo/fZOYTUFMX7ipvCC7sbsyKpJ0xZ/M
l5zXMBcI03gu6p1TvG+eL0xEk6X8LD+t+GbzH9EY58bZ8kOLEx4lbAX3fNYhMhbh
HJra9ZVW2QdgHoDV6wIDAQAB
-----END PUBLIC KEY-----"""


def verify_access_token(token: str) -> dict[str, Any] | None:
    """校验并解码 Nexus access token；失败时返回 None。"""
    try:
        import jwt
    except ImportError:
        logger.warning("PyJWT 未安装，跳过 JWT 签名校验")
        return _decode_unverified(token)

    try:
        payload = jwt.decode(
            token,
            NEXUS_JWT_PUBLIC_KEY,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        logger.warning("Nexus JWT 校验失败: %s", exc)
        return None


def _decode_unverified(token: str) -> dict[str, Any] | None:
    try:
        import base64
        import json

        parts = token.split(".")
        if len(parts) < 2:
            return None
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
