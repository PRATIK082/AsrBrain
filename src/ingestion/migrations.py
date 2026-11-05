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
CURRENT_VERSION = 7

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


MIGRATION_V3 = [
    # Knowledge-graph store (Phase 4, G1). Same contract as the reference
    # data/graph/graph.db census (nodes/edges/trace_links), plus the v2 provenance
    # tuple on every row. Deterministic ids (see src/graph/build.py) make rebuilds
    # idempotent: same content -> same id -> INSERT OR REPLACE refreshes in place.
    """CREATE TABLE IF NOT EXISTS graph_nodes(
        node_id TEXT PRIMARY KEY, type TEXT, label TEXT, properties TEXT,
        degree INT DEFAULT 0, community TEXT, source TEXT,
        snapshot_id TEXT, content_hash TEXT, created_by TEXT, confidence REAL)""",
    """CREATE TABLE IF NOT EXISTS graph_edges(
        edge_id TEXT PRIMARY KEY, src TEXT, dst TEXT, rel TEXT, weight REAL,
        confidence REAL, is_inferred INT DEFAULT 0, inference_method TEXT,
        provenance TEXT,
        snapshot_id TEXT, content_hash TEXT, created_by TEXT)""",
    """CREATE TABLE IF NOT EXISTS trace_links(
        link_id TEXT PRIMARY KEY, source_type TEXT, source_id TEXT,
        target_type TEXT, target_id TEXT, link_type TEXT, confidence REAL,
        evidence TEXT, is_inferred INT DEFAULT 0,
        snapshot_id TEXT, created_by TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(src)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges(dst)",
    "CREATE INDEX IF NOT EXISTS idx_graph_edges_rel ON graph_edges(rel)",
    "CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(type)",
    "CREATE INDEX IF NOT EXISTS idx_trace_links_source ON trace_links(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_trace_links_target ON trace_links(target_id)",
]


MIGRATION_V6 = [
    """CREATE TABLE IF NOT EXISTS pipeline_configs(
        config_id TEXT PRIMARY KEY, version INT NOT NULL, config_json TEXT NOT NULL,
        created_by TEXT, created_at TEXT, active INT DEFAULT 0, note TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_configs_version ON pipeline_configs(version)",
    "CREATE INDEX IF NOT EXISTS idx_pipeline_configs_active ON pipeline_configs(active)",
]


MIGRATION_V7 = [
    """CREATE TABLE IF NOT EXISTS test_runs(
        run_id TEXT PRIMARY KEY, name TEXT, created_by TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS test_results(
        result_id TEXT PRIMARY KEY, run_id TEXT, test_case_id TEXT, requirement_id TEXT,
        module TEXT, status TEXT NOT NULL, message TEXT, created_at TEXT,
        FOREIGN KEY (run_id) REFERENCES test_runs(run_id))""",
    "CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_req ON test_results(requirement_id)",
    "CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status)",
    """CREATE TABLE IF NOT EXISTS defects(
        defect_id TEXT PRIMARY KEY, title TEXT NOT NULL, requirement_id TEXT,
        severity TEXT, status TEXT DEFAULT 'open', created_by TEXT, created_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_defects_req ON defects(requirement_id)",
    """CREATE TABLE IF NOT EXISTS safety_goals(
        goal_id TEXT PRIMARY KEY, asil TEXT, description TEXT, requirement_id TEXT,
        created_by TEXT, created_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_safety_goals_req ON safety_goals(requirement_id)",
    """CREATE TABLE IF NOT EXISTS model_usage(
        usage_id TEXT PRIMARY KEY, model TEXT, kind TEXT, latency_ms REAL,
        prompt_chars INT, created_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_model_usage_model ON model_usage(model)",
]


MIGRATION_V5 = [
    """CREATE TABLE IF NOT EXISTS model_providers(
        provider_id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT NOT NULL,
        kind TEXT NOT NULL, task TEXT NOT NULL, base_url TEXT, model TEXT,
        api_key_env TEXT, timeout_s REAL DEFAULT 120.0,
        data_transfer_policy TEXT DEFAULT 'local_only', enabled INT DEFAULT 1,
        created_at TEXT, updated_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_model_providers_workspace ON model_providers(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_providers_task ON model_providers(task)",
]


MIGRATION_V4 = [
    # Slice 1: authentication, authorization, and collection scoping.
    """CREATE TABLE IF NOT EXISTS users(
        user_id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, display_name TEXT,
        password_hash TEXT NOT NULL, status TEXT DEFAULT 'active',
        created_at TEXT, last_login_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS workspaces(
        workspace_id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT UNIQUE,
        created_by TEXT, created_at TEXT)""",
    """CREATE TABLE IF NOT EXISTS workspace_memberships(
        user_id TEXT NOT NULL, workspace_id TEXT NOT NULL, role TEXT NOT NULL,
        created_at TEXT, created_by TEXT,
        PRIMARY KEY (user_id, workspace_id),
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id))""",
    """CREATE TABLE IF NOT EXISTS collections(
        collection_id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, name TEXT NOT NULL,
        description TEXT, visibility TEXT DEFAULT 'private', owner_id TEXT,
        created_at TEXT, updated_at TEXT,
        FOREIGN KEY (workspace_id) REFERENCES workspaces(workspace_id),
        FOREIGN KEY (owner_id) REFERENCES users(user_id))""",
    """CREATE TABLE IF NOT EXISTS collection_documents(
        collection_id TEXT NOT NULL, document_id TEXT NOT NULL, added_by TEXT,
        added_at TEXT,
        PRIMARY KEY (collection_id, document_id),
        FOREIGN KEY (collection_id) REFERENCES collections(collection_id))""",
    """CREATE TABLE IF NOT EXISTS user_sessions(
        session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, token_hash TEXT NOT NULL,
        created_at TEXT, expires_at TEXT, last_seen_at TEXT, revoked_at TEXT,
        user_agent TEXT, ip TEXT,
        FOREIGN KEY (user_id) REFERENCES users(user_id))""",
    """CREATE TABLE IF NOT EXISTS audit_events(
        event_id TEXT PRIMARY KEY, workspace_id TEXT, actor_user_id TEXT,
        action TEXT NOT NULL, target_type TEXT, target_id TEXT,
        metadata_json TEXT DEFAULT '{}', created_at TEXT)""",
    "CREATE INDEX IF NOT EXISTS idx_workspace_memberships_user ON workspace_memberships(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_workspace_memberships_workspace ON workspace_memberships(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_collections_workspace ON collections(workspace_id)",
    "CREATE INDEX IF NOT EXISTS idx_collection_documents_doc ON collection_documents(document_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_sessions_token ON user_sessions(token_hash)",
    "CREATE INDEX IF NOT EXISTS idx_audit_events_workspace ON audit_events(workspace_id)",
    "ALTER TABLE documents ADD COLUMN owner_user_id TEXT",
    "ALTER TABLE documents ADD COLUMN workspace_id TEXT",
    "ALTER TABLE documents ADD COLUMN classification TEXT",
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
    if version < 3 <= target:
        for stmt in MIGRATION_V3:
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 3, "knowledge-graph store (additive tables + indexes)")
        version = 3
    if version < 4 <= target:
        for stmt in MIGRATION_V4:
            m = re.match(r"ALTER TABLE (\w+) ADD COLUMN (\w+)", stmt)
            if m and m.group(2) in _columns(conn, m.group(1)):
                continue
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 4, "auth, workspaces, collections, audit (Slice 1)")
        version = 4
    if version < 5 <= target:
        for stmt in MIGRATION_V5:
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 5, "model provider registry (Slice 3)")
        version = 5
    if version < 6 <= target:
        for stmt in MIGRATION_V6:
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 6, "pipeline config versioning (Slice 4)")
        version = 6
    if version < 7 <= target:
        for stmt in MIGRATION_V7:
            conn.execute(stmt)
        conn.commit()
        _record_version(conn, 7, "test results, defects, safety goals (P2)")
        version = 7
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
