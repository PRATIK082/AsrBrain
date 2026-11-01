"""Modality indexes (Part I): independent text / requirement / API / ECUC / table /
figure pools with exact-field priority for lookups (Part H), fused downstream.

Each returns (chunk_ids in rank order). RRF/weighted fusion stays in fusion.py.
"""
from __future__ import annotations
import json
import sqlite3
from contextlib import contextmanager


@contextmanager
def _conn(db: str):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _rows(conn: sqlite3.Connection, q: str, args: list) -> list[dict]:
    out = []
    for r in conn.execute(q, args).fetchmany(50):
        d = dict(r)
        for k in ("requirement_ids", "api_names", "ecu_parameters"):
            if isinstance(d.get(k), str):
                try:
                    d[k] = json.loads(d[k])
                except Exception:
                    d[k] = []
        out.append(d)
    return out


def requirement_search(canonical_db: str, req_id: str, release: str = "") -> list[dict]:
    q = "SELECT * FROM chunks WHERE requirement_ids LIKE ?"
    args: list = [f"%{req_id}%"]
    if release:
        q += " AND autosar_release = ?"
        args.append(release)
    with _conn(canonical_db) as conn:
        return _rows(conn, q, args)


def table_search(canonical_db: str, query: str, release: str = "") -> list[dict]:
    try:
        with _conn(canonical_db) as conn:
            q = "SELECT * FROM tables WHERE (caption LIKE ? OR rows_json LIKE ?)"
            args: list = [f"%{query}%", f"%{query}%"]
            if release:
                q += " AND autosar_release = ?"
                args.append(release)
            return [dict(r) for r in conn.execute(q, args).fetchmany(20)]
    except Exception:
        return []


def figure_search(canonical_db: str, query: str) -> list[dict]:
    try:
        with _conn(canonical_db) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM figures WHERE caption LIKE ?", (f"%{query}%",)).fetchmany(20)]
    except Exception:
        return []
