"""Retrieval + answer + operational metrics: citation precision, faithfulness,
correctness, abstention quality, hallucinated-identifier rate, latency.

Design rules for this module
----------------------------
1. Every metric is a pure function over plain data. No I/O, no globals, no LLM call.
2. Metrics that cannot be computed exactly are named as proxies and document the proxy in
   ``METHODS`` so the report never presents a proxy as a measurement.
3. Slices, not single numbers: a metric that only has a mean hides the failure modes that
   matter, so the runner reports per-category means as well.
4. No third-party dependency: confidence intervals use the Wilson score interval, which is
   closed-form and adequate for the small-n slices here.
"""
from __future__ import annotations

import math
import re
from collections import Counter

# --------------------------------------------------------------------------------------
# Text normalisation
# --------------------------------------------------------------------------------------

STOPWORDS = frozenset("""
a an the of to in on for with by from as at is are was were be been being and or but if
then than that this these those it its we our you your i me my do does did not no nor so
such can could should would may might must shall will shall there here what which who whom
whose when where why how all any both each few more most other some only own same too very
about into over under again further once because while during before after above below
""".split())

# Requirement / specification identifiers, e.g. SWS_CanIf_00012, PRS_SOMEIP_00042
REQ_ID_RE = re.compile(r"\b(?:SWS|SRS|PRS|TPS|RS|EXP|CONSTR|QM)_[A-Za-z0-9_]+\b")
# API / function names, e.g. CanIf_Transmit, Rte_Read, Com_SendSignal
API_NAME_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+\b")
# Numbers with a unit, e.g. 500 ms, 10 kHz, 4096 bytes
NUMBER_UNIT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s?(?:ms|us|ns|s|mm|Hz|kHz|MHz|GB|MB|KB|kB|bit|byte|bytes|%|V|mA|A|W)\b")
# CamelCase identifiers, e.g. CanIf, PduR, EcuM
CAMEL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][A-Za-z0-9]*)+\b")

#: Metric names that are computed with a proxy rather than exactly, and why.
METHODS = {
    "faithfulness": "proxy: claim-level support via identifier containment + lexical overlap; "
                    "no entailment model is used in Phase 1",
    "answer_relevance": "proxy: content-word overlap between question and answer",
    "answer_correctness": "ROUGE-1 F1 against the verbatim gold answer span",
    "citation_precision": "proxy: a citation supports a claim when the claim's identifiers appear "
                           "verbatim in the cited chunk, else when the chunk contains the claim's "
                           "distinctive content words",
    "abstention_accuracy": "exact: correct iff answerable->answered and unanswerable->abstained",
    "hallucinated_id_rate": "exact: identifiers in the answer that appear in no retrieved chunk",
    "cost_usd": "estimate: characters/4 tokens x configured price; local Ollama is free",
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def content_tokens(text: str) -> list[str]:
    """Lower-cased content words (stopwords removed)."""
    return [w for w in (t.lower() for t in _WORD_RE.findall(text or "")) if w not in STOPWORDS]


def extract_identifiers(text: str) -> list[str]:
    """Requirement ids, API names and CamelCase identifiers found in ``text``."""
    out: list[str] = []
    for pattern in (REQ_ID_RE, API_NAME_RE, CAMEL_RE):
        out.extend(pattern.findall(text or ""))
    # de-duplicate, keep order
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def extract_exact_tokens(text: str) -> list[str]:
    """Identifiers plus numbers-with-units — the tokens the exact-token guard protects."""
    out = extract_identifiers(text)
    out.extend(NUMBER_UNIT_RE.findall(text or ""))
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq


# --------------------------------------------------------------------------------------
# Retrieval metrics (existing, unchanged in behaviour)
# --------------------------------------------------------------------------------------

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
    dcg = sum(1.0 / math.log2(i + 2) for i, cid in enumerate(retrieved[:k]) if cid in set(gold))
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(set(gold)), k)))
    return dcg / (ideal or 1.0)


# --------------------------------------------------------------------------------------
# Answer metrics
# --------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return (text or "").lower()


def claim_supported(claim: str, cited_chunk_text: str) -> bool:
    """Does the cited chunk support this claim?

    Strict path: every identifier in the claim must appear verbatim in the chunk.
    Proxy path (claims without identifiers): at least half of the claim's distinctive content
    words must be present in the chunk.
    """
    ids = extract_identifiers(claim)
    hay = _norm(cited_chunk_text)
    if ids:
        return all(_norm(i) in hay for i in ids)
    words = set(content_tokens(claim))
    if not words:
        return False
    hits = sum(1 for w in words if w in hay)
    return hits >= max(1, math.ceil(len(words) / 2))


def citation_precision_recall(verdicts: list[dict]) -> tuple[float, float]:
    """Precision/recall of claim->citation support.

    ``verdicts`` is a list of ``{"claim": str, "cited_chunk_texts": list[str]}``. A citation is
    precise when the cited chunk supports the claim. Recall is the share of *cited* pairs that
    were valid, i.e. the same population — it is reported separately from the corpus-level
    citation recall computed in :func:`citation_recall`.
    """
    pairs = [(v.get("claim", ""), t) for v in verdicts for t in v.get("cited_chunk_texts", [])]
    if not pairs:
        return 0.0, 0.0
    prec = sum(1 for claim, text in pairs if claim_supported(claim, text)) / len(pairs)
    return round(prec, 4), round(prec, 4)


