"""Conversation + feedback store (Part D contract). SQLite, additive file."""
from __future__ import annotations
import json
import os
import sqlite3
import time
import uuid

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY, title TEXT, created_at REAL, updated_at REAL,
  slots_json TEXT DEFAULT '{}', archived INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT,
  created_at REAL, meta_json TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, conversation_id TEXT, message_idx INT,
  rating TEXT, note TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS query_log(id TEXT PRIMARY KEY, conversation_id TEXT, query TEXT,
  pipeline_version TEXT DEFAULT '', intent TEXT DEFAULT '', outcome TEXT DEFAULT '',
  evidence_ids_json TEXT DEFAULT '[]', latency_s REAL DEFAULT 0.0, llm TEXT DEFAULT '',
  confidence REAL, created_at REAL);
"""

# Answer-outcome vocabulary for the query flywheel (Phase 4). Kept in sync with
# src.generation.verification.ABSTAIN_TEMPLATE by prefix, not by import.
ABSTAIN_PREFIX = "I could not verify this answer from the indexed AUTOSAR"

QUERY_LOG_ENABLED = os.getenv("ASRBRAIN_QUERY_LOG", "1") == "1"


def classify_outcome(answer: str, clarify: bool = False,
                     citation_coverage: float | None = None) -> str:
    """Map a staged answer to ANSWERED / PARTIAL / ABSTAIN / CLARIFY."""
    if clarify:
        return "CLARIFY"
    if (answer or "").startswith(ABSTAIN_PREFIX):
        return "ABSTAIN"
    if citation_coverage is not None and citation_coverage < 1.0:
        return "PARTIAL"
    return "ANSWERED"


def _conn(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    c = sqlite3.connect(path)
    c.executescript(SCHEMA)
    return c


class ChatStore:
    def __init__(self, path: str = "data/canonical/chat.db"):
        self.path = path

    def create(self, title: str = "New conversation") -> dict:
        cid = "conv-" + uuid.uuid4().hex[:10]
        now = time.time()
        c = _conn(self.path)
        c.execute("INSERT INTO conversations VALUES (?,?,?,?,?,0)", (cid, title, now, now, "{}"))
        c.commit()
        c.close()
        return {"id": cid, "title": title}

    def list(self, include_archived: bool = False) -> list[dict]:
        c = _conn(self.path)
        q = "SELECT id, title, created_at, updated_at, archived FROM conversations"
        if not include_archived:
            q += " WHERE archived = 0"
        rows = [{"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3], "archived": r[4]}
                for r in c.execute(q + " ORDER BY updated_at DESC").fetchall()]
        c.close()
        return rows

    def get(self, cid: str) -> dict | None:
        c = _conn(self.path)
        r = c.execute("SELECT id, title, slots_json, archived FROM conversations WHERE id = ?", (cid,)).fetchone()
        if not r:
            c.close()
            return None
        msgs = [{"role": m[0], "content": m[1], "meta": json.loads(m[2] or "{}")}
                for m in c.execute("SELECT role, content, meta_json FROM messages WHERE conversation_id = ? ORDER BY created_at", (cid,)).fetchall()]
        c.close()
        return {"id": r[0], "title": r[1], "slots": json.loads(r[2] or "{}"),
                "archived": r[3], "messages": msgs}

    def patch(self, cid: str, title: str | None = None, archived: bool | None = None) -> bool:
        c = _conn(self.path)
        if title is not None:
            c.execute("UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, time.time(), cid))
        if archived is not None:
            c.execute("UPDATE conversations SET archived = ? WHERE id = ?", (1 if archived else 0, cid))
        c.commit()
        n = c.total_changes
        c.close()
        return n > 0

    def delete(self, cid: str) -> bool:
        c = _conn(self.path)
        c.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        c.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        c.commit()
        n = c.total_changes
        c.close()
        return n > 0

    def add_message(self, cid: str, role: str, content: str, meta: dict | None = None):
        c = _conn(self.path)
        c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                  ("msg-" + uuid.uuid4().hex[:10], cid, role, content, time.time(), json.dumps(meta or {})))
        c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (time.time(), cid))
        # auto-title from first user message
        row = c.execute("SELECT title FROM conversations WHERE id = ?", (cid,)).fetchone()
        if row and row[0] in ("New conversation", "") and role == "user":
            c.execute("UPDATE conversations SET title = ? WHERE id = ?", (content[:60], cid))
        c.commit()
        c.close()

    def get_slots(self, cid: str) -> dict:
        c = _conn(self.path)
        r = c.execute("SELECT slots_json FROM conversations WHERE id = ?", (cid,)).fetchone()
        c.close()
        try:
            return json.loads((r or ["{}"])[0])
        except Exception:
            return {}

    def merge_slots(self, cid: str, **slots) -> dict:
        cur = self.get_slots(cid)
        for k, v in slots.items():
            if v:
                if isinstance(v, list):
                    cur[k] = sorted(set(cur.get(k, []) + v))
                else:
                    cur[k] = v
        c = _conn(self.path)
        c.execute("UPDATE conversations SET slots_json = ? WHERE id = ?", (json.dumps(cur), cid))
        c.commit()
        c.close()
        return cur

    def add_feedback(self, cid: str, idx: int, rating: str, note: str = "") -> str:
        fid = "fb-" + uuid.uuid4().hex[:8]
        c = _conn(self.path)
        c.execute("INSERT INTO feedback VALUES (?,?,?,?,?,?)", (fid, cid, idx, rating, note, time.time()))
        c.commit()
        c.close()
        return fid

    # ---- query flywheel (Phase 4): every answered question becomes trainable data ----
    def log_query(self, cid: str, query: str, evidence_ids: list[str], outcome: str,
                  intent: str = "", pipeline_version: str = "", latency_s: float = 0.0,
                  llm: str = "", confidence: float | None = None) -> str:
        """Append one query_log row. No-op (returns "") when ASRBRAIN_QUERY_LOG != 1."""
        if not QUERY_LOG_ENABLED:
            return ""
        qid = "qlog-" + uuid.uuid4().hex[:10]
        pv = pipeline_version or os.getenv("RAG_PIPELINE_VERSION",
                                           os.getenv("ASRBRAIN_PIPELINE_VERSION", "v2"))
        c = _conn(self.path)
        c.execute("INSERT INTO query_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                  (qid, cid, query, pv, intent, outcome, json.dumps(list(evidence_ids or [])),
                   latency_s, llm, confidence, time.time()))
        c.commit()
        c.close()
        return qid

    def list_query_log(self, limit: int = 5000) -> list[dict]:
        c = _conn(self.path)
        rows = c.execute(
            "SELECT id, conversation_id, query, pipeline_version, intent, outcome,"
            " evidence_ids_json, latency_s, llm, confidence, created_at"
            " FROM query_log ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        c.close()
        out = []
        for r in rows:
            try:
                ev = json.loads(r[6] or "[]")
            except Exception:
                ev = []
            out.append({"id": r[0], "conversation_id": r[1], "query": r[2],
                        "pipeline_version": r[3], "intent": r[4], "outcome": r[5],
                        "evidence_ids": ev, "latency_s": r[7], "llm": r[8],
                        "confidence": r[9], "created_at": r[10]})
        return out

    # ---- portable session bundles: save once, resume in any later session ----
    def export_bundle(self, cid: str) -> dict | None:
        conv = self.get(cid)
        if not conv:
            return None
        return {"format": "autosar-session/1", "title": conv["title"],
                "slots": conv["slots"], "messages": conv["messages"]}

    def import_bundle(self, bundle: dict) -> dict:
        if bundle.get("format") != "autosar-session/1":
            raise ValueError("not an autosar-session bundle")
        conv = self.create(bundle.get("title", "Imported session"))
        cid = conv["id"]
        c = _conn(self.path)
        c.execute("UPDATE conversations SET slots_json = ? WHERE id = ?",
                  (json.dumps(bundle.get("slots", {})), cid))
        for m in bundle.get("messages", []):
            if m.get("role") in ("user", "assistant"):
                c.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)",
                          ("msg-" + uuid.uuid4().hex[:10], cid, m["role"],
                           m.get("content", ""), time.time(), json.dumps(m.get("meta", {}))))
        c.commit()
        c.close()
        return {"id": cid, "title": conv["title"],
                "imported_messages": len(bundle.get("messages", []))}
