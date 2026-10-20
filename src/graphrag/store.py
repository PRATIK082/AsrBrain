"""SQLite-backed knowledge graph store for GraphRAG (nodes, edges, communities, traces).

Local-first: the whole GraphRAG capability works from a single file
(`data/canonical/graph.db`) with no server dependency.  Neo4j/Qdrant stay optional
adapters for the vector side; the graph side is deliberately self-contained so it can
run on an engineering laptop.

Every edge keeps provenance (chunk id, file, line, release) and an `is_inferred` flag:
inferred links are surfaced with their confidence and never used as normative proof.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS kg_nodes(
    node_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    label TEXT NOT NULL,
    properties TEXT DEFAULT '{}',
    degree INTEGER DEFAULT 0,
    community TEXT DEFAULT '',
    source TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS kg_nodes_type ON kg_nodes(type);
CREATE INDEX IF NOT EXISTS kg_nodes_community ON kg_nodes(community);

CREATE TABLE IF NOT EXISTS kg_edges(
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    rel TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    confidence REAL DEFAULT 0.8,
    is_inferred INTEGER DEFAULT 0,
    provenance TEXT DEFAULT '{}',
    PRIMARY KEY(src, dst, rel)
);
CREATE INDEX IF NOT EXISTS kg_edges_src ON kg_edges(src);
CREATE INDEX IF NOT EXISTS kg_edges_dst ON kg_edges(dst);
CREATE INDEX IF NOT EXISTS kg_edges_rel ON kg_edges(rel);

CREATE TABLE IF NOT EXISTS kg_communities(
    community_id TEXT PRIMARY KEY,
    title TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    member_count INTEGER DEFAULT 0,
    level INTEGER DEFAULT 0,
    properties TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS trace_links(
    link_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    link_type TEXT DEFAULT 'inferred',
    confidence REAL DEFAULT 0.5,
    evidence TEXT DEFAULT '[]',
    is_inferred INTEGER DEFAULT 1,
    created_at REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS trace_source ON trace_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS trace_target ON trace_links(target_type, target_id);
"""

NODE_TYPES = (
    "module", "requirement", "api", "ecuc_parameter", "port", "interface", "swc",
    "runnable", "connector", "function", "test_case", "document", "community",
    "concept", "error_code",
)

EDGE_TYPES = (
    "implements", "declared_in", "mentions", "co_mentioned_with", "references",
    "depends_on", "configured_by", "satisfies", "covered_by", "calls", "uses",
    "contains", "defines", "varies_in", "produced_by", "related_to",
)


def node_id(node_type: str, label: str) -> str:
    """Stable, collision-free node identity: ``<type>:<normalized label>``."""
    return f"{node_type}:{label.strip()}"


def normalize_label(label: str) -> str:
    return " ".join(str(label).split())


@dataclass
class TraceLink:
    link_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    link_type: str = "inferred"
    confidence: float = 0.5
    evidence: list[str] = field(default_factory=list)
    is_inferred: bool = True

    def to_dict(self) -> dict:
        return {"link_id": self.link_id, "source_type": self.source_type,
                "source_id": self.source_id, "target_type": self.target_type,
                "target_id": self.target_id, "link_type": self.link_type,
                "confidence": self.confidence, "evidence": list(self.evidence),
                "is_inferred": self.is_inferred}


