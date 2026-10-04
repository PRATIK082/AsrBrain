"""Vector-graph fusion with spec starting weights (spec §10). Additive over fusion.py."""
from __future__ import annotations
from .fusion import rrf

# (lexical, dense, graph, modality/table) starting values — tune against benchmark.
SPEC_WEIGHTS = {
    "api_lookup": (0.60, 0.20, 0.10, 0.10),       # exact lookup
    "requirement_lookup": (0.60, 0.20, 0.10, 0.10),
    "definition": (0.60, 0.20, 0.10, 0.10),
    "deep_explanation": (0.20, 0.35, 0.30, 0.15),  # architecture
    "dependency": (0.20, 0.35, 0.30, 0.15),
    "configuration": (0.45, 0.20, 0.20, 0.15),
    "troubleshooting": (0.40, 0.25, 0.25, 0.10),
    "comparison": (0.40, 0.30, 0.15, 0.15),
    "unknown": (0.40, 0.30, 0.15, 0.15),
}


def _norm(d: dict[str, float]) -> dict[str, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    rng = (hi - lo) or 1.0
    return {k: (v - lo) / rng for k, v in d.items()}


def fuse(lexical: dict[str, float], dense: dict[str, float],
         graph: dict[str, float] | None = None,
         modality: dict[str, float] | None = None,
         intent: str = "unknown") -> dict[str, float]:
    wl, wd, wg, wm = SPEC_WEIGHTS.get(intent, SPEC_WEIGHTS["unknown"])
    n = [_norm(lexical), _norm(dense), _norm(graph or {}), _norm(modality or {})]
    out: dict[str, float] = {}
    for cid in set(n[0]) | set(n[1]) | set(n[2]) | set(n[3]):
        out[cid] = wl * n[0].get(cid, 0.0) + wd * n[1].get(cid, 0.0) \
            + wg * n[2].get(cid, 0.0) + wm * n[3].get(cid, 0.0)
    return out


def fuse_rrf(lists: list[list[str]]) -> dict[str, float]:
    return rrf(lists)
