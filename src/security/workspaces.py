"""Workspace, membership, and collection helpers."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone

from .permissions import has_permission


def create_workspace(conn: sqlite3.Connection, name: str, slug: str | None, created_by: str) -> str:
    workspace_id = "ws-" + uuid.uuid4().hex[:12]
    conn.execute(
        "INSERT INTO workspaces(workspace_id,name,slug,created_by,created_at) VALUES (?,?,?,?,?)",
        (workspace_id, name, slug, created_by, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    return workspace_id


def add_member(conn: sqlite3.Connection, workspace_id: str, user_id: str, role: str,
               created_by: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO workspace_memberships(user_id,workspace_id,role,created_at,created_by) "
        "VALUES (?,?,?,?,?)",
        (user_id, workspace_id, role, datetime.now(timezone.utc).isoformat(), created_by))
    conn.commit()


def get_membership(conn: sqlite3.Connection, user_id: str, workspace_id: str) -> str | None:
    row = conn.execute(
        "SELECT role FROM workspace_memberships WHERE user_id = ? AND workspace_id = ?",
        (user_id, workspace_id)).fetchone()
    return row[0] if row else None


def list_workspaces_for_user(conn: sqlite3.Connection, user_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT w.workspace_id,w.name,w.slug,m.role FROM workspaces w "
        "JOIN workspace_memberships m ON m.workspace_id=w.workspace_id "
        "WHERE m.user_id = ?", (user_id,)).fetchall()
    return [{"workspace_id": r[0], "name": r[1], "slug": r[2], "role": r[3]} for r in rows]


def create_collection(conn: sqlite3.Connection, workspace_id: str, name: str,
                     description: str, visibility: str, owner_id: str) -> str:
    collection_id = "col-" + uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO collections(collection_id,workspace_id,name,description,visibility,owner_id,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (collection_id, workspace_id, name, description, visibility, owner_id, now, now))
    conn.commit()
    return collection_id


def list_collections(conn: sqlite3.Connection, workspace_id: str, user_id: str, role: str) -> list[dict]:
    rows = conn.execute(
        "SELECT collection_id,name,description,visibility,owner_id FROM collections "
        "WHERE workspace_id = ?", (workspace_id,)).fetchall()
    out = []
    for r in rows:
        if r[3] == "private" and r[4] != user_id and role not in ("owner", "admin"):
            continue
        out.append({"collection_id": r[0], "name": r[1], "description": r[2],
                    "visibility": r[3], "owner_id": r[4]})
    return out


def add_document_to_collection(conn: sqlite3.Connection, collection_id: str, document_id: str,
                               added_by: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO collection_documents(collection_id,document_id,added_by,added_at) "
        "VALUES (?,?,?,?)",
        (collection_id, document_id, added_by, datetime.now(timezone.utc).isoformat()))
    conn.commit()


def remove_document_from_collection(conn: sqlite3.Connection, collection_id: str, document_id: str) -> None:
    conn.execute("DELETE FROM collection_documents WHERE collection_id = ? AND document_id = ?",
                 (collection_id, document_id))
    conn.commit()


def collection_document_ids(conn: sqlite3.Connection, collection_ids: list[str]) -> set[str]:
    if not collection_ids:
        return set()
    placeholders = ",".join("?" for _ in collection_ids)
    rows = conn.execute(
        f"SELECT document_id FROM collection_documents WHERE collection_id IN ({placeholders})",
        collection_ids).fetchall()
    return {r[0] for r in rows}


def authorized_document_ids(conn: sqlite3.Connection, user_id: str, workspace_id: str,
                            role: str, collection_ids: list[str] | None = None) -> set[str]:
    # Documents in workspace owned by user or admin-visible.
    if role in ("owner", "admin"):
        rows = conn.execute(
            "SELECT document_id FROM documents WHERE workspace_id = ? OR workspace_id IS NULL",
            (workspace_id,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT document_id FROM documents WHERE (workspace_id = ? OR workspace_id IS NULL) "
            "AND (owner_user_id IS NULL OR owner_user_id = ?)",
            (workspace_id, user_id)).fetchall()
    allowed = {r[0] for r in rows}
    if collection_ids:
        coll_docs = collection_document_ids(conn, collection_ids)
        allowed = allowed & coll_docs if coll_docs else allowed
    return allowed


def log_audit(conn: sqlite3.Connection, workspace_id: str | None, actor_user_id: str | None,
              action: str, target_type: str | None = None, target_id: str | None = None,
              metadata: dict | None = None) -> None:
    import json
    conn.execute(
        "INSERT INTO audit_events(event_id,workspace_id,actor_user_id,action,target_type,target_id,metadata_json,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("evt-" + uuid.uuid4().hex[:12], workspace_id, actor_user_id, action, target_type,
         target_id, json.dumps(metadata or {}), datetime.now(timezone.utc).isoformat()))
    conn.commit()
