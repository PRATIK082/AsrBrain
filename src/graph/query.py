"""Trace queries over the v3 graph store (Phase 4, G4). SQLite-direct, no server."""
from __future__ import annotations

import json
import re
import sqlite3


def neighbors(canonical_db: str, node_id: str, depth: int = 1,
              rels: list[str] | None = None) -> dict:
    """Breadth-first neighborhood with provenance; optionally restricted to rels."""
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    seen = {node_id}
    frontier = {node_id}
    out_edges: list[dict] = []
    for _ in range(max(1, depth)):
        nxt: set[str] = set()
        q = ("SELECT * FROM graph_edges WHERE (src IN (%s) OR dst IN (%s))" % (
            ",".join("?" * len(frontier)), ",".join("?" * len(frontier))))
        args: list = list(frontier) + list(frontier)
        if rels:
            q += " AND rel IN (%s)" % ",".join("?" * len(rels))
            args += list(rels)
        for e in conn.execute(q, args):
            e = dict(e)
            other = e["dst"] if e["src"] in frontier else e["src"]
            out_edges.append(e)
            if other not in seen:
                seen.add(other)
                nxt.add(other)
        frontier = nxt
        if not frontier:
            break
    nodes = [dict(r) for r in conn.execute(
        "SELECT * FROM graph_nodes WHERE node_id IN (%s)" % ",".join("?" * len(seen)),
        list(seen))]
    conn.close()
    return {"node_id": node_id, "nodes": nodes, "edges": out_edges}


def evidence_graph(canonical_db: str, evidence: list[dict],
                   max_ids: int = 6) -> list[dict]:
    """Edges for the UI Graph tab, read from the persistent store (not ephemeral).

    Collects requirement/API/ECUC identifiers from the answer's evidence, returns
    their depth-1 neighborhoods as render dicts (subject/object/predicate/source).
    Bounded: at most ``max_ids`` identifiers, 30 edges. Empty store -> [].
    """
    wanted: list[str] = []
    for c in evidence or []:
        for rid in (c.get("requirement_ids", []) or [])[:3]:
            wanted.append(f"requirement:{rid}")
        for aid in (c.get("api_names", []) or [])[:3]:
            wanted.append(f"api:{aid}")
        for eid in (c.get("ecu_parameters", []) or [])[:2]:
            wanted.append(f"ecuc:{eid}")
    seen: set[str] = set()
    ids = [i for i in wanted if not (i in seen or seen.add(i))][:max_ids]
    if not ids:
        return []
    try:
        conn = sqlite3.connect(canonical_db)
        conn.row_factory = sqlite3.Row
        labels = {r["node_id"]: r["label"] for r in conn.execute(
            "SELECT node_id, label FROM graph_nodes WHERE node_id IN (%s)"
            % ",".join("?" * len(ids)), ids)}
        conn.close()
    except Exception:
        return []
    out: list[dict] = []
    for nid in ids:
        try:
            nb = neighbors(canonical_db, nid, depth=1)
        except Exception:
            continue
        out.extend(nb["edges"])
        if len(out) >= 60:
            break
    out = out[:30]
    # labels for every endpoint (the initial lookup only covered the seeds)
    try:
        conn = sqlite3.connect(canonical_db)
        conn.row_factory = sqlite3.Row
        eps = list({e["src"] for e in out} | {e["dst"] for e in out})
        labels = dict(labels)
        if eps:
            for r in conn.execute("SELECT node_id, label FROM graph_nodes WHERE node_id IN (%s)"
                                  % ",".join("?" * len(eps)), eps):
                labels[r["node_id"]] = r["label"]
        conn.close()
    except Exception:
        pass
    rendered: list[dict] = []
    for e in out:
        try:
            prov = json.loads(e.get("provenance") or "{}")
        except Exception:
            prov = {}
        rendered.append({"subject": labels.get(e["src"], e["src"]),
                         "object": labels.get(e["dst"], e["dst"]),
                         "predicate": e["rel"],
                         "is_inferred": bool(e.get("is_inferred")),
                         "source_pdf": prov.get("source_pdf", ""),
                         "page": prov.get("page"),
                         "confidence": e.get("confidence", 0.0)})
    return rendered


def _attach_provenance(edge_rows: list[dict]) -> tuple[list[str], list[dict]]:
    chunks: list[str] = []
    provs: list[dict] = []
    for e in edge_rows:
        try:
            prov = json.loads(e.get("provenance") or "{}")
        except Exception:
            prov = {}
        if prov.get("chunk_id"):
            chunks.append(prov["chunk_id"])
        provs.append(prov)
    return sorted(set(chunks)), provs


def trace_question(canonical_db: str, question: str) -> dict:
    """Answer one traceability question through the graph.

    Supported shapes (matched deterministically, no LLM):
    * "which apis satisfy <REQ_ID>" -> satisfies in-edges of requirement:<REQ_ID>
    * "which requirements does <API> satisfy" -> satisfies out-edges of api:<API>
    * "which requirements does <REQ_ID> reference" -> references out-edges
    * "what connects to <ID>" -> depth-1 neighborhood of the node
    Returns node/edge ids plus the supporting chunk ids with provenance.
    """
    q = question.strip()
    m = re.search(r"satisfy\s+([A-Za-z0-9_\-]+)", q, re.I)
    m2 = re.search(r"does\s+([A-Za-z0-9_\-]+)\s+satisf", q, re.I)
    mref = re.search(r"does\s+([A-Za-z0-9_\-]+)\s+reference", q, re.I)
    m3 = re.search(r"connects to\s+([A-Za-z0-9_\-]+)", q, re.I)
    conn = sqlite3.connect(canonical_db)
    conn.row_factory = sqlite3.Row
    out: dict = {"question": question, "node_ids": [], "edge_ids": [],
                 "chunk_ids": [], "provenance": []}
    edge_rows: list[dict] = []
    if m and not m2:
        rid = f"requirement:{m.group(1)}"
        edge_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM graph_edges WHERE dst=? AND rel='satisfies'", (rid,))]
        out["node_ids"] = sorted({rid} | {r["src"] for r in edge_rows})
    elif m2:
        aid = m2.group(1)
        aid = aid if aid.startswith("api:") else f"api:{aid}"
        edge_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM graph_edges WHERE src=? AND rel='satisfies'", (aid,))]
        out["node_ids"] = sorted({aid} | {r["dst"] for r in edge_rows})
    elif mref:
        rid = mref.group(1)
        rid = rid if rid.startswith("requirement:") else f"requirement:{rid}"
        edge_rows = [dict(r) for r in conn.execute(
            "SELECT * FROM graph_edges WHERE src=? AND rel='references'", (rid,))]
        out["node_ids"] = sorted({rid} | {r["dst"] for r in edge_rows})
    else:
        ident = m3.group(1) if m3 else ""
        cand = [f"api:{ident}", f"requirement:{ident}", f"module:{ident}",
                f"ecuc:{ident}"]
        hit = conn.execute("SELECT node_id FROM graph_nodes WHERE node_id IN (%s)"
                           % ",".join("?" * len(cand)), cand).fetchone()
        conn.close()
        if hit:
            nb = neighbors(canonical_db, hit["node_id"], depth=1)
            out["node_ids"] = sorted(n["node_id"] for n in nb["nodes"])
            out["edge_ids"] = [e["edge_id"] for e in nb["edges"]]
            out["chunk_ids"], out["provenance"] = _attach_provenance(nb["edges"])
        return out
    conn.close()
    out["edge_ids"] = [r["edge_id"] for r in edge_rows]
    out["chunk_ids"], out["provenance"] = _attach_provenance(edge_rows)
    return out
