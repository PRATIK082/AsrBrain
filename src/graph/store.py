"""Typed knowledge graph with mandatory provenance (ADR-0004, ADR-0007, ADR-0011).

The graph is **not** a place to dump "AI relationships". Every node and every
edge has:

* a **type** from a closed vocabulary (an unknown type is rejected at write
  time, not stored and hoped for);
* **provenance** — the artifact version, the source location inside that
  version, and how the relation was established;
* a **confidence** and an `is_inferred` flag;
* a **lifecycle state**.

An inferred edge can never satisfy `VERIFIED` (ADR-0001). The store is an
interface so the local SQLite implementation can be replaced by FalkorDB
without touching the call sites (ADR-0011) — the protocol, not the server, is
the dependency.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable, Protocol

__all__ = [
    "EdgeProvenance",
    "GraphEdge",
    "GraphNode",
    "GraphStore",
    "SqliteGraphStore",
    "UnknownRelationError",
    "UnknownTypeError",
]


class UnknownTypeError(ValueError):
    """The node type is not part of the closed vocabulary."""


class UnknownRelationError(ValueError):
    """The relation is not part of the closed vocabulary."""


# --------------------------------------------------------------------------- #
# vocabulary
# --------------------------------------------------------------------------- #

#: Node types the store accepts. Derived from the multimodal graph vocabulary
#: (`src/schema/multimodal_graph.py`) plus the ARXML element types.
NODE_TYPES: tuple[str, ...] = (
    "document", "release", "platform", "module", "chapter", "section", "subsection",
    "requirement", "api", "ecuc_parameter", "table", "image", "diagram",
    "equation", "interface", "error_code", "state", "event",
    "arxml_artifact", "software_component", "composition", "port", "runnable",
    "connector", "project", "workspace", "artifact_version", "source_location",
    "code_symbol", "test_case", "finding", "change_set",
)

#: Relations the store accepts. `contains`/`has_port`/`references_interface`/
#: `assembly_connects`/`delegates_to` cover the ARXML projection.
RELATION_TYPES: tuple[str, ...] = (
    "contains", "belongs_to", "available_in", "defined_in", "depends_on",
    "interacts_with", "routes_through", "configured_by", "satisfies",
    "references", "has_table", "has_image", "has_diagram", "explains",
    "precedes", "transitions_to", "differs_from", "supported_by",
    "has_port", "references_interface", "assembly_connects", "delegates_to",
    "has_runnable", "has_connector", "implements", "co_mentioned_with",
)


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- #
# records
# --------------------------------------------------------------------------- #


class GraphNode:
    """A typed node. ``properties`` holds the entity attributes."""

    __slots__ = ("id", "type", "label", "properties")

    def __init__(self, id: str, type: str, label: str = "", properties: dict | None = None):
        if type not in NODE_TYPES:
            raise UnknownTypeError(
                f"unknown node type: {type!r} (allowed: {', '.join(sorted(NODE_TYPES))})")
        self.id = id
        self.type = type
        self.label = label or id
        self.properties = dict(properties or {})

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "label": self.label,
                "properties": self.properties}


class EdgeProvenance:
    """Where a relation came from. Mandatory on every edge."""

    __slots__ = ("artifact_version_id", "source_location_id", "extraction_method",
                 "confidence", "is_inferred", "lifecycle_state")

    def __init__(self, artifact_version_id: str = "", source_location_id: str = "",
                 extraction_method: str = "", confidence: float = 1.0,
                 is_inferred: bool = False, lifecycle_state: str = "active"):
        self.artifact_version_id = artifact_version_id
        self.source_location_id = source_location_id
        self.extraction_method = extraction_method
        self.confidence = float(confidence)
        self.is_inferred = bool(is_inferred)
        self.lifecycle_state = lifecycle_state

    def to_dict(self) -> dict:
        return {
            "artifact_version_id": self.artifact_version_id,
            "source_location_id": self.source_location_id,
            "extraction_method": self.extraction_method,
            "confidence": self.confidence,
            "is_inferred": self.is_inferred,
            "lifecycle_state": self.lifecycle_state,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "EdgeProvenance":
        data = data or {}
        return cls(
            artifact_version_id=str(data.get("artifact_version_id") or ""),
            source_location_id=str(data.get("source_location_id") or ""),
            extraction_method=str(data.get("extraction_method") or ""),
            confidence=float(data.get("confidence", 1.0) or 0.0),
            is_inferred=bool(data.get("is_inferred", False)),
            lifecycle_state=str(data.get("lifecycle_state") or "active"),
        )


class GraphEdge:
    """A typed relation with provenance."""

    __slots__ = ("src", "predicate", "dst", "provenance")

    def __init__(self, src: str, predicate: str, dst: str, provenance: EdgeProvenance | None = None):
        if predicate not in RELATION_TYPES:
            raise UnknownRelationError(
                f"unknown relation: {predicate!r} (allowed: {', '.join(sorted(RELATION_TYPES))})")
        self.src = src
        self.predicate = predicate
        self.dst = dst
        self.provenance = provenance or EdgeProvenance()

    def to_dict(self) -> dict:
        return {"src": self.src, "predicate": self.predicate, "dst": self.dst,
                "provenance": self.provenance.to_dict()}

    @classmethod
    def from_dict(cls, data: dict) -> "GraphEdge":
        return cls(str(data["src"]), str(data["predicate"]), str(data["dst"]),
                   EdgeProvenance.from_dict(data.get("provenance")))


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #


class GraphStore(Protocol):
    """The interface every graph backend implements (ADR-0007)."""

    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> int: ...
    def upsert_edges(self, edges: Iterable[GraphEdge]) -> int: ...
    def get_node(self, node_id: str) -> dict | None: ...
    def neighbors(self, node_id: str, depth: int = 1,
                  predicate: str = "", limit: int = 100) -> dict: ...
    def paths(self, src: str, dst: str, max_depth: int = 6, limit: int = 20) -> list[dict]: ...
    def subgraph(self, node_ids: Iterable[str], depth: int = 1, limit: int = 500) -> dict: ...
    def stats(self) -> dict: ...


# --------------------------------------------------------------------------- #
# local implementation
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_nodes(
  id TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT NOT NULL,
  properties_json TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS graph_edges(
  id TEXT PRIMARY KEY, src TEXT NOT NULL, dst TEXT NOT NULL, predicate TEXT NOT NULL,
  artifact_version_id TEXT DEFAULT '', source_location_id TEXT DEFAULT '',
  extraction_method TEXT DEFAULT '', confidence REAL DEFAULT 1.0,
  is_inferred INT DEFAULT 0, lifecycle_state TEXT DEFAULT 'active',
  created_at TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(src);
CREATE INDEX IF NOT EXISTS idx_graph_edges_dst ON graph_edges(dst);
CREATE INDEX IF NOT EXISTS idx_graph_edges_predicate ON graph_edges(predicate);
"""


