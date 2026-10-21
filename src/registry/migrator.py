"""Ordered, idempotent SQL migration runner (ADR-0003).

Rules:

* migrations are plain ``.sql`` files named ``NNN_name.sql`` and are applied in
  numeric order;
* every migration is wrapped in a transaction, so a failure leaves the schema at
  the previous version — a half-applied migration can never be observed;
* the applied version and the file checksum are recorded in ``schema_version``;
  a changed checksum for an already-applied version is reported as an error
  rather than silently re-running;
* re-running the runner is a no-op.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from .db import connect, default_registry_db

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

_SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version    INTEGER PRIMARY KEY,
    name       TEXT NOT NULL DEFAULT '',
    checksum   TEXT NOT NULL DEFAULT '',
    applied_at TEXT NOT NULL DEFAULT ''
);
"""


class MigrationError(RuntimeError):
    """Raised when a migration cannot be applied safely."""


def migration_files(directory: str | Path | None = None) -> list[Path]:
    """Migration files in apply order (numeric prefix ascending)."""
    base = Path(directory) if directory else MIGRATIONS_DIR
    if not base.exists():
        return []
    files = [p for p in base.glob("*.sql") if p.is_file()]
    return sorted(files, key=lambda p: (int(p.stem.split("_")[0]) if p.stem.split("_")[0].isdigit() else 0,
                                        p.name))


def _version_of(path: Path) -> int:
    head = path.stem.split("_")[0]
    if not head.isdigit():
        raise MigrationError(f"migration file name must start with a number: {path.name}")
    return int(head)


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_version(db_path: str | None = None, directory: str | Path | None = None) -> int:
    """Highest applied migration version (0 when the database is empty)."""
    conn = connect(db_path)
    try:
        conn.executescript(_SCHEMA_VERSION_DDL)
        row = conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return int(row["v"]) if row and row["v"] is not None else 0
    finally:
        conn.close()


def apply_migrations(db_path: str | None = None,
                     directory: str | Path | None = None) -> list[int]:
    """Apply every pending migration. Returns the versions that were applied.

    Idempotent: calling it twice applies nothing the second time.
    """
    files = migration_files(directory)
    conn = connect(db_path)
    applied: list[int] = []
    try:
        conn.executescript(_SCHEMA_VERSION_DDL)
        conn.commit()
        known = {int(r["version"]): r["checksum"]
                 for r in conn.execute("SELECT version, checksum FROM schema_version")}
        for path in files:
            version = _version_of(path)
            checksum = _checksum(path)
            if version in known:
                if known[version] and known[version] != checksum:
                    raise MigrationError(
                        f"migration {version} ({path.name}) changed after it was applied; "
                        "add a new migration instead of editing an applied one")
                continue
            sql = path.read_text(encoding="utf-8")
            try:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO schema_version(version, name, checksum, applied_at) "
                    "VALUES (?, ?, ?, datetime('now'))",
                    (version, path.name, checksum))
                conn.commit()
            except sqlite3.Error as e:
                conn.rollback()
                raise MigrationError(f"migration {version} ({path.name}) failed: {e}") from e
            applied.append(version)
        return applied
    finally:
        conn.close()
