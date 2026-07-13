# -*- coding: utf-8 -*-
"""本地凭据加密存储（Windows DPAPI / 其他平台文件级隔离）。"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from ..config import _user_config_dir

logger = logging.getLogger(__name__)

_SECRETS_FILE = "nexus_tokens.enc"


def _secrets_path() -> Path:
    return _user_config_dir() / _SECRETS_FILE


def _machine_key() -> bytes:
    node = str(uuid.getnode()).encode("utf-8")
    user = (os.environ.get("USERNAME") or os.environ.get("USER") or "user").encode(
        "utf-8"
    )
    return hashlib.sha256(node + user + b"cpmm-nexus-tokens-v1").digest()


def _xor_crypt(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _dpapi_encrypt(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptProtectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _dpapi_decrypt(data: bytes) -> bytes:
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_byte)),
        ]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob = DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_byte)))
    out_blob = DATA_BLOB()
    if not crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    ):
        raise OSError("CryptUnprotectData failed")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def encrypt_payload(payload: dict[str, Any]) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if os.name == "nt":
        return b"DPAPI\x00" + _dpapi_encrypt(raw)
    return b"XOR\x00" + _xor_crypt(raw, _machine_key())


def decrypt_payload(blob: bytes) -> dict[str, Any]:
    if blob.startswith(b"DPAPI\x00"):
        raw = _dpapi_decrypt(blob[6:])
    elif blob.startswith(b"XOR\x00"):
        raw = _xor_crypt(blob[4:], _machine_key())
    else:
        raise ValueError("Unknown secrets blob format")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Secrets payload must be a JSON object")
    return data


def save_secret_blob(payload: dict[str, Any]) -> Path:
    path = _secrets_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = encrypt_payload(payload)
    encoded = base64.b64encode(encrypted)
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_bytes(encoded)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def load_secret_blob() -> dict[str, Any] | None:
    path = _secrets_path()
    if not path.exists():
        return None
    try:
        encrypted = base64.b64decode(path.read_bytes())
        return decrypt_payload(encrypted)
    except Exception as exc:
        logger.warning("无法读取加密凭据: %s", exc)
        return None


def clear_secret_blob() -> None:
    path = _secrets_path()
    if path.exists():
        path.unlink(missing_ok=True)
