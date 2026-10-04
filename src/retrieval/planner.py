"""Modality-aware query planner (spec §9). Wraps deterministic parse(); never mixes releases."""
from __future__ import annotations

INTENT_MODALITIES = {
    "api_lookup": ["api", "requirement", "text", "configuration", "table"],
    "requirement_lookup": ["requirement", "text", "table"],
    "configuration": ["configuration", "table", "text", "api"],
    "comparison": ["api", "requirement", "configuration", "text", "table", "diagram"],
    "dependency": ["diagram", "graph", "text", "api"],
    "deep_explanation": ["text", "diagram", "table", "graph", "requirement", "api"],
    "troubleshooting": ["requirement", "api", "text", "table"],
    "definition": ["text", "requirement"],
    "unknown": ["text", "requirement", "api"],
}


def plan(query: str) -> dict:
    from .query_understanding import parse
    p = parse(query)
    base = p.model_dump() if hasattr(p, "model_dump") else dict(p)
    intent = base.get("intent", "unknown")
    modalities = list(INTENT_MODALITIES.get(intent, INTENT_MODALITIES["unknown"]))
    ql = query.lower()
    if any(w in ql for w in ("diagram", "figure", "path from", "communication path", "sequence")):
        for m in ("diagram", "graph"):
            if m not in modalities:
                modalities.append(m)
    if "table" in ql or "parameter" in ql or "container" in ql:
        if "table" not in modalities:
            modalities.append("table")
    needs_graph = bool(base.get("needs_graph_search")) or intent in ("dependency", "deep_explanation")
    comparison = base.get("release_mode") == "comparison"
    return {**base, "required_modalities": modalities,
            "needs_graph_traversal": needs_graph,
            "comparison_mode": comparison,
            # releases filtered independently per branch; alignment happens after retrieval
            "release_branches": list(base.get("releases", [])) if comparison else []}
