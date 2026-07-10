# -*- coding: utf-8 -*-
"""启动入口：python -m cyberpunk_mod_manager 或 uvicorn 方式启动。"""
import uvicorn

from .api.app import app


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
