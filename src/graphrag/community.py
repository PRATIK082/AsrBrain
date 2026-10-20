"""Community detection + deterministic community summaries for GraphRAG global search.

Label propagation over the undirected projection of the knowledge graph.  It is
deterministic (nodes are visited in sorted order, ties broken by label) so a rebuild
produces the same communities - important for review and for diffing graph changes.

Summaries are generated without a model call: they list the highest-degree members,
the strongest relations and the requirement / module vocabulary of the community.
An LLM can refine them later (opt-in), but the default answer path never depends on it.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .store import GraphStore


def _undirected_neighbors(store: GraphStore) -> dict[str, list[tuple[str, float]]]:
    nb: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in store.conn.execute("SELECT src,dst,weight FROM kg_edges").fetchall():
        w = float(row["weight"] or 1.0)
        nb[row["src"]].append((row["dst"], w))
        nb[row["dst"]].append((row["src"], w))
    return nb


def detect_communities(store: GraphStore, max_iter: int = 12,
                       max_communities: int = 200) -> list[dict]:
    """Label propagation. Returns community dicts ready for `replace_communities`."""
    nb = _undirected_neighbors(store)
    labels: dict[str, str] = {}
    for row in store.conn.execute("SELECT node_id FROM kg_nodes ORDER BY node_id").fetchall():
        labels[row["node_id"]] = row["node_id"]

    for _ in range(max_iter):
        changed = False
        for node in sorted(labels):
            counts: Counter = Counter()
            for other, w in nb.get(node, []):
                if other in labels:
                    counts[labels[other]] += w
            if not counts:
                continue
            best = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if best != labels[node]:
                labels[node] = best
                changed = True
        if not changed:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    for node, lab in labels.items():
        groups[lab].append(node)

    communities: list[dict] = []
    for idx, (label, members) in enumerate(sorted(groups.items(),
                                                  key=lambda kv: (-len(kv[1]), kv[0]))):
        if len(members) < 2 and len(groups) > 1:
            continue
        cid = f"c{idx:03d}"
        summary = summarize_community(store, members)
        title = _community_title(store, members)
        communities.append({"community_id": cid, "title": title, "summary": summary,
                            "members": sorted(members), "level": 0,
                            "properties": {"size": len(members)}})
        if len(communities) >= max_communities:
            break
    return communities


def summarize_community(store: GraphStore, members: list[str], max_members: int = 12) -> str:
    """Deterministic, citation-friendly summary of one community."""
    if not members:
        return ""
    nodes = []
    for m in members:
        n = store.get_node(m)
        if n:
            nodes.append(n)
    nodes.sort(key=lambda n: (-n["degree"], n["label"]))
    top = nodes[:max_members]
    member_set = set(members)

    rel_counter: Counter = Counter()
    for row in store.conn.execute("SELECT src,dst,rel,weight FROM kg_edges").fetchall():
        if row["src"] in member_set and row["dst"] in member_set:
            rel_counter[row["rel"]] += 1
    top_rels = ", ".join(f"{r}({c})" for r, c in rel_counter.most_common(4)) or "none"

    by_type: Counter = Counter(n["type"] for n in nodes)
    type_str = ", ".join(f"{t}:{c}" for t, c in by_type.most_common(5))
    reqs = [n["label"] for n in nodes if n["type"] == "requirement"][:5]
    mods = [n["label"] for n in nodes if n["type"] == "module"][:5]

    parts = [f"{len(nodes)} nodes", f"types[{type_str}]", f"relations[{top_rels}]"]
    if mods:
        parts.append("modules[" + ", ".join(mods) + "]")
    if reqs:
        parts.append("requirements[" + ", ".join(reqs) + "]")
    parts.append("key[" + ", ".join(f"{n['type']}:{n['label']}" for n in top) + "]")
    return " | ".join(parts)


def _community_title(store: GraphStore, members: list[str]) -> str:
    best_label = ""
    best_score = -1.0
    for m in members:
        n = store.get_node(m)
        if not n:
            continue
        score = n["degree"] + (2.0 if n["type"] == "module" else 0.0)
        if score > best_score:
            best_score = score
            best_label = n["label"]
    return best_label or (members[0] if members else "")
