"""Local reranker: exact-identifier boost + lexical overlap (cross-encoder hook when configured)."""
from __future__ import annotations
from ..indexing.hybrid import tokenize_technical


def rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    q_terms = set(tokenize_technical(query))
    req_tokens = {t for t in q_terms if len(t) > 5}
    scored = []
    for c in candidates:
        text = (c.get("section_title", "") + " " + c.get("normalized_text", "")).lower()
        overlap = len(q_terms & set(tokenize_technical(text))) / max(1, len(q_terms))
        exact = 0.0
        for rid in c.get("requirement_ids", []) + c.get("api_names", []):
            if rid.lower() in query.lower():
                exact += 0.5
        score = c.get("fused_score", 0.0) * 0.6 + overlap * 0.3 + min(exact, 1.0) * 0.4
        scored.append({**c, "rerank_score": round(float(score), 4)})
    scored.sort(key=lambda d: d["rerank_score"], reverse=True)
    return scored[:top_n]
