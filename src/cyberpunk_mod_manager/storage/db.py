# -*- coding: utf-8 -*-
"""SQLite 存储层。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from ..config import config
from ..models import Mod, InstallRecord, Setting, ModDependency  # noqa: F401  # 注册表模型


engine = create_engine(
    f"sqlite:///{config.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    """创建所有表。"""
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
