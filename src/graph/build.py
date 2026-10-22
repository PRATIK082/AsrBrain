"""Knowledge-graph construction (Phase 4, G2). Deterministic only; inferred edges flagged.

Two builders feed the v3 graph tables (see src/ingestion/migrations.py):

* spec builder — chunk signals (requirement_ids / api_names / ecu_parameters /
  module) become typed nodes; document CONTAINS edges are exact, co-mention edges
  (SATISFIES / REFERENCES / MENTIONS) are inferred and say so. Co-mention is
  same-sentence: two identifiers in one 220-word window may be unrelated, but two
  in one sentence are discussed together.
* ARXML builder — persists what src/ingestion/arxml/graph_export.py already
  computes (CONTAINS / HAS_PORT / REFERENCES_INTERFACE / assembly edges) instead
  of leaving it in process memory.

Node ids are namespaced (``requirement:SWS_X``, ``api:CanIf_Init`` ...), edge ids are
``e-<sha12(src|rel|dst)>`` — same content always yields the same ids, so rebuilds
are idempotent (INSERT OR REPLACE refreshes in place). Every row carries the v2
provenance tuple (snapshot/content-hash/created_by/confidence).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from ..ingestion.migrations import close_run, content_hash, migrate, new_run

NODE_TYPES = {"document", "module", "requirement", "api", "ecuc",
              "swc", "port", "interface", "runnable", "connector",
              "table", "figure", "artifact"}

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORDS = re.compile(r"[A-Za-z0-9_]+")
# Requirement-shaped tokens double-filed as api_names by the signal extractor
# (same identifier pattern feeds both lists). They already exist as requirement
# nodes; admitting them as api nodes too fabricates api<->requirement links.
_REQ_SHAPED = re.compile(r"^(SWS|RS|PRS|SRS|TPS|constr)_")
# Truncated identifier fragments ("PRS_E2E_", "ECUC_EthTSyn_") would merge every
# mention into one junk node and corrupt neighborhoods. Text retrieval keeps them;
# the graph does not admit them.
_FRAGMENT = re.compile(r"[_-]$")


def _clean_ids(names: list[str]) -> list[str]:
    return sorted({n for n in (names or []) if n and not _FRAGMENT.search(n)})


def _real_apis(names: list[str]) -> list[str]:
    """Keep only attributable API names: requirement-shaped tokens and bare
    SNAKE_CONSTANTS (E_OK, ANY_IP) are extractor noise, not APIs. module_for_api
    is the established is-this-a-real-API test (prefix must map to a module)."""
    from ..ingestion.metadata import module_for_api
    return sorted({a for a in (names or [])
                   if not _REQ_SHAPED.match(a or "") and module_for_api(a or "")})


def edge_id(src: str, rel: str, dst: str) -> str:
    return "e-" + hashlib.sha256(f"{src}|{rel}|{dst}".encode()).hexdigest()[:12]


def _prov(chunk: dict | None, **extra) -> dict:
    base = {"chunk_id": "", "source_pdf": "", "page": None,
            "release": "", "platform": ""}
    if chunk:
        base.update({"chunk_id": chunk.get("chunk_id", ""),
                     "source_pdf": chunk.get("source_pdf", ""),
                     "page": chunk.get("page_start"),
                     "release": chunk.get("autosar_release", ""),
                     "platform": chunk.get("platform", "")})
    base.update(extra)
    return base


def build_spec(chunks: list[dict], documents: list[dict],
               snapshot_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Nodes/edges/trace-links from indexed chunk signals. Pure function (no I/O)."""
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    links: dict[str, dict] = {}

    def add_node(nid, ntype, label, props, conf=1.0):
        nodes.setdefault(nid, {"node_id": nid, "type": ntype, "label": label,
                               "properties": json.dumps(props), "degree": 0,
                               "community": "", "source": props.get("source_pdf", ""),
                               "snapshot_id": snapshot_id,
                               "content_hash": content_hash(nid + label),
                               "created_by": "parser", "confidence": conf})

    def add_edge(src, rel, dst, prov, conf=1.0, inferred=0, method="", weight=1.0):
        eid = edge_id(src, rel, dst)
        edges.setdefault(eid, {"edge_id": eid, "src": src, "dst": dst, "rel": rel,
                               "weight": weight, "confidence": conf,
                               "is_inferred": inferred, "inference_method": method,
                               "provenance": json.dumps(prov),
                               "snapshot_id": snapshot_id,
                               "content_hash": content_hash(src + rel + dst),
                               "created_by": "parser" if not inferred else "parser"})

    def add_link(stype, sid, ttype, tid, ltype, conf, ev, inferred=0):
        lid = f"tr-{ltype}::{sid}::{tid}"
        links.setdefault(lid, {"link_id": lid, "source_type": stype, "source_id": sid,
                               "target_type": ttype, "target_id": tid,
                               "link_type": ltype, "confidence": conf,
                               "evidence": json.dumps(ev), "is_inferred": inferred,
                               "snapshot_id": snapshot_id, "created_by": "parser"})

    for d in documents:
        did = f"document:{d['document_id']}"
        add_node(did, "document", d.get("title", d["document_id"]),
                 {"source_pdf": d.get("source_pdf", ""),
                  "release": d.get("autosar_release", "")})
    for c in chunks:
        did = f"document:{c['document_id']}"
        prov = _prov(c)
        if c.get("module"):
            mid = f"module:{c['module']}"
            add_node(mid, "module", c["module"], {"source_pdf": c.get("source_pdf", "")})
            add_edge(did, "contains", mid, prov)
        reqs = _clean_ids(c.get("requirement_ids", []))
        apis = _clean_ids(_real_apis(c.get("api_names", [])))
        ecucs = _clean_ids(c.get("ecu_parameters", []))
        for r in reqs:
            nid = f"requirement:{r}"
            add_node(nid, "requirement", r, {"source_pdf": c.get("source_pdf", "")})
            add_edge(did, "contains", nid, prov)
        for a in apis:
            nid = f"api:{a}"
            add_node(nid, "api", a, {"source_pdf": c.get("source_pdf", "")})
            add_edge(did, "contains", nid, prov)
        for e in ecucs:
            nid = f"ecuc:{e}"
            add_node(nid, "ecuc", e, {"source_pdf": c.get("source_pdf", "")})
            add_edge(did, "contains", nid, prov)
        # co-mention edges (inferred): identifiers discussed together. Same sentence,
        # not same chunk: a 220-word atomic window can list dozens of unrelated ids
        # (tables especially), but two ids in one sentence are discussed together.
        # Atomic chunks only — merged context unions would explode into noise.
        if c.get("chunk_kind") == "atomic":
            from ..retrieval.reranking import identifier_matches
            text = c.get("normalized_text", "") or ""
            for sent in _SENT_SPLIT.split(text):
                toks = set(_WORDS.findall(sent.lower()))
                if not toks:
                    continue
                sreqs = [r for r in reqs if identifier_matches(toks, r)]
                sapis = [a for a in apis if identifier_matches(toks, a)]
                # List-like sentences (tables, enumerations) name many identifiers
                # without relating them — pairing those is noise, not traceability.
                if len(sreqs) + len(sapis) > 8:
                    continue
                for i in range(len(sreqs)):
                    for j in range(i + 1, len(sreqs)):
                        add_edge(f"requirement:{sreqs[i]}", "references",
                                 f"requirement:{sreqs[j]}", prov,
                                 conf=0.6, inferred=1, method="same_sentence")
                for a in sapis:
                    for r in sreqs:
                        add_edge(f"api:{a}", "satisfies", f"requirement:{r}", prov,
                                 conf=0.6, inferred=1, method="same_sentence")
                        add_link("api", f"api:{a}", "requirement",
                                 f"requirement:{r}",
                                 "satisfies", 0.6, [prov], inferred=1)
    return list(nodes.values()), list(edges.values()), list(links.values())


