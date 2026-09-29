"""Retrieval + answer + operational metrics (spec §22)."""
from __future__ import annotations


def recall_at_k(retrieved: list[str], gold: list[str], k: int) -> float:
    if not gold:
        return 1.0 if not retrieved else 0.0  # abstention-expected items handled by caller
    return len(set(retrieved[:k]) & set(gold)) / len(set(gold))


def mrr(retrieved: list[str], gold: list[str]) -> float:
    for i, cid in enumerate(retrieved, start=1):
        if cid in set(gold):
            return 1.0 / i
    return 0.0


def ndcg(retrieved: list[str], gold: list[str], k: int = 10) -> float:
    import math
    dcg = sum(1.0 / math.log2(i + 2) for i, cid in enumerate(retrieved[:k]) if cid in set(gold))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(set(gold)), k)))
    return dcg / (ideal or 1.0)


def citation_precision_recall(verdicts: list[dict]) -> tuple[float, float]:
    prec = sum(v["supported"] for v in verdicts) / max(1, len(verdicts))
    return round(prec, 4), round(prec, 4)  # claim-support proxy; recall needs gold claims
