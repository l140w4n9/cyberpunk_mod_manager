# -*- coding: utf-8 -*-
"""Nexus OAuth 令牌持久化。"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ..storage.secrets import clear_secret_blob, load_secret_blob, save_secret_blob

_STORE_KEY = "nexus_oauth"


@dataclass
class NexusTokens:
    access_token: str
    refresh_token: str
    expires_at: float
    username: str = ""
    user_id: int = 0
    is_premium: bool = False

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.expires_at - 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "username": self.username,
            "user_id": self.user_id,
            "is_premium": self.is_premium,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NexusTokens":
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_at=float(data.get("expires_at") or 0),
            username=str(data.get("username") or ""),
            user_id=int(data.get("user_id") or 0),
            is_premium=bool(data.get("is_premium")),
        )


def has_nexus_tokens() -> bool:
    tokens = load_nexus_tokens()
    return tokens is not None and bool(tokens.access_token and tokens.refresh_token)


def load_nexus_tokens() -> NexusTokens | None:
    blob = load_secret_blob()
    if not blob:
        return None
    section = blob.get(_STORE_KEY)
    if not isinstance(section, dict):
        return None
    tokens = NexusTokens.from_dict(section)
    if not tokens.access_token or not tokens.refresh_token:
        return None
    return tokens


def save_nexus_tokens(tokens: NexusTokens) -> None:
    blob = load_secret_blob() or {}
    blob[_STORE_KEY] = tokens.to_dict()
    save_secret_blob(blob)


def clear_nexus_tokens() -> None:
    blob = load_secret_blob()
    if not blob or _STORE_KEY not in blob:
        clear_secret_blob()
        return
    blob.pop(_STORE_KEY, None)
    if blob:
        save_secret_blob(blob)
    else:
        clear_secret_blob()
