"""C / C++ code tools: symbol scan, call graph, RTE<->ARXML mapping, advisory checks.

Everything here is advisory: findings describe what the source *shows*, they never
claim MISRA / ISO 26262 compliance.  Symbols and call sites carry file + line so the
agent can cite them.
"""
from __future__ import annotations

import os
import re

from ..graphrag.extractor import (FUNC_DEF_RE, INCLUDE_RE, RTE_CALL_RE,
                                  module_of_symbol)
from ..graphrag.runtime import get_store

CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
RESERVED = {"if", "for", "while", "switch", "return", "sizeof", "do", "else", "case",
            "defined", "typedef", "static_assert", "alignof", "break", "continue",
            "goto", "default", "va_start", "va_end", "va_arg", "va_copy", "offsetof"}


def scan_c_source(text: str, path: str = "<input>") -> dict:
    """Static scan of one C translation unit: functions, includes, call sites."""
    functions: list[dict] = []
    for m in FUNC_DEF_RE.finditer(text):
        name = m.group("name")
        if name in RESERVED:
            continue
        line = text[: m.start()].count("\n") + 1
        # body = from the opening brace to the matching closing brace (best effort)
        start = text.find("{", m.end() - 1)
        body = ""
        if start >= 0:
            depth = 0
            for i in range(start, min(len(text), start + 200000)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        body = text[start:i + 1]
                        break
        calls = [c for c in dict.fromkeys(CALL_RE.findall(body))
                 if c not in RESERVED and c != name]
        functions.append({"name": name, "file": path, "line": line,
                          "module": module_of_symbol(name),
                          "calls": calls,
                          "rte_calls": sorted(set(RTE_CALL_RE.findall(body)))})
    includes = [i for i in dict.fromkeys(INCLUDE_RE.findall(text))]
    return {"file": path, "functions": functions, "includes": includes,
            "rte_calls": sorted(set(RTE_CALL_RE.findall(text)))}


def code_symbols(path: str = "", source: str = "", module: str = "",
                 store=None) -> dict:
    """Symbols of a C file (path) or of an inline source snippet."""
    if source:
        res = scan_c_source(source, path or "<input>")
        return {"functions": res["functions"], "includes": res["includes"],
                "rte_calls": res["rte_calls"], "source": "inline"}
    if path:
        if not os.path.exists(path):
            return {"error": f"file not found: {path}", "functions": []}
        with open(path, encoding="utf-8", errors="replace") as f:
            res = scan_c_source(f.read(), path)
        return {"functions": res["functions"], "includes": res["includes"],
                "rte_calls": res["rte_calls"], "source": path}
    # no path/source -> read from the knowledge graph
    st = store or get_store()
    nodes = st.find_nodes(type="function", limit=5000)
    if module:
        nodes = [n for n in nodes if n["label"].startswith(module + "_")]
    return {"functions": [{"name": n["label"], "file": (n["properties"] or {}).get("file", ""),
                           "line": (n["properties"] or {}).get("line", 0),
                           "module": module_of_symbol(n["label"])}
                          for n in nodes],
            "includes": [], "rte_calls": [], "source": "graph"}


def code_callgraph(function: str, path: str = "", source: str = "",
                   depth: int = 2, store=None) -> dict:
    """Call graph around a function (callers + callees)."""
    if source or path:
        if source:
            res = scan_c_source(source, path or "<input>")
        else:
            if not os.path.exists(path):
                return {"error": f"file not found: {path}", "nodes": [], "edges": []}
            with open(path, encoding="utf-8", errors="replace") as f:
                res = scan_c_source(f.read(), path)
        fns = {f["name"]: f for f in res["functions"]}
        if function not in fns:
            return {"error": f"function not found: {function}", "nodes": [], "edges": []}
        nodes = [fns[function]]
        edges = []
        callers = [f for f in res["functions"] if function in f["calls"]]
        for c in callers:
            nodes.append(c)
            edges.append({"src": c["name"], "dst": function, "rel": "calls"})
        for callee in fns[function]["calls"]:
            edges.append({"src": function, "dst": callee, "rel": "calls"})
            if callee in fns and callee not in nodes:
                nodes.append(fns[callee])
        return {"root": function, "nodes": nodes, "edges": edges,
                "rte_calls": fns[function].get("rte_calls", []),
                "source": res["file"]}

    st = store or get_store()
    nid = f"function:{function}"
    if not st.get_node(nid):
        return {"error": f"function not in graph: {function}", "nodes": [], "edges": []}
    sub = st.neighbors(nid, depth=min(max(1, depth), 3), limit=100)
    return {"root": function, "nodes": sub["nodes"], "edges": sub["edges"],
            "source": "graph"}


def code_rte_map(source: str = "", path: str = "", port_names: list[str] | None = None,
                 store=None) -> dict:
    """Map RTE call sites to ARXML ports (name-overlap evidence only)."""
    from ..code_intelligence.advisory import map_rte_to_arxml, rte_call_sites
    if source:
        calls = rte_call_sites(source)
    elif path and os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:
            calls = rte_call_sites(f.read())
    else:
        st = store or get_store()
        calls = [n["label"] for n in st.find_nodes(type="api", label_contains="Rte_", limit=500)]
    ports = list(port_names or [])
    if not ports:
        st = store or get_store()
        ports = [n["label"] for n in st.find_nodes(type="port", limit=500)]
        ports += [n["label"] for n in st.find_nodes(type="interface", limit=500)]
    links = map_rte_to_arxml(calls, ports)
    return {"rte_calls": calls, "port_candidates": len(ports),
            "traceability": [lnk.model_dump() for lnk in links],
            "note": "name-overlap evidence only - verify against the ARXML model."}


def code_analyze(source: str, path: str = "input.c") -> dict:
    """Advisory static checks on a C snippet (never a compliance verdict)."""
    from ..code_intelligence.advisory import preflight_checks, rte_call_sites
    findings = preflight_checks(source, path)
    return {"findings": [f.model_dump() for f in findings],
            "rte_calls": rte_call_sites(source),
            "disclaimer": "Advisory only - not a MISRA/ISO 26262 compliance determination."}
