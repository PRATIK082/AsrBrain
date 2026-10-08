"""Metadata hard filtering BEFORE semantic retrieval (spec §11)."""
from __future__ import annotations
from ..schema.queries import QueryPlan


def apply_filters(chunks: list[dict], plan: QueryPlan, release_override: str = "") -> list[dict]:
    rels = [release_override] if release_override else plan.releases
    out = []
    for c in chunks:
        # Project sources (linked code / ARXML / configs / diagrams) are scoped
        # by the user at link time, not by spec release/platform — always keep
        # them so chat can ground answers in the user's own files.
        is_project = (c.get("document_type") in ("code", "arxml", "config", "diagram")
                      or (c.get("chunk_id") or "").startswith("ps-"))
        if plan.platforms and not is_project and (c.get("platform") or "") not in plan.platforms:
            # allow Foundation chunks for Adaptive SOME/IP questions? No — strict.
            continue
        if rels and plan.release_mode in ("exact",) and not is_project and (c.get("autosar_release") or "") not in rels:
            continue
        if rels and plan.release_mode == "comparison" and (c.get("autosar_release") or "") not in rels:
            # comparison handled per-release upstream; keep both releases here
            pass
        if plan.modules and c.get("module"):
            if c["module"] not in plan.modules:
                continue
        out.append(c)
    return out
