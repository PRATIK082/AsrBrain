"""Versioned pipeline configuration store (Slice 4)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

DEFAULT_CONFIG = {
    "chunking": {"chunk_size": 1200, "overlap": 200, "parent_expand": True},
    "retrieval": {"top_k": 12, "fusion": "weighted", "use_rerank": True,
                  "candidate_pool": 60, "context_budget": 1500},
    "generation": {"temperature": 0.2, "max_tokens": 512, "citation_required": True},
    "privacy": {"cloud_policy": "local_only"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_config(cfg: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(cfg, dict):
        return ["config must be an object"]
    for key in ("chunking", "retrieval", "generation", "privacy"):
        if key not in cfg:
            errors.append(f"missing section: {key}")
    if "chunking" in cfg:
        c = cfg["chunking"]
        if not isinstance(c.get("chunk_size", 0), int) or c.get("chunk_size", 0) <= 0:
            errors.append("chunk_size must be positive int")
    if "retrieval" in cfg:
        r = cfg["retrieval"]
        if r.get("top_k", 0) <= 0:
            errors.append("top_k must be positive")
        if r.get("fusion") not in ("rrf", "weighted"):
            errors.append("fusion must be rrf or weighted")
    return errors


def create_config(conn: sqlite3.Connection, config: dict, created_by: str | None = None,
                  note: str = "", activate: bool = False) -> str:
    errs = validate_config(config)
    if errs:
        raise ValueError("; ".join(errs))
    if activate:
        conn.execute("UPDATE pipeline_configs SET active = 0")
    version = (conn.execute("SELECT COALESCE(MAX(version),0) FROM pipeline_configs").fetchone()[0] or 0) + 1
    cid = "cfg-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO pipeline_configs(config_id,version,config_json,created_by,created_at,active,note) "
        "VALUES (?,?,?,?,?,?,?)",
        (cid, version, json.dumps(config), created_by, _now(), 1 if activate else 0, note))
    conn.commit()
    return cid


def get_active(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT config_id,version,config_json,created_at,note FROM pipeline_configs WHERE active=1 "
        "ORDER BY version DESC LIMIT 1").fetchone()
    if not row:
        return None
    return {"config_id": row[0], "version": row[1], "config": json.loads(row[2]),
            "created_at": row[3], "note": row[4]}


def list_configs(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT config_id,version,created_by,created_at,active,note FROM pipeline_configs "
        "ORDER BY version DESC").fetchall()
    return [{"config_id": r[0], "version": r[1], "created_by": r[2], "created_at": r[3],
             "active": bool(r[4]), "note": r[5]} for r in rows]


def activate_config(conn: sqlite3.Connection, config_id: str) -> bool:
    row = conn.execute("SELECT config_id FROM pipeline_configs WHERE config_id = ?", (config_id,)).fetchone()
    if not row:
        return False
    conn.execute("UPDATE pipeline_configs SET active = 0")
    conn.execute("UPDATE pipeline_configs SET active = 1 WHERE config_id = ?", (config_id,))
    conn.commit()
    return True


def rollback(conn: sqlite3.Connection, to_version: int | None = None) -> str | None:
    if to_version is None:
        row = conn.execute("SELECT config_id FROM pipeline_configs ORDER BY version DESC LIMIT 1 OFFSET 1").fetchone()
    else:
        row = conn.execute("SELECT config_id FROM pipeline_configs WHERE version = ?", (to_version,)).fetchone()
    if not row:
        return None
    activate_config(conn, row[0])
    return row[0]
