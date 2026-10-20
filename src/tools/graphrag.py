"""GraphRAG tools: search, neighbourhoods, paths, communities and graph build."""
from __future__ import annotations

from ..graphrag.runtime import get_store


def _store(store=None):
    return store or get_store()


def graph_search(query: str, mode: str = "hybrid", depth: int = 2, limit: int = 25,
                 store=None) -> dict:
    """Search the knowledge graph. mode = local | global | hybrid."""
    st = _store(store)
    if mode == "local":
        from ..graphrag.retrieval import local_search
        res = local_search(st, query, depth=depth, limit=limit)
    elif mode == "global":
        from ..graphrag.retrieval import global_search
        res = global_search(st, query, limit=limit)
    else:
        from ..graphrag.retrieval import hybrid_search
        res = hybrid_search(st, query, depth=depth, local_limit=limit)
    res["stats"] = st.stats()
    return res


def graph_neighbors(node: str, depth: int = 1, limit: int = 120, store=None) -> dict:
    """Neighbourhood of one graph node (label or `type:label` id)."""
    st = _store(store)
    nid = node if node.startswith(("module:", "requirement:", "api:", "port:", "interface:",
                                   "swc:", "runnable:", "ecuc_parameter:", "function:",
                                   "test_case:", "document:", "concept:", "error_code:",
                                   "connector:", "community:")) else ""
    if not nid:
        row = st.conn.execute("SELECT node_id FROM kg_nodes WHERE label = ? "
                              "ORDER BY degree DESC LIMIT 1", (node,)).fetchone()
        if not row:
            return {"found": False, "node": node, "nodes": [], "edges": [],
                    "error": "node not found"}
        nid = row["node_id"]
    sub = st.neighbors(nid, depth=depth, limit=limit)
    sub["found"] = True
    sub["node"] = nid
    return sub


def graph_path(source: str, target: str, max_depth: int = 6, store=None) -> dict:
    """Shortest path between two nodes (relationship explanation)."""
    st = _store(store)
    src = _resolve(st, source)
    dst = _resolve(st, target)
    if not src or not dst:
        return {"found": False, "path": [], "edges": [],
                "error": "source or target node not found"}
    res = st.shortest_path(src, dst, max_depth=max_depth)
    res["source"] = src
    res["target"] = dst
    return res


def graph_communities(query: str = "", limit: int = 10, store=None) -> dict:
    """List communities, optionally ranked against a query (global GraphRAG)."""
    st = _store(store)
    if query:
        from ..graphrag.retrieval import global_search
        res = global_search(st, query, limit=limit)
        return res
    return {"communities": st.list_communities(limit=limit), "query": query}


def graph_community(community_id: str, store=None) -> dict:
    st = _store(store)
    c = st.get_community(community_id)
    if not c:
        return {"found": False, "community_id": community_id}
    members = []
    for nid in c.get("members", []):
        n = st.get_node(nid)
        if n:
            members.append(n)
    return {"found": True, **c, "member_details": members}


def graph_stats(store=None) -> dict:
    st = _store(store)
    return st.stats()


def graph_build(canonical_db: str = "", code_dirs: list[str] | None = None,
                clear: bool = True, store=None) -> dict:
    """(Re)build the knowledge graph from the canonical store + code directories."""
    from ..config.settings import settings
    from ..graphrag.builder import build_graph
    from ..indexing.hybrid import load_chunks
    st = _store(store)
    chunks = load_chunks(canonical_db or settings.canonical_db)
    result = build_graph(st, chunks, code_roots=list(code_dirs or []), clear=clear)
    return {"built": True, **result}


def _resolve(st, label: str) -> str:
    if not label:
        return ""
    row = st.conn.execute("SELECT node_id FROM kg_nodes WHERE node_id = ?", (label,)).fetchone()
    if row:
        return row["node_id"]
    row = st.conn.execute("SELECT node_id FROM kg_nodes WHERE label = ? "
                          "ORDER BY degree DESC LIMIT 1", (label,)).fetchone()
    if row:
        return row["node_id"]
    row = st.conn.execute("SELECT node_id FROM kg_nodes WHERE label LIKE ? "
                          "ORDER BY degree DESC LIMIT 1", (f"%{label}%",)).fetchone()
    return row["node_id"] if row else ""
