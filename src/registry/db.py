"""Registry database access.

SQLite is the development store; PostgreSQL is the target system of record
(ADR-0010). The DDL in ``migrations/`` is portable, so the same migrations run
on both — only the connection factory differs.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def default_registry_db() -> str:
    """Path of the registry database (env ``REGISTRY_DB``)."""
    return os.environ.get("REGISTRY_DB", "data/canonical/registry.db")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    """Open the registry database with the pragmas the store relies on."""
    path = db_path or default_registry_db()
    if path != ":memory:":
        parent = Path(path).parent
        if str(parent) and not parent.exists():
            parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn
