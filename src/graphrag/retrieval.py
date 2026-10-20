"""GraphRAG retrieval: local (entity neighbourhood), global (community) and hybrid.

* **local**  - seed entities from the query, weighted BFS over the KG.
* **global** - community summaries ranked against the query (BM25 over the summary).
* **hybrid** - local + global fused, optionally merged with the classic vector/BM25
  evidence of the retrieval pipeline so GraphRAG *adds* signal instead of replacing a
  pipeline that is already validated against the benchmark.

All results carry the provenance of the underlying edge (chunk id / file / line) so the
answer layer can cite `[G#]` graph evidence the same way it cites `[E#]` text evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from ..indexing.hybrid import tokenize_technical
from .extractor import seed_labels
from .store import GraphStore


# --------------------------------------------------------------------- helpers
def _candidate_nodes(store: GraphStore, seed: str, limit: int = 12) -> list[dict]:
    """Resolve one seed string to concrete graph nodes (exact first, then contains)."""
    out: list[dict] = []
    row = store.conn.execute(
        "SELECT * FROM kg_nodes WHERE label = ? ORDER BY degree DESC LIMIT ?",
        (seed, int(limit))).fetchall()
    out.extend(_rows_to_nodes(row))
    if not out:
        row = store.conn.execute(
            "SELECT * FROM kg_nodes WHERE label LIKE ? ORDER BY degree DESC LIMIT ?",
            (f"%{seed}%", int(limit))).fetchall()
        out.extend(_rows_to_nodes(row))
    return out


def _rows_to_nodes(rows) -> list[dict]:
    out = []
    for r in rows:
        out.append({"node_id": r["node_id"], "type": r["type"], "label": r["label"],
                    "degree": int(r["degree"] or 0), "community": r["community"] or "",
                    "properties": _loads(r["properties"])})
    return out


def _loads(text: str) -> dict:
    import json
    try:
        return json.loads(text or "{}")
    except Exception:
        return {}


def _bm25_scores(query: str, docs: list[str]) -> list[float]:
    if not docs:
        return []
    import math
    toks = [tokenize_technical(d) for d in docs]
    df: Counter = Counter()
    for t in toks:
        for term in set(t):
            df[term] += 1
    n = len(docs)
    avgdl = sum(len(t) for t in toks) / max(1, n)
    scores = [0.0] * n
    q_terms = set(tokenize_technical(query))
    for i, t in enumerate(toks):
        dl = len(t) or 1
        for term in q_terms:
            f = t.count(term)
            if not f:
                continue
            idf = math.log((n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5) + 1.0)
            denom = f + 1.5 * (1 - 0.75 + 0.75 * dl / (avgdl or 1))
            scores[i] += idf * (f * (2.5) / denom)
    return scores


# ------------------------------------------------------------------ local search
def local_search(store: GraphStore, query: str, depth: int = 2,
                 limit: int = 25) -> dict:
    """Entity-centred neighbourhood retrieval."""
    seeds = seed_labels(query)
    seed_nodes: list[dict] = []
    seen: set[str] = set()
    for s in seeds:
        for n in _candidate_nodes(store, s):
            if n["node_id"] in seen:
                continue
            seen.add(n["node_id"])
            seed_nodes.append(n)
    scores: dict[str, float] = {n["node_id"]: 1.0 for n in seed_nodes}
    edge_map: dict[tuple[str, str, str], dict] = {}
    frontier = {n["node_id"] for n in seed_nodes}
    visited = set(frontier)
    for level in range(1, max(1, depth) + 1):
        decay = 0.55 ** level
        nxt: set[str] = set()
        for fid in sorted(frontier):
            for e in store.edges_of(fid):
                key = (e["src"], e["dst"], e["rel"])
                if key in edge_map:
                    continue
                edge_map[key] = e
                other = e["dst"] if e["src"] == fid else e["src"]
                if other in visited:
                    continue
                visited.add(other)
                nxt.add(other)
                scores[other] = max(scores.get(other, 0.0), decay * float(e["weight"] or 1.0)
                                    * float(e["confidence"] or 0.5))
        frontier = nxt
        if not frontier:
            break

    nodes = []
    for nid, score in scores.items():
        n = store.get_node(nid)
        if n:
            n["score"] = round(float(score), 5)
            nodes.append(n)
    nodes.sort(key=lambda n: (-n["score"], -n["degree"], n["label"]))
    edges = [edge_map[k] for k in sorted(edge_map)]
    return {"mode": "local", "query": query, "seeds": seeds,
            "seed_nodes": seed_nodes[:10], "nodes": nodes[:limit],
            "edges": edges[:limit * 3], "node_count": len(nodes),
            "edge_count": len(edges)}


# ----------------------------------------------------------------- global search
def global_search(store: GraphStore, query: str, limit: int = 8) -> dict:
    """Community-summary retrieval (map stage of the map-reduce pattern)."""
    communities = store.list_communities(limit=5000)
    if not communities:
        return {"mode": "global", "query": query, "communities": [], "community_count": 0}
    docs = [f"{c['title']} {c['summary']}" for c in communities]
    scores = _bm25_scores(query, docs)
    ranked = sorted(zip(communities, scores), key=lambda kv: (-kv[1], kv[0]["community_id"]))
    out = []
    for c, s in ranked[:limit]:
        out.append({**c, "score": round(float(s), 5)})
    return {"mode": "global", "query": query, "communities": out,
            "community_count": len(communities)}


# ------------------------------------------------------------------ hybrid search
def hybrid_search(store: GraphStore, query: str, depth: int = 2,
                  local_limit: int = 25, global_limit: int = 6,
                  evidence: list[dict] | None = None) -> dict:
    """Local + global graph retrieval, optionally fused with classic hybrid evidence."""
    loc = local_search(store, query, depth=depth, limit=local_limit)
    glo = global_search(store, query, limit=global_limit)

    merged: dict[str, dict] = {}
    for n in loc["nodes"]:
        merged[n["node_id"]] = {**n, "channels": ["local"], "score": float(n.get("score", 0.0))}
    for c in glo["communities"]:
        for mid in c.get("members", []):
            entry = merged.get(mid)
            if entry is None:
                node = store.get_node(mid)
                if not node:
                    continue
                entry = {**node, "score": 0.0, "channels": []}
                merged[mid] = entry
            entry["channels"].append("global")
            entry["score"] = float(entry.get("score", 0.0)) + 0.25 * float(c.get("score", 0.0))

    nodes = sorted(merged.values(), key=lambda n: (-n["score"], -n["degree"], n["label"]))
    chunk_scores = _fuse_with_evidence(nodes, evidence or [])
    return {"mode": "hybrid", "query": query, "nodes": nodes[:local_limit],
            "edges": loc["edges"], "communities": glo["communities"],
            "seeds": loc["seeds"], "seed_nodes": loc["seed_nodes"],
            "node_count": len(nodes), "edge_count": len(loc["edges"]),
            "chunk_scores": chunk_scores}


def _fuse_with_evidence(nodes: list[dict], evidence: list[dict]) -> dict[str, float]:
    """Attach chunk-level hybrid scores to graph nodes that point at those chunks."""
    out: dict[str, float] = {}
    for c in evidence:
        cid = c.get("chunk_id", "")
        if not cid:
            continue
        out[cid] = float(c.get("rerank_score") or c.get("fused_score") or 0.0)
    return out


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Reciprocal rank fusion over several ranked id lists (deterministic)."""
    scores: dict[str, float] = defaultdict(float)
    for ids in rank_lists:
        for rank, nid in enumerate(ids):
            scores[nid] += 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
