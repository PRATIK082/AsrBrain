"""Modality indexes (Part I): independent text / requirement / API / ECUC / table /
figure pools with exact-field priority for lookups (Part H), fused downstream.

Each returns (chunk_ids in rank order). RRF/weighted fusion stays in fusion.py.
"""
from __future__ import annotations
import json
import sqlite3


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
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM chunks WHERE requirement_ids LIKE ?"
    args: list = [f"%{req_id}%"]
    if release:
        q += " AND autosar_release = ?"
        args.append(release)
    rows = _rows(conn, q, args)
    conn.close()
    return rows


def api_search(canonical_db: str, api: str, release: str = "") -> list[dict]:
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    q = "SELECT * FROM chunks WHERE api_names LIKE ?"
    args: list = [f"%{api}%"]
    if release:
        q += " AND autosar_release = ?"
        args.append(release)
    rows = _rows(conn, q, args)
    conn.close()
    return rows


def ecuc_search(canonical_db: str, param: str) -> list[dict]:
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    rows = _rows(conn, "SELECT * FROM chunks WHERE ecu_parameters LIKE ?", (f"%{param}%",))
    conn.close()
    return rows


def table_search(canonical_db: str, query: str, release: str = "") -> list[dict]:
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    try:
        q = "SELECT * FROM tables WHERE (caption LIKE ? OR rows_json LIKE ?)"
        args: list = [f"%{query}%", f"%{query}%"]
        if release:
            q += " AND autosar_release = ?"
            args.append(release)
        return [dict(r) for r in conn.execute(q, args).fetchmany(20)]
    except Exception:
        return []
    finally:
        conn.close()


def figure_search(canonical_db: str, query: str) -> list[dict]:
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM figures WHERE caption LIKE ?", (f"%{query}%",)).fetchmany(20)]
    except Exception:
        return []
    finally:
        conn.close()