def build_arxml(topologies: list, snapshot_id: str) -> tuple[list[dict], list[dict]]:
    """Persist graph_export() projections with snapshot provenance. Pure function."""
    from ..ingestion.arxml.graph_export import export_graph
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}
    for topo in topologies:
        g = export_graph(topo)
        art = topo.artifact
        for n in g["nodes"]:
            nid = n["id"]
            nodes.setdefault(nid, {
                "node_id": nid, "type": n.get("type", "artifact"),
                "label": n.get("label", nid),
                "properties": json.dumps({
                    "xpath": n.get("xpath", ""), "artifact_id": art.artifact_id,
                    "source_path": art.source_path,
                    "release": art.autosar_release or ""}),
                "degree": 0, "community": "", "source": art.source_path,
                "snapshot_id": snapshot_id,
                "content_hash": content_hash(nid),
                "created_by": "parser", "confidence": 1.0})
        for e in g["edges"]:
            eid = edge_id(e["src"], e["rel"], e["dst"])
            edges.setdefault(eid, {
                "edge_id": eid, "src": e["src"], "dst": e["dst"], "rel": e["rel"],
                "weight": 1.0, "confidence": e.get("confidence", 1.0),
                "is_inferred": 1 if e.get("is_inferred") else 0,
                "inference_method": e.get("inference_method", ""),
                "provenance": json.dumps({
                    "artifact_id": art.artifact_id, "source_path": art.source_path,
                    "source_sha256": art.source_sha256,
                    "release": art.autosar_release or ""}),
                "snapshot_id": snapshot_id,
                "content_hash": content_hash(e["src"] + e["rel"] + e["dst"]),
                "created_by": "parser"})
    return list(nodes.values()), list(edges.values())


