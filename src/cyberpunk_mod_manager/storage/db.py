# -*- coding: utf-8 -*-
"""SQLite 存储层。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from ..config import config
from ..models import Mod, InstallRecord, Setting, ModDependency, ChatSession  # noqa: F401  # 注册表模型


engine = create_engine(
    f"sqlite:///{config.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def _migrate_columns() -> None:
    """为已有 SQLite 数据库补充新增列。"""
    with engine.connect() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(mods)").fetchall()
        columns = {row[1] for row in rows}
        if "summary_line" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE mods ADD COLUMN summary_line VARCHAR DEFAULT ''"
            )
            conn.commit()
        if "summary_source" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE mods ADD COLUMN summary_source VARCHAR DEFAULT ''"
            )
            conn.commit()


def init_db() -> None:
    """创建所有表并执行轻量迁移。"""
    SQLModel.metadata.create_all(engine)
    _migrate_columns()


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
