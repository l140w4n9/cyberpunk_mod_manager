# -*- coding: utf-8 -*-
"""启动入口：python -m cyberpunk_mod_manager 或 uvicorn 方式启动。"""
from __future__ import annotations

import os
import socket
import sys

import uvicorn

from .api.app import app
from .config import config


def _pick_port(preferred: int = 8000, attempts: int = 10) -> int:
    """选择可用端口，避免端口占用导致进程直接退出。"""
    env_port = os.environ.get("CP2077_PORT", "").strip()
    if env_port.isdigit():
        return int(env_port)
    for port in range(preferred, preferred + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def main() -> None:
    port = _pick_port()
    if config.config_file:
        print(f"配置文件: {config.config_file}")
    else:
        print("未找到配置文件，请在前端「设置」页保存配置。")
    if port != 8000:
        print(f"端口 8000 已被占用，改用 http://127.0.0.1:{port}")
    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    except OSError as exc:
        print(f"服务启动失败: {exc}", file=sys.stderr)
        print("若端口被占用，可设置环境变量 CP2077_PORT=8001 后重试。", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