def persist(conn: sqlite3.Connection, nodes: list[dict], edges: list[dict],
            links: list[dict], snapshot_id: str) -> dict:
    """Full rebuild inside one transaction: wipe + insert. Counts returned."""
    cur = conn.cursor()
    cur.execute("DELETE FROM graph_nodes WHERE snapshot_id != ?", (snapshot_id,))
    cur.execute("DELETE FROM graph_edges WHERE snapshot_id != ?", (snapshot_id,))
    cur.execute("DELETE FROM trace_links WHERE snapshot_id != ?", (snapshot_id,))
    for n in nodes:
        cur.execute("INSERT OR REPLACE INTO graph_nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (n["node_id"], n["type"], n["label"], n["properties"], n["degree"],
                     n["community"], n["source"], n["snapshot_id"], n["content_hash"],
                     n["created_by"], n["confidence"]))
    for e in edges:
        cur.execute("INSERT OR REPLACE INTO graph_edges VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (e["edge_id"], e["src"], e["dst"], e["rel"], e["weight"],
                     e["confidence"], e["is_inferred"], e["inference_method"],
                     e["provenance"], e["snapshot_id"], e["content_hash"],
                     e["created_by"]))
    for t in links:
        cur.execute("INSERT OR REPLACE INTO trace_links VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (t["link_id"], t["source_type"], t["source_id"], t["target_type"],
                     t["target_id"], t["link_type"], t["confidence"], t["evidence"],
                     t["is_inferred"], t["snapshot_id"], t["created_by"]))
    # degrees from edge counts (undirected)
    cur.execute("""UPDATE graph_nodes SET degree =
                   (SELECT COUNT(*) FROM graph_edges
                    WHERE graph_edges.src = graph_nodes.node_id
                       OR graph_edges.dst = graph_nodes.node_id)""")
    conn.commit()
    return {"nodes": len(nodes), "edges": len(edges), "links": len(links)}


def build_graph(canonical_db: str) -> dict:
    """Migrate, open a graph snapshot run, rebuild from chunks + linked ARXML."""
    from ..indexing.hybrid import load_chunks
    conn = sqlite3.connect(canonical_db)
    migrate(conn)
    snapshot_id = new_run(conn, source_fingerprint="graph-build")
    try:
        chunks = load_chunks(canonical_db)
        conn.row_factory = sqlite3.Row
        documents = [dict(r) for r in conn.execute("SELECT * FROM documents")]
        conn.row_factory = None
        nodes, edges, links = build_spec(chunks, documents, snapshot_id)
        # ARXML from linked project sources (best effort: unparsable files skipped)
        topologies = []
        try:
            from ..ingestion import project_sources as ps
            from ..ingestion.arxml.parser import parse_arxml
            for rec in ps.load_registry():
                base = rec.get("local_path", "")
                import os
                if not base or not os.path.exists(base):
                    continue
                root = base if os.path.isdir(base) else os.path.dirname(base)
                for dp, _, fns in os.walk(root):
                    for fn in sorted(fns):
                        if not fn.lower().endswith((".arxml", ".xml")):
                            continue
                        try:
                            topologies.append(parse_arxml(os.path.join(dp, fn)))
                        except Exception:
                            continue
        except Exception:
            pass
        anode, aedge = build_arxml(topologies, snapshot_id)
        stats = persist(conn, nodes + anode, edges + aedge, links, snapshot_id)
        stats["arxml_nodes"] = len(anode)
        stats["snapshot_id"] = snapshot_id
    finally:
        close_run(conn, snapshot_id)
    conn.close()
    return stats
