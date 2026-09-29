"""Conversational slot-filling (req. 1–2): no corpus-filter sidebar.

- Release/platform: if the question lacks them AND the corpus spans several, ask back.
- Module: auto-detected, shown with Confirm/Change — filter applies only after confirm
  or when the user named it explicitly.
- Document type: always auto (query-routed), trace-only, never a required question.
"""
from __future__ import annotations
from ..schema.queries import QueryPlan

RELEASE_TOKENS = ("4.2", "4.3", "4.4", "R19", "R20", "R21", "R22", "R23", "R24")


def _get(plan, key: str, default=None):
    if isinstance(plan, dict):
        return plan.get(key, default)
    return getattr(plan, key, default)


def missing_slots(plan, corpus_releases: list[str] | None = None,
                  corpus_platforms: list[str] | None = None) -> list[str]:
    """Which slots must be asked back. Module/doctype are never 'missing' (auto)."""
    missing = []
    if not _get(plan, "releases", []) and (corpus_releases is None or len(set(corpus_releases)) > 1):
        missing.append("release")
    if not _get(plan, "platforms", []) and (corpus_platforms is None or len(set(corpus_platforms)) > 1):
        missing.append("platform")
    return missing


def clarification_question(plan, missing: list[str]) -> str:
    modules = _get(plan, "modules", []) or []
    bits = []
    if "release" in missing:
        bits.append("which AUTOSAR release (e.g. 4.4.0, R22-11)")
    if "platform" in missing:
        bits.append("which platform (Classic / Adaptive / Foundation)")
    q = "To answer precisely, please tell me " + " and ".join(bits) + "."
    if modules:
        q += f"\n\nI detected module(s): **{', '.join(modules)}** — confirm, or tell me to change it."
    q += "\n\n(Or say “any release” / “all versions” and I’ll answer generally with per-release evidence.)"
    return q


def apply_user_confirmation(plan: QueryPlan, text: str) -> QueryPlan:
    """Fold a clarification reply (or chip click) back into the plan."""
    from .query_understanding import parse as _parse
    extra = _parse(text)
    if extra.releases:
        plan.releases = sorted(set(plan.releases) | set(extra.releases))
        if plan.release_mode == "none":
            plan.release_mode = "exact" if len(plan.releases) == 1 else "comparison"
            plan.needs_comparison_table = len(plan.releases) > 1
    if extra.platforms:
        plan.platforms = sorted(set(plan.platforms) | set(extra.platforms))
    if extra.modules:
        plan.modules = sorted(set(plan.modules) | set(extra.modules))
    tl = text.lower()
    if "any release" in tl or "all versions" in tl:
        plan.releases = []
        plan.release_mode = "none"
    return plan
