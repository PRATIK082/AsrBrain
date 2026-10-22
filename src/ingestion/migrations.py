"""Versioned, reversible migrations for the canonical SQLite store.

History: the store was created by inline ``CREATE TABLE IF NOT EXISTS`` + ``INSERT OR
REPLACE`` with no version tracking, no provenance on records, and rollback by "restore the
file you remembered to copy". This module replaces that with:

* ``schema_version`` table (mirrored in ``PRAGMA user_version``) — every DDL change is a
  numbered, idempotent migration.
* ``ingest_runs`` table — every write belongs to a run (``snapshot_id``), so citations can
  name the exact ingest that produced a chunk.
* additive-only DDL — ``ALTER TABLE ... ADD COLUMN`` never rewrites user data, so each
  migration is reversible by restoring the pre-migration backup (see
  ``scripts/backup_canonical.bat`` — back up before any migration).

Version history:
* v1 — legacy schema as created by ``src/ingestion/pipeline.py::SCHEMA`` (documents,
  chunks, tables, figures, 10/20/10/12 columns, no provenance).
* v2 — provenance + run tracking: ``schema_version`` + ``ingest_runs`` tables and the new
  nullable columns on all four evidence tables. All nullable, so old writers keep working
  until they are switched (writers use explicit column lists, which work on both shapes).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

BASELINE_VERSION = 1
CURRENT_VERSION = 2

# Evidence-id layout written by the v1 pipeline: tbl-doc-<12hex>-<page>-<n>
_EVIDENCE_RE = re.compile(r"^(tbl|fig)-(doc-[0-9a-f]{12})-(\d+)-(\d+)$")

MIGRATION_V2 = [
    """CREATE TABLE IF NOT EXISTS schema_version(
        version INTEGER PRIMARY KEY, applied_at TEXT, note TEXT)""",
    """CREATE TABLE IF NOT EXISTS ingest_runs(
        snapshot_id TEXT PRIMARY KEY, started_at TEXT, pipeline_version TEXT,
        parser_name TEXT, parser_version TEXT, config_hash TEXT,
        source_fingerprint TEXT, status TEXT)""",
    "ALTER TABLE documents ADD COLUMN snapshot_id TEXT",
    "ALTER TABLE documents ADD COLUMN content_hash TEXT",
    "ALTER TABLE documents ADD COLUMN supersedes_doc_id TEXT",
    "ALTER TABLE documents ADD COLUMN created_by TEXT",
    "ALTER TABLE documents ADD COLUMN confidence REAL",
    "ALTER TABLE chunks ADD COLUMN snapshot_id TEXT",
    "ALTER TABLE chunks ADD COLUMN content_hash TEXT",
    "ALTER TABLE chunks ADD COLUMN created_by TEXT",
    "ALTER TABLE chunks ADD COLUMN confidence REAL",
    "ALTER TABLE chunks ADD COLUMN char_start INT",
    "ALTER TABLE chunks ADD COLUMN char_end INT",
    "ALTER TABLE chunks ADD COLUMN printed_page TEXT",
    "ALTER TABLE chunks ADD COLUMN line_start INT",
    "ALTER TABLE chunks ADD COLUMN line_end INT",
    "ALTER TABLE tables ADD COLUMN chunk_id TEXT",
    "ALTER TABLE tables ADD COLUMN snapshot_id TEXT",
    "ALTER TABLE tables ADD COLUMN content_hash TEXT",
    "ALTER TABLE tables ADD COLUMN created_by TEXT",
    "ALTER TABLE tables ADD COLUMN confidence REAL",
    "ALTER TABLE figures ADD COLUMN chunk_id TEXT",
    "ALTER TABLE figures ADD COLUMN snapshot_id TEXT",
    "ALTER TABLE figures ADD COLUMN content_hash TEXT",
    "ALTER TABLE figures ADD COLUMN created_by TEXT",
    "ALTER TABLE figures ADD COLUMN confidence REAL",
]


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """0 = fresh/unknown, 1 = legacy tables without version tracking, 2+ = migrated."""
    try:
        rows = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
        if rows and rows[0]:
            return int(rows[0])
    except Exception:
        pass
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    except Exception:
        return 0
    if {"documents", "chunks"} <= names:
        return BASELINE_VERSION
    return 0


def _record_version(conn: sqlite3.Connection, version: int, note: str) -> None:
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version("
                 "version INTEGER PRIMARY KEY, applied_at TEXT, note TEXT)")
    conn.execute("INSERT OR REPLACE INTO schema_version VALUES (?,?,?)",
                 (version, datetime.now(timezone.utc).isoformat(), note))
    try:
        conn.execute(f"PRAGMA user_version={version}")
    except Exception:
        pass


def migrate(conn: sqlite3.Connection, target: int = CURRENT_VERSION) -> int:
    """Idempotent: bring the store to ``target``. Safe to call on every writer open."""
    version = get_schema_version(conn)
    if version >= target:
        return version
    if version == 0:
        # Fresh database: lay the legacy baseline first so v1-shaped readers still work.
        from .pipeline import SCHEMA
        conn.executescript(SCHEMA)
        _record_version(conn, BASELINE_VERSION, "legacy baseline applied by migrator")
        version = BASELINE_VERSION
    if version < 2 <= target:
        for stmt in MIGRATION_V2:
            m = re.match(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", stmt)
            if m and m.group(2) in _columns(conn, m.group(1)):
                continue
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 2, "provenance + ingest_runs (additive, nullable)")
        version = 2
    conn.commit()
    return version


def new_run(conn: sqlite3.Connection, pipeline_version: str = "",
            parser_name: str = "", parser_version: str = "",
            config_hash: str = "", source_fingerprint: str = "") -> str:
    """Open an ingest run and return its snapshot_id. Every row written afterwards tags it."""
    snapshot_id = "run-" + uuid.uuid4().hex[:12]
    migrate(conn)
    conn.execute("INSERT INTO ingest_runs VALUES (?,?,?,?,?,?,?,?)",
                 (snapshot_id, datetime.now(timezone.utc).isoformat(), pipeline_version,
                  parser_name, parser_version, config_hash, source_fingerprint, "open"))
    conn.commit()
    return snapshot_id


def close_run(conn: sqlite3.Connection, snapshot_id: str, status: str = "complete") -> None:
    conn.execute("UPDATE ingest_runs SET status=? WHERE snapshot_id=?", (status, snapshot_id))
    conn.commit()


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:32]


def backfill(conn: sqlite3.Connection, pipeline_version: str = "") -> dict:
    """M3: tag every pre-provenance row with the legacy baseline run.

    * documents keep their file sha as ``content_hash`` (it already is one) and their
      ``quality`` as ``confidence``;
    * chunks get ``sha256(normalized_text)`` and inherit their document's quality as a
      documented proxy for parse confidence (per-chunk quality was never measured in v1);
    * tables/figures get a content hash over caption+payload and a best-effort ``chunk_id``
      join to the first atomic chunk on the same page (evidence ids encode doc+page).
    Returns counts. Idempotent: rows that already carry a snapshot_id are skipped.
    """
    migrate(conn)
    stats = {"documents": 0, "chunks": 0, "tables": 0, "figures": 0, "chunk_links": 0}
    legacy = "run-legacy-baseline"
    conn.execute("INSERT OR IGNORE INTO ingest_runs VALUES (?,?,?,?,?,?,?,?)",
                 (legacy, datetime.now(timezone.utc).isoformat(), pipeline_version or "v1",
                  "unknown", "", "", "", "backfilled"))
    doc_quality: dict[str, float] = {}
    for doc_id, quality in conn.execute(
            "SELECT document_id, quality FROM documents WHERE snapshot_id IS NULL").fetchall():
        doc_quality[doc_id] = quality
    conn.execute("UPDATE documents SET snapshot_id=?, content_hash=sha256, "
                 "created_by='parser', confidence=quality WHERE snapshot_id IS NULL",
                 (legacy,))
    stats["documents"] = len(doc_quality)

    rows = conn.execute("SELECT chunk_id, document_id, normalized_text FROM chunks "
                        "WHERE snapshot_id IS NULL").fetchall()
    conn.executemany(
        "UPDATE chunks SET snapshot_id=?, content_hash=?, created_by='parser', "
        "confidence=? WHERE chunk_id=?",
        [(legacy, content_hash(t or ""), doc_quality.get(d), cid) for cid, d, t in rows])
    stats["chunks"] = len(rows)

    for table, extra in (("tables", "caption || rows_json"), ("figures", "caption || kind || number")):
        try:
            erows = conn.execute(
                f"SELECT evidence_id, document_id, {extra} FROM {table} "
                "WHERE snapshot_id IS NULL").fetchall()
        except Exception:
            continue
        for eid, doc_id, payload in erows:
            conn.execute(f"UPDATE {table} SET snapshot_id=?, content_hash=?, "
                         "created_by='parser' WHERE evidence_id=?",
                         (legacy, content_hash(payload or ""), eid))
            m = _EVIDENCE_RE.match(eid or "")
            if m:
                page_idx = int(m.group(3))
                hit = conn.execute("SELECT chunk_id FROM chunks WHERE document_id=? "
                                   "AND pdf_page_index=? AND chunk_kind='atomic' "
                                   "ORDER BY page_start LIMIT 1",
                                   (m.group(2), page_idx)).fetchone()
                if hit:
                    conn.execute(f"UPDATE {table} SET chunk_id=? WHERE evidence_id=?",
                                 (hit[0], eid))
                    stats["chunk_links"] += 1
        stats[table] = len(erows)
    conn.commit()
    return stats