class SqliteGraphStore:
    """The local graph store. The development default (ADR-0007, ADR-0011)."""

    def __init__(self, path: str = "data/canonical/graph.db"):
        self.path = path
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- writes ------------------------------------------------------------
    def upsert_nodes(self, nodes: Iterable[GraphNode]) -> int:
        count = 0
        now = _now()
        for node in nodes:
            if not isinstance(node, GraphNode):
                raise UnknownTypeError("upsert_nodes expects GraphNode instances")
            self._conn.execute(
                "INSERT INTO graph_nodes(id, type, label, properties_json, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET type=excluded.type, label=excluded.label,"
                " properties_json=excluded.properties_json, updated_at=excluded.updated_at",
                (node.id, node.type, node.label, json.dumps(node.properties), now, now))
            count += 1
        self._conn.commit()
        return count

    def upsert_edges(self, edges: Iterable[GraphEdge]) -> int:
        count = 0
        now = _now()
        for edge in edges:
            if not isinstance(edge, GraphEdge):
                raise UnknownRelationError("upsert_edges expects GraphEdge instances")
            edge_id = f"{edge.src}|{edge.predicate}|{edge.dst}"
            p = edge.provenance
            self._conn.execute(
                "INSERT INTO graph_edges(id, src, dst, predicate, artifact_version_id,"
                " source_location_id, extraction_method, confidence, is_inferred,"
                " lifecycle_state, created_at, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET artifact_version_id=excluded.artifact_version_id,"
                " source_location_id=excluded.source_location_id,"
                " extraction_method=excluded.extraction_method, confidence=excluded.confidence,"
                " is_inferred=excluded.is_inferred, lifecycle_state=excluded.lifecycle_state,"
                " updated_at=excluded.updated_at",
                (edge_id, edge.src, edge.dst, edge.predicate, p.artifact_version_id,
                 p.source_location_id, p.extraction_method, p.confidence,
                 1 if p.is_inferred else 0, p.lifecycle_state, now, now))
            count += 1
        self._conn.commit()
        return count

    # -- reads -------------------------------------------------------------
    def get_node(self, node_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM graph_nodes WHERE id=?", (node_id,)).fetchone()
        return self._node_row(row) if row else None

    def list_nodes(self, type: str = "", limit: int = 1000) -> list[dict]:
        if type:
            rows = self._conn.execute(
                "SELECT * FROM graph_nodes WHERE type=? ORDER BY id LIMIT ?", (type, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM graph_nodes ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [self._node_row(r) for r in rows]

    def _node_row(self, row) -> dict:
        return {"id": row["id"], "type": row["type"], "label": row["label"],
                "properties": json.loads(row["properties_json"] or "{}")}

    def _edge_row(self, row) -> dict:
        return {
            "src": row["src"], "predicate": row["predicate"], "dst": row["dst"],
            "provenance": {
                "artifact_version_id": row["artifact_version_id"],
                "source_location_id": row["source_location_id"],
                "extraction_method": row["extraction_method"],
                "confidence": row["confidence"],
                "is_inferred": bool(row["is_inferred"]),
                "lifecycle_state": row["lifecycle_state"],
            },
        }

    def list_edges(self, predicate: str = "", limit: int = 1000) -> list[dict]:
        if predicate:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE predicate=? ORDER BY id LIMIT ?",
                (predicate, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM graph_edges ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [self._edge_row(r) for r in rows]

    def neighbors(self, node_id: str, depth: int = 1, predicate: str = "",
                  limit: int = 100) -> dict:
        """Breadth-first neighbourhood. Deterministic and bounded."""
        seen = {node_id}
        frontier = {node_id}
        edges: list[dict] = []
        edge_ids: set[str] = set()
        for _ in range(max(0, depth)):
            if not frontier:
                break
            next_frontier: set[str] = set()
            for current in sorted(frontier):
                sql = ("SELECT * FROM graph_edges WHERE (src=? OR dst=?)"
                       + (" AND predicate=?" if predicate else "")
                       + " ORDER BY id LIMIT ?")
                params = (current, current, predicate, limit) if predicate else (current, current, limit)
                for row in self._conn.execute(sql, params).fetchall():
                    if row["id"] in edge_ids:
                        continue
                    edge_ids.add(row["id"])
                    edges.append(self._edge_row(row))
                    for other in (row["src"], row["dst"]):
                        if other not in seen:
                            seen.add(other)
                            next_frontier.add(other)
            frontier = next_frontier
        nodes = []
        for nid in sorted(seen):
            node = self.get_node(nid)
            if node:
                nodes.append(node)
        return {"node_id": node_id, "depth": depth, "nodes": nodes, "edges": edges}

    def paths(self, src: str, dst: str, max_depth: int = 6, limit: int = 20) -> list[dict]:
        """Shortest paths from src to dst (breadth first, deterministic order)."""
        if src == dst:
            return [{"nodes": [src], "edges": []}]
        queue: list[tuple[str, list[str], list[dict]]] = [(src, [src], [])]
        found: list[dict] = []
        while queue and len(found) < limit:
            current, node_path, edge_path = queue.pop(0)
            if len(node_path) > max_depth:
                continue
            rows = self._conn.execute(
                "SELECT * FROM graph_edges WHERE src=? ORDER BY id", (current,)).fetchall()
            for row in rows:
                if row["dst"] in node_path:
                    continue
                edge = self._edge_row(row)
                new_nodes = node_path + [row["dst"]]
                new_edges = edge_path + [edge]
                if row["dst"] == dst:
                    found.append({"nodes": new_nodes, "edges": new_edges})
                    if len(found) >= limit:
                        break
                else:
                    queue.append((row["dst"], new_nodes, new_edges))
        return found

    def subgraph(self, node_ids: Iterable[str], depth: int = 1, limit: int = 500) -> dict:
        seen: set[str] = set()
        edges: list[dict] = []
        for node_id in node_ids:
            if node_id in seen:
                continue
            seen.add(node_id)
            result = self.neighbors(node_id, depth=depth, limit=limit)
            edges.extend(result["edges"])
            for node in result["nodes"]:
                seen.add(node["id"])
        nodes = [n for n in (self.get_node(nid) for nid in sorted(seen)) if n]
        unique_edges = {json.dumps(e, sort_keys=True): e for e in edges}
        return {"nodes": nodes, "edges": list(unique_edges.values())[:limit]}

    def stats(self) -> dict:
        nodes = self._conn.execute("SELECT COUNT(*) AS n FROM graph_nodes").fetchone()["n"]
        edges = self._conn.execute("SELECT COUNT(*) AS n FROM graph_edges").fetchone()["n"]
        inferred = self._conn.execute(
            "SELECT COUNT(*) AS n FROM graph_edges WHERE is_inferred=1").fetchone()["n"]
        types = {r["type"]: r["n"] for r in self._conn.execute(
            "SELECT type, COUNT(*) AS n FROM graph_nodes GROUP BY type ORDER BY type").fetchall()}
        return {"nodes": nodes, "edges": edges, "inferred_edges": inferred,
                "node_types": types, "backend": "sqlite"}

    def close(self) -> None:
        self._conn.close()
