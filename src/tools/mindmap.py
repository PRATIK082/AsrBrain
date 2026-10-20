"""Mindmap generation: deterministic Mermaid `mindmap` blocks for any topic.

Three sources are supported and all of them end in the same renderer:

* **graph**    - neighbourhood of a topic inside the GraphRAG knowledge graph
* **evidence** - the classic retrieval evidence of a question (documents -> modules ->
                 requirements -> APIs), used when the graph is empty
* **outline**  - an explicit hierarchy supplied by the caller (agent workflows)

The renderer never invents nodes: every leaf maps back to a chunk id, file or ARXML
xpath that the UI can turn into a citation.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------- helpers
_SAFE_RE = re.compile(r"[^\w\s\-./:+#()\[\]]", re.UNICODE)


def sanitize(label: str, max_len: int = 80) -> str:
    """Make a label safe for a Mermaid mindmap node."""
    text = " ".join(str(label).split())
    text = text.replace('"', "'").replace("`", "'")
    text = _SAFE_RE.sub("", text)
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text or "untitled"


def _node_line(node_id: str, label: str, indent: int, shape: str = "square") -> str:
    pad = "  " * indent
    text = sanitize(label)
    if shape == "root":
        return f'{pad}{node_id}(("{text}"))'
    return f'{pad}{node_id}["{text}"]'


# --------------------------------------------------------------------- renderer
def render_mermaid(tree: dict) -> str:
    """Render a nested dict tree as a Mermaid mindmap.

    Tree shape::

        {"label": "root", "children": [{"label": "branch", "children": [...]}]}
    """
    lines = ["mindmap"]
    counter = {"i": 0}

    def next_id() -> str:
        counter["i"] += 1
        return f"n{counter['i']}"

    def walk(node: dict, indent: int, node_id: str | None = None) -> None:
        if node_id is None:
            node_id = next_id()
            lines.append(_node_line(node_id, node.get("label", ""), indent, "root"))
        else:
            lines.append(_node_line(node_id, node.get("label", ""), indent))
        for child in node.get("children", []) or []:
            walk(child, indent + 1, next_id())

    walk(tree, 1)
    return "\n".join(lines)


def tree_from_pairs(pairs: list[tuple[str, list[str]]], topic: str) -> dict:
    """Build a two-level tree (branch -> leaves) from `(branch, [leaf, ...])` pairs."""
    children = []
    for branch, leaves in pairs:
        if not leaves:
            continue
        children.append({"label": branch,
                         "children": [{"label": leaf} for leaf in leaves]})
    return {"label": topic, "children": children}


# ------------------------------------------------------------------ graph based
def mindmap_from_graph(store, topic: str, depth: int = 2, max_branches: int = 12,
                       max_leaves: int = 25) -> dict:
    """Neighbourhood mindmap of a topic inside the knowledge graph."""
    from ..graphrag.retrieval import local_search
    res = local_search(store, topic, depth=depth, limit=120)
    nodes = res.get("nodes", [])
    citations: dict[str, str] = {}
    groups: dict[str, list[str]] = {
        "Requirements": [], "APIs": [], "ARXML Ports": [], "Interfaces": [],
        "Software Components": [], "Runnables": [], "ECUC Parameters": [],
        "Code Functions": [], "Test Cases": [], "Modules": [], "Documents": [],
    }
    type_group = {
        "requirement": "Requirements", "api": "APIs", "port": "ARXML Ports",
        "interface": "Interfaces", "swc": "Software Components", "runnable": "Runnables",
        "ecuc_parameter": "ECUC Parameters", "function": "Code Functions",
        "test_case": "Test Cases", "module": "Modules", "document": "Documents",
    }
    for n in nodes:
        group = type_group.get(n.get("type", ""))
        if not group:
            continue
        label = n.get("label", "")
        if label not in groups[group]:
            groups[group].append(label)
        props = n.get("properties") or {}
        if props.get("chunk_id"):
            citations[label] = props["chunk_id"]
        elif props.get("file"):
            citations[label] = props["file"]
    pairs = [(g, groups[g][:max_leaves]) for g in groups if groups[g]]
    tree = tree_from_pairs(pairs[:max_branches], topic)
    return {"topic": topic, "source": "graph", "tree": tree,
            "mermaid": render_mermaid(tree), "nodes": nodes,
            "seeds": res.get("seeds", []), "citations": citations,
            "node_count": len(nodes), "empty": not pairs}


# ----------------------------------------------------------------- evidence based
def mindmap_from_evidence(evidence: list[dict], topic: str, max_branches: int = 12,
                          max_leaves: int = 25) -> dict:
    """Mindmap built from retrieval evidence (documents -> modules -> requirements)."""
    docs: dict[str, list[str]] = {}
    modules: dict[str, list[str]] = {}
    reqs: list[str] = []
    apis: list[str] = []
    citations: dict[str, str] = {}
    for c in evidence or []:
        doc = c.get("source_pdf") or c.get("document_id") or "document"
        section = c.get("section_title") or c.get("section_number") or ""
        label = f"{doc}{(' - ' + section) if section else ''}"
        docs.setdefault("Sources", [])
        if label not in docs["Sources"]:
            docs["Sources"].append(label)
        mod = c.get("module") or ""
        if mod:
            modules.setdefault(mod, [])
            for r in (c.get("requirement_ids") or [])[:5]:
                if r not in modules[mod]:
                    modules[mod].append(r)
        for r in (c.get("requirement_ids") or [])[:10]:
            if r not in reqs:
                reqs.append(r)
        for a in (c.get("api_names") or [])[:10]:
            if a not in apis:
                apis.append(a)
        if c.get("chunk_id"):
            citations[label] = c["chunk_id"]
    pairs: list[tuple[str, list[str]]] = []
    if reqs:
        pairs.append(("Requirements", reqs[:max_leaves]))
    if apis:
        pairs.append(("APIs", apis[:max_leaves]))
    for mod, rlist in list(modules.items())[:max_branches]:
        pairs.append((f"Module: {mod}", rlist[:max_leaves]))
    if docs.get("Sources"):
        pairs.append(("Sources", docs["Sources"][:max_leaves]))
    tree = tree_from_pairs(pairs, topic)
    return {"topic": topic, "source": "evidence", "tree": tree,
            "mermaid": render_mermaid(tree), "citations": citations,
            "node_count": len(pairs), "empty": not pairs}


# ------------------------------------------------------------------ outline based
def mindmap_from_outline(outline: list[dict], topic: str) -> dict:
    """Mindmap from an explicit hierarchy (used by the agent workflows)."""
    tree = {"label": topic, "children": outline or []}
    return {"topic": topic, "source": "outline", "tree": tree,
            "mermaid": render_mermaid(tree), "citations": {}, "empty": not outline}


# --------------------------------------------------------------------- combined
def build_mindmap(topic: str, source: str = "auto", store=None, evidence: list[dict] | None = None,
                  outline: list[dict] | None = None, depth: int = 2) -> dict:
    """Entry point used by the `mindmap.build` tool and the REST API."""
    if source == "outline" and outline:
        return mindmap_from_outline(outline, topic)
    if source == "evidence":
        return mindmap_from_evidence(evidence or [], topic)
    if source == "graph":
        if store is None:
            from ..graphrag.runtime import get_store
            store = get_store()
        return mindmap_from_graph(store, topic, depth=depth)
    # auto: prefer the graph, fall back to evidence
    if store is None:
        from ..graphrag.runtime import get_store
        store = get_store()
    res = mindmap_from_graph(store, topic, depth=depth)
    if res.get("empty") and evidence:
        return mindmap_from_evidence(evidence, topic)
    return res
