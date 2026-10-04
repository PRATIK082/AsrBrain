"""Multimodal context assembly rules (spec §11). Filters evidence before prompt build."""
from __future__ import annotations

TEXT_BUDGET = 12
MAX_TABLES = 4
MAX_DIAGRAMS = 3


def include_image(item: dict, query_modalities: list[str], budget_left: int) -> bool:
    if budget_left <= 0:
        return False
    needs_visual = any(m in query_modalities for m in ("diagram", "image", "graph"))
    strongly_related = float(item.get("score", 0.0)) >= 0.3 or bool(item.get("caption"))
    has_page = item.get("page_index") is not None or item.get("page_start") is not None
    return bool(needs_visual and strongly_related and has_page)


def assemble(evidence: list[dict], query_modalities: list[str],
             release_filter: list[str] | None = None) -> list[dict]:
    """Exact release filter first; then modality budgets. Never silently mixes releases."""
    out = list(evidence)
    if release_filter:
        exact = [e for e in out if (e.get("autosar_release") or e.get("release")) in release_filter]
        if exact:
            out = exact  # drop other releases rather than mixing
    texts = [e for e in out if (e.get("content_type", "text")) in ("text", "requirement", "api", "configuration")][:TEXT_BUDGET]
    tables = [e for e in out if e.get("content_type") == "table"][:MAX_TABLES]
    visuals: list[dict] = []
    for e in out:
        if e.get("content_type") in ("image", "diagram", "equation", "graph"):
            if len(visuals) >= MAX_DIAGRAMS:
                break
            if include_image(e, query_modalities, MAX_DIAGRAMS - len(visuals)):
                visuals.append(e)
    return texts + tables + visuals


def to_spec_claim(claim: str, evidence_ids: list[str], citation_valid: bool,
                  release_ok: bool, platform_ok: bool, score: float) -> dict:
    return {"claim": claim, "supported": bool(evidence_ids) and citation_valid,
            "evidence_ids": evidence_ids, "citation_valid": citation_valid,
            "release_consistent": release_ok, "platform_consistent": platform_ok,
            "support_score": round(float(score), 4)}
