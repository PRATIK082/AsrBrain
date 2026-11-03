"""Bounded reasoning helpers (Slice 5).

Deterministic, observable planning primitives. Agent-style execution is intentionally
bounded: no arbitrary tool calls, no document mutation, no config changes. Retrieved
text is treated as data, never as instructions.
"""
from __future__ import annotations
from typing import Any


MAX_HOPS = 3
MAX_EVIDENCE = 24


def bounded_plan(query: str, plan: Any) -> list[str]:
    from ..retrieval.multi_hop import decompose_query
    steps = decompose_query(query, plan)
    return steps[:MAX_HOPS]


def should_stop(evidence: list[dict], hop: int) -> bool:
    if hop >= MAX_HOPS:
        return True
    if len(evidence) >= MAX_EVIDENCE:
        return True
    return False


def summarize_conflicts(conflicts: list[dict]) -> str:
    if not conflicts:
        return "No conflicts detected in retrieved evidence."
    lines = []
    for c in conflicts:
        lines.append(f"- {c.get('type')}: releases {c.get('releases')} ids {c.get('requirement_ids')}")
    return "\n".join(lines)
