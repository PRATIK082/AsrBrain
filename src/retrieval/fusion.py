"""RRF + query-type weighted fusion (spec §13)."""
from __future__ import annotations

DEFAULT_WEIGHTS = {
    "definition": (0.5, 0.35, 0.15), "api_lookup": (0.65, 0.2, 0.15),
    "requirement_lookup": (0.65, 0.2, 0.15), "configuration": (0.5, 0.25, 0.25),
    "comparison": (0.4, 0.4, 0.2), "dependency": (0.25, 0.25, 0.5),
    "troubleshooting": (0.5, 0.3, 0.2), "deep_explanation": (0.25, 0.55, 0.2),
    "architecture": (0.25, 0.55, 0.2), "unknown": (0.4, 0.4, 0.2),
}


def rrf(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    scores: dict[str, float] = {}
    for lst in rank_lists:
        for rank, cid in enumerate(lst, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


def weighted_fusion(bm25: dict[str, float], dense: dict[str, float], intent: str) -> dict[str, float]:
    wb, wd, _ = DEFAULT_WEIGHTS.get(intent, DEFAULT_WEIGHTS["unknown"])
    # min-max normalise each channel
    def norm(d):
        if not d:
            return {}
        lo, hi = min(d.values()), max(d.values())
        rng = (hi - lo) or 1.0
        return {cid: (v - lo) / rng for cid, v in d.items()}
    nb, nd = norm(bm25), norm(dense)
    out: dict[str, float] = {}
    for cid in set(nb) | set(nd):
        out[cid] = wb * nb.get(cid, 0.0) + wd * nd.get(cid, 0.0)
    return out