class GraphStore:
    """Thin, explicit SQLite wrapper. No ORM, no magic, easy to inspect by hand."""

    def __init__(self, path: str = "data/canonical/graph.db") -> None:
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        # The API serves requests from a thread pool, so the connection is shared
        # across threads; SQLite runs in serialized mode and the write lock below
        # keeps the mutations atomic.
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---------------------------------------------------------------- lifecycle
    def close(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
                self.conn.close()
            except Exception:
                pass

    def __enter__(self) -> "GraphStore":
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    def clear(self) -> None:
        with self._lock:
            for table in ("kg_nodes", "kg_edges", "kg_communities", "trace_links"):
                self.conn.execute(f"DELETE FROM {table}")
            self.conn.commit()

    # ------------------------------------------------------------------- nodes
    def upsert_node(self, node_type: str, label: str, properties: dict | None = None,
                     source: str = "") -> str:
        label = normalize_label(label)
        if not label:
            return ""
        nid = node_id(node_type, label)
        props = properties or {}
        with self._lock:
            row = self.conn.execute("SELECT properties FROM kg_nodes WHERE node_id = ?",
                                    (nid,)).fetchone()
            if row:
                merged = _merge_props(json.loads(row["properties"] or "{}"), props)
                self.conn.execute(
                    "UPDATE kg_nodes SET type=?, label=?, properties=? WHERE node_id=?",
                    (node_type, label, json.dumps(merged, ensure_ascii=False), nid))
            else:
                self.conn.execute(
                    "INSERT INTO kg_nodes(node_id,type,label,properties,degree,community,source)"
                    " VALUES (?,?,?,?,0,'',?)",
                    (nid, node_type, label, json.dumps(props, ensure_ascii=False), source))
        return nid

    def get_node(self, nid: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM kg_nodes WHERE node_id = ?", (nid,)).fetchone()
        if not row:
            return None
        return _node_row_to_dict(row)

    def find_nodes(self, type: str | None = None, label_contains: str = "",
                   limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM kg_nodes WHERE 1=1"
        args: list[Any] = []
        if type:
            sql += " AND type = ?"
            args.append(type)
        if label_contains:
            sql += " AND label LIKE ?"
            args.append(f"%{label_contains}%")
        sql += " ORDER BY degree DESC, label ASC LIMIT ?"
        args.append(int(limit))
        return [_node_row_to_dict(r) for r in self.conn.execute(sql, args).fetchall()]

    def count_nodes(self, type: str | None = None) -> int:
        if type:
            r = self.conn.execute("SELECT COUNT(*) c FROM kg_nodes WHERE type=?", (type,)).fetchone()
        else:
            r = self.conn.execute("SELECT COUNT(*) c FROM kg_nodes").fetchone()
        return int(r["c"])

    # ------------------------------------------------------------------- edges
    def upsert_edge(self, src: str, dst: str, rel: str, weight: float = 1.0,
                    confidence: float = 0.8, is_inferred: bool = False,
                    provenance: dict | None = None) -> None:
        if not src or not dst or src == dst:
            return
        with self._lock:
            self.conn.execute(
                "INSERT INTO kg_edges(src,dst,rel,weight,confidence,is_inferred,provenance)"
                " VALUES (?,?,?,?,?,?,?)"
                " ON CONFLICT(src,dst,rel) DO UPDATE SET"
                " weight=MAX(kg_edges.weight, excluded.weight),"
                " confidence=MAX(kg_edges.confidence, excluded.confidence),"
                " is_inferred=MIN(kg_edges.is_inferred, excluded.is_inferred),"
                " provenance=excluded.provenance",
                (src, dst, rel, float(weight), float(confidence), 1 if is_inferred else 0,
                 json.dumps(provenance or {}, ensure_ascii=False)))

    def count_edges(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) c FROM kg_edges").fetchone()["c"])

    def edges_of(self, nid: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM kg_edges WHERE src = ? OR dst = ?", (nid, nid)).fetchall()
        out = []
        for r in rows:
            d = _edge_row_to_dict(r)
            d["direction"] = "out" if d["src"] == nid else "in"
            out.append(d)
        return out

    def neighbors(self, nid: str, depth: int = 1, limit: int = 200) -> dict:
        """BFS neighbourhood with edge + node payload (deterministic ordering)."""
        seen = {nid}
        frontier = {nid}
        collected_edges: dict[tuple[str, str, str], dict] = {}
        for _ in range(max(1, depth)):
            if not frontier:
                break
            nxt: set[str] = set()
            for fid in sorted(frontier):
                for e in self.edges_of(fid):
                    key = (e["src"], e["dst"], e["rel"])
                    if key in collected_edges:
                        continue
                    other = e["dst"] if e["src"] == fid else e["src"]
                    if other in seen:
                        collected_edges[key] = e
                        continue
                    collected_edges[key] = e
                    seen.add(other)
                    nxt.add(other)
            frontier = nxt
        nodes = []
        for nid2 in sorted(seen):
            n = self.get_node(nid2)
            if n:
                nodes.append(n)
        edges = [collected_edges[k] for k in sorted(collected_edges)]
        return {"root": nid, "nodes": nodes[:limit], "edges": edges[:limit],
                "node_count": len(nodes), "edge_count": len(edges)}

    def shortest_path(self, src: str, dst: str, max_depth: int = 6) -> dict:
        """BFS shortest path (undirected projection) - deterministic tie-break by id."""
        if src == dst:
            return {"path": [src], "edges": [], "found": True}
        seen = {src}
        frontier = {src}
        parent: dict[str, tuple[str, dict]] = {}
        for _ in range(max_depth):
            if not frontier:
                break
            nxt: set[str] = set()
            for fid in sorted(frontier):
                for e in sorted(self.edges_of(fid), key=lambda x: (x["rel"], x["src"], x["dst"])):
                    other = e["dst"] if e["src"] == fid else e["src"]
                    if other in seen:
                        continue
                    seen.add(other)
                    parent[other] = (fid, e)
                    nxt.add(other)
                    if other == dst:
                        break
                if dst in seen:
                    break
            if dst in seen:
                break
            frontier = nxt
        if dst not in seen:
            return {"path": [], "edges": [], "found": False}
        chain = [dst]
        edges = []
        cur = dst
        while cur != src:
            prev, edge = parent[cur]
            edges.append(edge)
            chain.append(prev)
            cur = prev
        chain.reverse()
        edges.reverse()
        return {"path": chain, "edges": edges, "found": True}

    def degree(self) -> None:
        with self._lock:
            self.conn.execute(
                "UPDATE kg_nodes SET degree = ("
                " SELECT COUNT(*) FROM kg_edges WHERE kg_edges.src = kg_nodes.node_id"
                " OR kg_edges.dst = kg_nodes.node_id)")
            self.conn.commit()

    # -------------------------------------------------------------- communities
    def replace_communities(self, communities: list[dict]) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM kg_communities")
            self.conn.execute("UPDATE kg_nodes SET community = ''")
            for c in communities:
                members = list(c.get("members", []))
                self.conn.execute(
                    "INSERT OR REPLACE INTO kg_communities(community_id,title,summary,member_count,level,properties)"
                    " VALUES (?,?,?,?,?,?)",
                    (c["community_id"], c.get("title", ""), c.get("summary", ""), len(members),
                     int(c.get("level", 0)), json.dumps(c.get("properties", {}), ensure_ascii=False)))
                for m in members:
                    self.conn.execute("UPDATE kg_nodes SET community=? WHERE node_id=?",
                                      (c["community_id"], m))
            self.conn.commit()

    def list_communities(self, limit: int = 100) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM kg_communities ORDER BY member_count DESC, community_id LIMIT ?",
            (int(limit),)).fetchall()
        out = []
        for r in rows:
            members = [x["node_id"] for x in self.conn.execute(
                "SELECT node_id FROM kg_nodes WHERE community=? ORDER BY degree DESC, node_id LIMIT 60",
                (r["community_id"],)).fetchall()]
            out.append({"community_id": r["community_id"], "title": r["title"],
                        "summary": r["summary"], "member_count": r["member_count"],
                        "level": r["level"], "members": members,
                        "properties": json.loads(r["properties"] or "{}")})
        return out

    def get_community(self, cid: str) -> dict | None:
        for c in self.list_communities(limit=100000):
            if c["community_id"] == cid:
                return c
        return None

    # ------------------------------------------------------------- trace links
    def add_trace_link(self, link: TraceLink) -> None:
        with self._lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO trace_links(link_id,source_type,source_id,target_type,"
                "target_id,link_type,confidence,evidence,is_inferred,created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM trace_links WHERE link_id=?),0))",
                (link.link_id, link.source_type, link.source_id, link.target_type, link.target_id,
                 link.link_type, float(link.confidence), json.dumps(link.evidence, ensure_ascii=False),
                 1 if link.is_inferred else 0, link.link_id))

    def trace_links(self, source_type: str = "", source_id: str = "",
                    target_type: str = "", target_id: str = "",
                    limit: int = 200) -> list[dict]:
        sql = "SELECT * FROM trace_links WHERE 1=1"
        args: list[Any] = []
        if source_type:
            sql += " AND source_type=?"
            args.append(source_type)
        if source_id:
            sql += " AND source_id=?"
            args.append(source_id)
        if target_type:
            sql += " AND target_type=?"
            args.append(target_type)
        if target_id:
            sql += " AND target_id=?"
            args.append(target_id)
        sql += " ORDER BY confidence DESC, link_id LIMIT ?"
        args.append(int(limit))
        out = []
        for r in self.conn.execute(sql, args).fetchall():
            out.append({"link_id": r["link_id"], "source_type": r["source_type"],
                        "source_id": r["source_id"], "target_type": r["target_type"],
                        "target_id": r["target_id"], "link_type": r["link_type"],
                        "confidence": r["confidence"],
                        "evidence": json.loads(r["evidence"] or "[]"),
                        "is_inferred": bool(r["is_inferred"])})
        return out

    # ------------------------------------------------------------------- stats
    def stats(self) -> dict:
        by_type: dict[str, int] = {}
        for r in self.conn.execute("SELECT type, COUNT(*) c FROM kg_nodes GROUP BY type").fetchall():
            by_type[r["type"]] = int(r["c"])
        by_rel: dict[str, int] = {}
        for r in self.conn.execute("SELECT rel, COUNT(*) c FROM kg_edges GROUP BY rel").fetchall():
            by_rel[r["rel"]] = int(r["c"])
        communities = int(self.conn.execute("SELECT COUNT(*) c FROM kg_communities").fetchone()["c"])
        traces = int(self.conn.execute("SELECT COUNT(*) c FROM trace_links").fetchone()["c"])
        inferred = int(self.conn.execute("SELECT COUNT(*) c FROM kg_edges WHERE is_inferred=1").fetchone()["c"])
        return {"path": self.path, "nodes": self.count_nodes(), "edges": self.count_edges(),
                "communities": communities, "trace_links": traces, "inferred_edges": inferred,
                "nodes_by_type": by_type, "edges_by_rel": by_rel}

    def commit(self) -> None:
        with self._lock:
            self.conn.commit()


# --------------------------------------------------------------------- helpers
def _merge_props(old: dict, new: dict) -> dict:
    out = dict(old)
    for k, v in (new or {}).items():
        if k in out and isinstance(out[k], list) and isinstance(v, list):
            merged = list(out[k])
            for item in v:
                if item not in merged:
                    merged.append(item)
            out[k] = merged
        elif k in out and isinstance(out[k], str) and isinstance(v, str) and out[k]:
            continue
        else:
            out[k] = v
    return out


def _node_row_to_dict(row: sqlite3.Row) -> dict:
    return {"node_id": row["node_id"], "type": row["type"], "label": row["label"],
            "properties": json.loads(row["properties"] or "{}"), "degree": int(row["degree"] or 0),
            "community": row["community"] or "", "source": row["source"] or ""}


def _edge_row_to_dict(row: sqlite3.Row) -> dict:
    return {"src": row["src"], "dst": row["dst"], "rel": row["rel"],
            "weight": float(row["weight"] or 0.0), "confidence": float(row["confidence"] or 0.0),
            "is_inferred": bool(row["is_inferred"]),
            "provenance": json.loads(row["provenance"] or "{}")}


def batch_iter(items: Iterable[Any], size: int = 500) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for it in items:
        batch.append(it)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
