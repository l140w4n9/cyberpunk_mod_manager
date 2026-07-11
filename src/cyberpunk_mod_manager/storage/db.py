# -*- coding: utf-8 -*-
"""SQLite 存储层。"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from ..config import ConfigError, config
from ..models import Mod, InstallRecord, Setting, ModDependency, ChatSession  # noqa: F401

_engine = None


def _create_engine():
    if not config.has_data_dir:
        raise ConfigError("data_dir 未配置，无法连接数据库")
    return create_engine(
        f"sqlite:///{config.db_path}",
        echo=False,
        connect_args={"check_same_thread": False},
    )


def get_engine():
    """惰性创建数据库引擎（data_dir 配置后才可用）。"""
    global _engine
    if _engine is None:
        _engine = _create_engine()
    return _engine


def reload_db_engine() -> None:
    """配置变更后重置数据库连接。"""
    global _engine
    _engine = None


def _migrate_columns() -> None:
    """为已有 SQLite 数据库补充新增列。"""
    with get_engine().connect() as conn:
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
    if not config.has_data_dir:
        return
    SQLModel.metadata.create_all(get_engine())
    _migrate_columns()


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
