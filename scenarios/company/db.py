"""
Synchronous SQLite engine for the Northwind Support scenario backend.

Deliberately synchronous and file-based: tool calls execute inside a
per-call sandboxed subprocess (mediator/execution/sandbox.py), each opening
its own short-lived connection. This is a fake company, not Blackbox's own
trace store — the trace store is the real Postgres described in Section 9.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from scenarios.company.models import Base

DEFAULT_DB_PATH = Path(__file__).parent / "northwind.db"


def db_path() -> Path:
    override = os.environ.get("NORTHWIND_DB_PATH")
    return Path(override) if override else DEFAULT_DB_PATH


def get_engine(path: Path | None = None, *, echo: bool = False):
    p = path or db_path()
    return create_engine(f"sqlite:///{p}", echo=echo, future=True)


def init_db(path: Path | None = None) -> None:
    engine = get_engine(path)
    Base.metadata.create_all(engine)


def reset_db(path: Path | None = None) -> None:
    p = path or db_path()
    if p.exists():
        p.unlink()
    init_db(p)


def get_sessionmaker(path: Path | None = None) -> sessionmaker[Session]:
    engine = get_engine(path)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