def citation_precision(verdicts: list[dict]) -> float:
    """Share of (claim, cited chunk) pairs where the chunk really supports the claim."""
    pairs = [(v.get("claim", ""), t) for v in verdicts for t in v.get("cited_chunk_texts", [])]
    if not pairs:
        return 0.0
    return round(sum(1 for claim, text in pairs if claim_supported(claim, text)) / len(pairs), 4)


def citation_recall(gold_evidence_ids: list[str], retrieved_ids: list[str],
                    cited_ids: list[str]) -> float:
    """Share of the gold evidence that was retrieved *and* actually cited in the answer."""
    if not gold_evidence_ids:
        return 0.0
    got = set(retrieved_ids) & set(cited_ids)
    return round(len(got & set(gold_evidence_ids)) / len(set(gold_evidence_ids)), 4)


def faithfulness(claims: list[str], cited_chunk_texts: list[str]) -> float:
    """Proxy for groundedness: share of claims supported by the retrieved evidence.

    A claim is supported when it carries identifiers and at least one cited chunk contains
    them all, or — for identifier-free claims — when the union of the cited chunks contains
    at least half of the claim's content words.
    """
    if not claims:
        return 0.0
    joined = "\n".join(cited_chunk_texts or [])
    supported = 0
    for claim in claims:
        ids = extract_identifiers(claim)
        hay = _norm(joined)
        if ids:
            if any(all(_norm(i) in _norm(t) for i in ids) for t in (cited_chunk_texts or [])):
                supported += 1
            continue
        words = set(content_tokens(claim))
        if words and sum(1 for w in words if w in hay) >= max(1, math.ceil(len(words) / 2)):
            supported += 1
    return round(supported / len(claims), 4)


def answer_relevance(question: str, answer: str) -> float:
    """Proxy: content-word overlap between the question and the answer."""
    q = set(content_tokens(question))
    if not q:
        return 0.0
    a = set(content_tokens(answer))
    return round(len(q & a) / len(q), 4)


def context_precision(retrieved_ids: list[str], gold_evidence_ids: list[str]) -> float:
    """Share of the retrieved context that is gold evidence."""
    if not retrieved_ids:
        return 0.0
    if not gold_evidence_ids:
        return 0.0
    return round(len(set(retrieved_ids) & set(gold_evidence_ids)) / len(retrieved_ids), 4)


def context_recall(retrieved_ids: list[str], gold_evidence_ids: list[str]) -> float:
    """Share of the gold evidence that made it into the retrieved context."""
    if not gold_evidence_ids:
        return 0.0
    return round(len(set(retrieved_ids) & set(gold_evidence_ids)) / len(set(gold_evidence_ids)), 4)


def rouge1_f1(prediction: str, reference: str) -> float:
    """ROUGE-1 F1 between the produced answer and the gold answer span."""
    p = Counter(content_tokens(prediction))
    r = Counter(content_tokens(reference))
    if not p or not r:
        return 0.0
    overlap = sum((p & r).values())
    if overlap == 0:
        return 0.0
    prec = overlap / sum(p.values())
    rec = overlap / sum(r.values())
    return round(2 * prec * rec / (prec + rec), 4)


def exact_id_match(gold_requirement_ids: list[str], answer: str) -> float:
    """Share of the gold requirement ids that appear verbatim in the answer."""
    if not gold_requirement_ids:
        return 0.0
    hay = _norm(answer)
    return round(sum(1 for g in gold_requirement_ids if _norm(g) in hay) / len(gold_requirement_ids), 4)


def hallucinated_id_rate(answer: str, evidence_texts: list[str]) -> tuple[float, list[str]]:
    """Share of the answer's identifiers that appear in no retrieved chunk.

    Returns ``(rate, offending_identifiers)``. This is the metric behind the
    "hallucinated IDs / identifiers <= 0.5%" target.
    """
    ids = extract_identifiers(answer)
    if not ids:
        return 0.0, []
    hay = _norm("\n".join(evidence_texts or []))
    bad = [i for i in ids if _norm(i) not in hay]
    return round(len(bad) / len(ids), 4), bad


def abstention_accuracy(answerable: bool, abstained: bool) -> float:
    """Correct abstention behaviour: answerable->answer, unanswerable->abstain."""
    return 1.0 if (answerable != abstained) else 0.0


# --------------------------------------------------------------------------------------
# Operational metrics
# --------------------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Rough token count (~4 characters per token)."""
    return max(0, len(text or "")) // 4


def cost_usd(prompt_text: str, completion_text: str, price_in: float, price_out: float) -> float:
    """Estimated cost in USD. Local Ollama is priced at 0."""
    return round(estimate_tokens(prompt_text) * price_in + estimate_tokens(completion_text) * price_out, 6)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile (``pct`` in 0..100)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(0, min(rank - 1, len(ordered) - 1))]


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95% by default)."""
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return round(max(0.0, centre - margin), 4), round(min(1.0, centre + margin), 4)


def mean_ci95(values: list[float]) -> tuple[float, float]:
    """95% confidence interval for the mean of a bounded sample.

    Used for metrics that are means of ratios (context recall, faithfulness, ...). The Wilson
    interval is for *proportions of independent trials* and must not be used for those: it
    answers a different question and yields an interval that can exclude its own mean.
    """
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return round(mean, 4), round(mean, 4)
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(var / n)
    return round(max(0.0, mean - 1.96 * se), 4), round(min(1.0, mean + 1.96 * se), 4)
