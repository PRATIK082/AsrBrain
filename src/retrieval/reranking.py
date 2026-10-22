"""Local reranker: exact-identifier boost + lexical overlap (cross-encoder hook when configured)."""
from __future__ import annotations
import re
from ..indexing.hybrid import tokenize_technical

# Default weights, kept so existing callers see identical weighting.
# The retrieval pipeline passes RetrievalFlags with the measured weights instead.
_LEGACY_WEIGHTS = (0.6, 0.3, 0.4)

_QUERY_TOKENS_RE = re.compile(r"[A-Za-z0-9_]+")


def identifier_matches(query_tokens: set[str], identifier: str) -> bool:
    """True when a stored identifier is actually named in the query.

    A plain substring test ("sws_x_1" in "sws_x_11") promotes near-miss chunks, so the
    identifier must equal a whole query token. The signal extractor sometimes stores a
    truncated identifier ("prs_e2e_"), which is accepted as a prefix of a query token.
    """
    ident = (identifier or "").lower()
    if not ident or len(ident) < 4:
        return False
    if ident in query_tokens:
        return True
    return ident.endswith("_") and any(tok.startswith(ident) for tok in query_tokens)


def rerank(query: str, candidates: list[dict], top_n: int, flags=None) -> list[dict]:
    w_fused, w_overlap, w_exact = (_LEGACY_WEIGHTS if flags is None
                                   else (flags.w_fused, flags.w_overlap, flags.w_exact))
    q_terms = set(tokenize_technical(query))
    q_tokens = set(_QUERY_TOKENS_RE.findall(query.lower()))
    req_tokens = {t for t in q_terms if len(t) > 5}
    scored = []
    for c in candidates:
        text = (c.get("section_title", "") + " " + c.get("normalized_text", "")).lower()
        overlap = len(q_terms & set(tokenize_technical(text))) / max(1, len(q_terms))
        exact = 0.0
        for rid in (c.get("requirement_ids", []) + c.get("api_names", [])
                    + c.get("ecu_parameters", [])):
            if identifier_matches(q_tokens, rid):
                exact += 0.5
        score = c.get("fused_score", 0.0) * w_fused + overlap * w_overlap \
            + min(exact, 1.0) * w_exact
        scored.append({**c, "rerank_score": round(float(score), 4)})
    scored.sort(key=lambda d: d["rerank_score"], reverse=True)
    return scored[:top_n]
