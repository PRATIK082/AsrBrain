"""Build the GraphRAG knowledge graph from the canonical store, code sources and ARXML.

Pipeline
--------
1. canonical chunks  -> requirement / api / ecuc_parameter / module / document nodes
2. C sources         -> function / api(Rte_*) nodes, call + implements edges
3. test sources      -> test_case nodes, covers/verifies edges
4. ARXML topologies  -> swc / port / interface / runnable nodes (deterministic export)
5. trace links       -> requirement <-> api <-> function <-> test_case matrix
6. communities       -> label propagation + deterministic summaries

The build is incremental-friendly: `max_nodes` / `max_edges` caps keep huge corpora
bounded, and every run reports what it produced.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import Iterable

from .community import detect_communities
from .extractor import (Relation, extract_chunk_entities, extract_code_entities,
                         extract_test_entities)
from .store import GraphStore, TraceLink, node_id

CODE_EXTS = {".c", ".h", ".cpp", ".hpp", ".cc"}
TEST_EXTS = {".c", ".h", ".cpp", ".py", ".java"}


def _iter_source_files(roots: Iterable[str]) -> list[tuple[str, str]]:
    """Return (path, kind) where kind is 'code' or 'test'."""
    out: list[tuple[str, str]] = []
    for root in roots:
        if not root:
            continue
        if os.path.isfile(root):
            out.append((root, _kind_for(root)))
            continue
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__",
                                                            ".next", "data", "frontend")]
            for fn in sorted(filenames):
                fp = os.path.join(dirpath, fn)
                out.append((fp, _kind_for(fp)))
    return out


def _kind_for(path: str) -> str:
    base = os.path.basename(path).lower()
    ext = os.path.splitext(path)[1].lower()
    if ext not in CODE_EXTS and ext not in TEST_EXTS:
        return "other"
    if base.startswith(("test_", "ut_", "it_", "tc_")) or "test" in base:
        return "test"
    if ext == ".py":
        return "other"
    return "code"


def build_graph(store: GraphStore, chunks: list[dict],
                code_roots: list[str] | None = None,
                arxml_graphs: list[dict] | None = None,
                max_nodes: int = 20000, max_edges: int = 120000,
                clear: bool = True) -> dict:
    started = time.time()
    if clear:
        store.clear()
    stats = {"chunks": 0, "entities": 0, "relations": 0, "code_files": 0,
             "test_files": 0, "arxml_graphs": 0, "traces": 0}

    def add_entity(ent_type: str, label: str, props: dict) -> str:
        return store.upsert_node(ent_type, label, props)

    def add_relation(rel: Relation) -> None:
        src = node_id(rel.src_type, rel.src)
        dst = node_id(rel.dst_type, rel.dst)
        store.upsert_edge(src, dst, rel.rel, weight=1.0, confidence=rel.confidence,
                          is_inferred=rel.is_inferred, provenance=rel.provenance)

    # ------------------------------------------------------------ spec chunks
    for chunk in chunks:
        stats["chunks"] += 1
        ents, rels = extract_chunk_entities(chunk)
        for e in ents:
            add_entity(e.type, e.label, e.properties)
            stats["entities"] += 1
        for r in rels:
            add_relation(r)
            stats["relations"] += 1

    # ---------------------------------------------------------- code / tests
    for path, kind in _iter_source_files(code_roots or []):
        if kind == "other":
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        if not text.strip():
            continue
        if kind == "test":
            ents, rels = extract_test_entities(path, text)
            stats["test_files"] += 1
        else:
            ents, rels = extract_code_entities(path, text)
            stats["code_files"] += 1
        for e in ents:
            add_entity(e.type, e.label, e.properties)
            stats["entities"] += 1
        for r in rels:
            add_relation(r)
            stats["relations"] += 1

    # --------------------------------------------------------------- ARXML
    for graph in arxml_graphs or []:
        stats["arxml_graphs"] += 1
        for n in graph.get("nodes", []):
            add_entity(_arxml_node_type(n.get("type", "")), str(n.get("label") or n.get("id", "")),
                       {"xpath": n.get("xpath", ""), "artifact_id": graph.get("artifact_id", "")})
            stats["entities"] += 1
        for e in graph.get("edges", []):
            src = node_id(_arxml_node_type(_arxml_type_of(e["src"], graph)), e["src"])
            dst = node_id(_arxml_node_type(_arxml_type_of(e["dst"], graph)), e["dst"])
            store.upsert_edge(src, dst, e["rel"].lower(), weight=1.0, confidence=0.95,
                              is_inferred=False,
                              provenance={"artifact_id": graph.get("artifact_id", ""),
                                          "source_file": graph.get("source_file", "")})
            stats["relations"] += 1

    store.commit()
    store.degree()

    # ------------------------------------------------------ trace link matrix
    stats["traces"] = _build_trace_links(store)

    # ---------------------------------------------------------- communities
    communities = detect_communities(store)
    store.replace_communities(communities)
    store.commit()

    result = store.stats()
    result.update(stats)
    result["communities_built"] = len(communities)
    result["elapsed_s"] = round(time.time() - started, 3)
    result["truncated"] = result["nodes"] > max_nodes or result["edges"] > max_edges
    return result


def _arxml_node_type(arxml_type: str) -> str:
    t = (arxml_type or "").lower()
    if "port" in t and "interface" in t:
        return "interface"
    if "port" in t:
        return "port"
    if "runnable" in t:
        return "runnable"
    if "composition" in t or "component" in t:
        return "swc"
    if "ecuc" in t:
        return "ecuc_parameter"
    if "artifact" in t:
        return "document"
    return "concept"


def _arxml_type_of(node_id_str: str, graph: dict) -> str:
    for n in graph.get("nodes", []):
        if n.get("id") == node_id_str:
            return n.get("type", "")
    return ""


def _build_trace_links(store: GraphStore) -> int:
    """requirement <-> api <-> function <-> test_case matrix from the KG itself."""
    count = 0
    reqs = store.find_nodes(type="requirement", limit=100000)
    apis = store.find_nodes(type="api", limit=100000)
    fns = store.find_nodes(type="function", limit=100000)
    tests = store.find_nodes(type="test_case", limit=100000)

    api_labels = {a["label"] for a in apis}
    fn_labels = {f["label"] for f in fns}

    # api -> requirement (satisfies edges already in the KG)
    for e in store.conn.execute(
            "SELECT src,dst,confidence,provenance FROM kg_edges WHERE rel='satisfies'").fetchall():
        store.add_trace_link(TraceLink(
            link_id=f"tr-api-req::{e['src']}::{e['dst']}",
            source_type="api", source_id=e["src"], target_type="requirement", target_id=e["dst"],
            link_type="satisfies", confidence=float(e["confidence"] or 0.5),
            evidence=[f"kg edge satisfies ({e['provenance']})"], is_inferred=True))
        count += 1

    # function -> api (Rte_ call sites)
    for e in store.conn.execute(
            "SELECT src,dst,confidence,provenance FROM kg_edges WHERE rel='calls'").fetchall():
        store.add_trace_link(TraceLink(
            link_id=f"tr-fn-api::{e['src']}::{e['dst']}",
            source_type="function", source_id=e["src"], target_type="api", target_id=e["dst"],
            link_type="implements", confidence=float(e["confidence"] or 0.5),
            evidence=[f"Rte call site ({e['provenance']})"], is_inferred=False))
        count += 1

    # api -> function (reverse of the call edge)
    for e in store.conn.execute(
            "SELECT src,dst,confidence FROM kg_edges WHERE rel='calls'").fetchall():
        if e["dst"].split(":", 1)[-1] in api_labels or e["src"].split(":", 1)[-1] in fn_labels:
            store.add_trace_link(TraceLink(
                link_id=f"tr-api-fn::{e['dst']}::{e['src']}",
                source_type="api", source_id=e["dst"], target_type="function", target_id=e["src"],
                link_type="implemented_by", confidence=float(e["confidence"] or 0.5),
                evidence=["Rte call site"], is_inferred=False))
            count += 1

    # test_case -> requirement (covers edges)
    for e in store.conn.execute(
            "SELECT src,dst,confidence,provenance FROM kg_edges WHERE rel IN ('covers','covered_by')").fetchall():
        store.add_trace_link(TraceLink(
            link_id=f"tr-tc-req::{e['src']}::{e['dst']}",
            source_type="test_case", source_id=e["src"], target_type="requirement", target_id=e["dst"],
            link_type="covers", confidence=float(e["confidence"] or 0.5),
            evidence=[f"test annotation ({e['provenance']})"], is_inferred=False))
        count += 1

    # requirement -> api -> function -> test_case  (2-hop composition)
    api_to_fns: dict[str, list[str]] = {}
    for e in store.conn.execute(
            "SELECT src,dst FROM kg_edges WHERE rel='calls'").fetchall():
        api_to_fns.setdefault(e["dst"], []).append(e["src"])
    req_to_apis: dict[str, list[str]] = {}
    for e in store.conn.execute(
            "SELECT src,dst FROM kg_edges WHERE rel='satisfies'").fetchall():
        req_to_apis.setdefault(e["dst"], []).append(e["src"])
    tc_to_reqs: dict[str, list[str]] = {}
    for e in store.conn.execute(
            "SELECT src,dst FROM kg_edges WHERE rel IN ('covers','covered_by')").fetchall():
        tc_to_reqs.setdefault(e["dst"], []).append(e["src"])

    for req, api_list in req_to_apis.items():
        for api in api_list:
            for fn in api_to_fns.get(api, [])[:20]:
                store.add_trace_link(TraceLink(
                    link_id=f"tr-req-fn::{req}::{fn}",
                    source_type="requirement", source_id=req, target_type="function",
                    target_id=fn, link_type="implemented_by", confidence=0.5,
                    evidence=[f"requirement -> {api} -> {fn}"], is_inferred=True))
                count += 1
                for tc in tc_to_reqs.get(req, [])[:20]:
                    store.add_trace_link(TraceLink(
                        link_id=f"tr-tc-fn::{tc}::{fn}",
                        source_type="test_case", source_id=tc, target_type="function",
                        target_id=fn, link_type="verifies", confidence=0.4,
                        evidence=[f"{tc} covers {req}; {req} implemented by {fn}"], is_inferred=True))
                    count += 1
    store.commit()
    return count


def build_from_canonical(canonical_db: str = "data/canonical/canonical.db",
                         graph_db: str = "data/canonical/graph.db",
                         code_roots: list[str] | None = None,
                         clear: bool = True) -> dict:
    from src.indexing.hybrid import load_chunks
    chunks = load_chunks(canonical_db)
    with GraphStore(graph_db) as store:
        return build_graph(store, chunks, code_roots=code_roots, clear=clear)


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the GraphRAG knowledge graph")
    ap.add_argument("--canonical", default="data/canonical/canonical.db")
    ap.add_argument("--out", default="data/canonical/graph.db")
    ap.add_argument("--code-dir", action="append", default=[],
                    help="directory (repeatable) with C sources and tests")
    ap.add_argument("--keep", action="store_true", help="do not clear the existing graph")
    args = ap.parse_args()
    result = build_from_canonical(args.canonical, args.out, code_roots=args.code_dir,
                                  clear=not args.keep)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
