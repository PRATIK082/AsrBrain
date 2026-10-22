"""Metadata hard filtering BEFORE semantic retrieval.

The module filter is relaxed when the surviving pool is too small to answer the
question — not only when it is completely empty. Chunks with an empty ``module`` field
are always kept, so a plan that names a module which is absent from the indexed
documents would otherwise leave a pool of only module-less project-source chunks while
thousands of useful chunks are discarded, and the retriever returns nothing for a
question whose answer is in the corpus.

The relaxation decision is reported in the trace so the user can see that a filter
was dropped.
"""
from __future__ import annotations

from ..schema.queries import QueryPlan
from .flags import RetrievalFlags, default_flags


def _release_match(chunk_release: str, wanted: list[str]) -> bool:
    """Query labels may be short ("4.4") while chunks carry full labels ("4.4.0").

    A chunk matches when its release equals the wanted label or extends it on a
    version boundary ("4.4" matches "4.4.0" but never "4.40.x"). Without this, an
    exact-release question filters out its own answer and the pool is empty.
    """
    cr = chunk_release or ""
    for w in wanted:
        if cr == w or (w and cr.startswith(w + ".")):
            return True
    return False


def _keep(chunks: list[dict], plan: QueryPlan, rels: list[str],
          module_constraint: bool) -> list[dict]:
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
        if rels and plan.release_mode in ("exact",) and not is_project \
                and not _release_match(c.get("autosar_release") or "", rels):
            continue
        if rels and plan.release_mode == "comparison" \
                and not _release_match(c.get("autosar_release") or "", rels):
            # comparison handled per-release upstream; keep both releases here
            pass
        if module_constraint and plan.modules and c.get("module"):
            if c["module"] not in plan.modules:
                continue
        out.append(c)
    return out


def apply_filters_ex(chunks: list[dict], plan: QueryPlan, release_override: str = "",
                     flags: RetrievalFlags | None = None) -> tuple[list[dict], dict]:
    """Filter the corpus and report what was relaxed.

    Returns ``(chunks, trace)`` where the trace says which constraint was dropped and why.
    """
    flags = flags or default_flags()
    rels = [release_override] if release_override else plan.releases
    trace: dict = {"relaxed": [], "pool_size": 0, "corpus_size": len(chunks)}

    use_module = bool(flags.module_filter and plan.modules)
    out = _keep(chunks, plan, rels, module_constraint=use_module)

    if use_module:
        # A pool that is a tiny remnant of the corpus cannot answer the question: the module
        # the plan inferred is simply not represented in the indexed documents. An empty
        # pool relaxes unconditionally — answering from general evidence beats abstaining.
        floor = max(1, int(len(chunks) * flags.pool_relax_ratio))
        if not out or len(out) < floor:
            relaxed = _keep(chunks, plan, rels, module_constraint=False)
            if len(relaxed) > len(out):
                trace["relaxed"].append({
                    "constraint": "module",
                    "requested": list(plan.modules),
                    "pool_before": len(out),
                    "pool_after": len(relaxed),
                    "reason": "the inferred module is not represented in the indexed documents; "
                              "answering from general evidence beats abstaining",
                })
                out = relaxed

    trace["pool_size"] = len(out)
    return out, trace


def apply_filters(chunks: list[dict], plan: QueryPlan, release_override: str = "",
                  flags: RetrievalFlags | None = None) -> list[dict]:
    """Filter the corpus. Kept for the existing call sites and tests."""
    out, _ = apply_filters_ex(chunks, plan, release_override=release_override, flags=flags)
    return out
