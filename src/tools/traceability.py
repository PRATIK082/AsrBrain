"""Traceability tools: requirement <-> ARXML <-> C code <-> test case links.

Every link carries a confidence and the evidence that produced it.  Links derived
from name overlap are flagged `is_inferred` so an engineer can tell a confirmed
annotation from a suspected match.
"""
from __future__ import annotations

from ..graphrag.runtime import get_store


def _st(store=None):
    return store or get_store()


def _links_for(st, node_type: str, node_id: str, limit: int = 100) -> list[dict]:
    """All trace links that touch a node, in both directions."""
    out: list[dict] = []
    seen: set[str] = set()
    for link in st.trace_links(source_type=node_type, source_id=node_id, limit=limit):
        if link["link_id"] not in seen:
            seen.add(link["link_id"])
            out.append(link)
    for link in st.trace_links(target_type=node_type, target_id=node_id, limit=limit):
        if link["link_id"] not in seen:
            seen.add(link["link_id"])
            out.append(link)
    return out


def _req_node_id(label: str) -> str:
    """Normalize a requirement label to its graph node id."""
    label = (label or "").strip()
    return label if label.startswith("requirement:") else f"requirement:{label}"


def _seed_nodes(st, query: str, limit: int = 20) -> list[dict]:
    """Graph nodes that match a free-text query.

    A natural-language query rarely equals a node label, so the raw query is tried
    first and the deterministic identifier extraction (requirement IDs, test IDs,
    function names, AUTOSAR module names) supplies the fallbacks.
    """
    from ..graphrag.extractor import seed_labels
    out: list[dict] = []
    seen: set[str] = set()
    for candidate in [query] + seed_labels(query, limit=8):
        candidate = (candidate or "").strip()
        if not candidate:
            continue
        for node in st.find_nodes(limit=limit, label_contains=candidate):
            if node["node_id"] in seen:
                continue
            seen.add(node["node_id"])
            out.append(node)
    return out


def trace_links(source_type: str = "", source_id: str = "", target_type: str = "",
                target_id: str = "", limit: int = 100, store=None) -> dict:
    """Raw trace links filtered by type/id."""
    st = _st(store)
    links = st.trace_links(source_type=source_type, source_id=source_id,
                           target_type=target_type, target_id=target_id, limit=limit)
    return {"links": links, "count": len(links)}


def trace_requirements(query: str, limit: int = 40, store=None) -> dict:
    """Requirements reachable from a symbol / port / module / API name."""
    st = _st(store)
    q = (query or "").strip()
    if not q:
        return {"query": q, "requirements": [], "count": 0}
    seeds = _seed_nodes(st, q)
    req_ids: dict[str, dict] = {}
    for seed in seeds:
        for link in _links_for(st, seed["type"], seed["node_id"], limit=limit):
            if link["target_type"] == "requirement":
                rid = _req_node_id(link["target_id"])
                req_ids.setdefault(rid, {"requirement": rid,
                                         "via": seed["label"], "confidence": link["confidence"],
                                         "is_inferred": link["is_inferred"]})
            elif link["source_type"] == "requirement":
                rid = _req_node_id(link["source_id"])
                req_ids.setdefault(rid, {"requirement": rid,
                                         "via": seed["label"], "confidence": link["confidence"],
                                         "is_inferred": link["is_inferred"]})
    # direct requirement lookup by exact id
    nid = _req_node_id(q)
    if st.get_node(nid) and nid not in req_ids:
        req_ids[nid] = {"requirement": nid, "via": "direct", "confidence": 1.0,
                        "is_inferred": False}
    out = sorted(req_ids.values(), key=lambda r: (-r["confidence"], r["requirement"]))
    return {"query": q, "requirements": out[:limit], "count": len(out)}


def trace_tests(query: str, limit: int = 40, store=None) -> dict:
    """Test cases that cover a requirement / API."""
    st = _st(store)
    q = (query or "").strip()
    tests: dict[str, dict] = {}
    for seed in _seed_nodes(st, q):
        for link in _links_for(st, seed["type"], seed["node_id"], limit=limit):
            for src, dst in ((link["source_type"], link["target_type"]),
                             (link["target_type"], link["source_type"])):
                if src == "test_case" and dst in ("requirement", "api"):
                    tests.setdefault(link["source_id"] if src == "test_case" else link["target_id"],
                                     {"test_case": link["source_id"] if src == "test_case" else link["target_id"],
                                      "covers": link["target_id"] if src == "test_case" else link["source_id"],
                                      "confidence": link["confidence"],
                                      "is_inferred": link["is_inferred"]})
    out = sorted(tests.values(), key=lambda t: (-t["confidence"], t["test_case"]))
    return {"query": q, "tests": out[:limit], "count": len(out)}


def trace_matrix(module: str = "", limit: int = 200, store=None) -> dict:
    """Requirement / code / test matrix for a module (or the whole graph)."""
    st = _st(store)
    prefix = f"{module}_" if module else ""
    requirements: list[str] = []
    functions: list[str] = []
    tests: list[str] = []
    apis: list[str] = []
    for n in st.find_nodes(type="requirement", limit=100000):
        if not prefix or n["label"].upper().find(module.upper()) >= 0:
            requirements.append(n["node_id"])
    for n in st.find_nodes(type="function", limit=100000):
        if not prefix or n["label"].startswith(prefix):
            functions.append(n["node_id"])
    for n in st.find_nodes(type="api", limit=100000):
        if not prefix or n["label"].startswith(prefix) or n["label"].startswith("Rte_"):
            apis.append(n["node_id"])
    for n in st.find_nodes(type="test_case", limit=100000):
        tests.append(n["node_id"])

    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for rid in requirements:
        req_links = _links_for(st, "requirement", rid, limit=limit)
        for link in req_links:
            # the requirement may be either end of the link
            other_type, other_id = (link["target_type"], link["target_id"])
            if link["target_type"] == "requirement":
                other_type, other_id = (link["source_type"], link["source_id"])
            if other_type not in ("api", "function", "test_case"):
                continue
            key = (rid, other_id if other_type == "api" else "",
                   other_id if other_type == "function" else "")
            if key in seen:
                continue
            seen.add(key)
            rows.append({"requirement": rid,
                         "api": other_id if other_type == "api" else "",
                         "function": other_id if other_type == "function" else "",
                         "test_case": other_id if other_type == "test_case" else "",
                         "confidence": link["confidence"],
                         "is_inferred": link["is_inferred"]})
    rows.sort(key=lambda r: (-r["confidence"], r["requirement"]))
    return {"module": module or "*", "requirements": len(requirements),
            "requirement_ids": requirements,
            "functions": len(functions), "apis": len(apis), "test_cases": len(tests),
            "rows": rows[:limit], "row_count": len(rows),
            "note": "Links inferred from name overlap are flagged is_inferred=true."}


def trace_gaps(module: str = "", store=None) -> dict:
    """Requirements without a code implementation or without a test case."""
    st = _st(store)
    matrix = trace_matrix(module=module, limit=100000, store=st)
    covered_code = {r["requirement"] for r in matrix["rows"] if r["function"] or r["api"]}
    covered_test = {r["requirement"] for r in matrix["rows"] if r["test_case"]}
    all_reqs = set(matrix["requirement_ids"])
    return {"module": module or "*",
            "without_code": sorted(all_reqs - covered_code),
            "without_test": sorted(all_reqs - covered_test),
            "total_requirements": len(all_reqs)}
