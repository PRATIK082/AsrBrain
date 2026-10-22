"""Claim extraction + citation verification + confidence/abstain (spec §17–18)."""
from __future__ import annotations
import re
from ..schema.queries import ClaimVerdict

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
CITE_RE = re.compile(r"\[E(\d+)\]")
CITE_AT_START = re.compile(r"^\[E\d+\]")


def split_claims(draft: str) -> list[str]:
    """Split a draft into verifiable claims.

    Two rules, both of which fix real answer-loss bugs:

    * A markdown header is a header, not a sentence. Splitting the raw text let
      ``"## Direct answer\\nCom is a module. [E1]"`` arrive as one segment, which the
      "skip anything starting with #" rule then threw away *together with the first real
      claim of the section*. Every section lost its first claim.
    * A short sentence that carries a citation is a claim. Two-word statements such as
      ``"Com is a module. [E1]"`` are exactly what an AUTOSAR answer is made of, and
      dropping them made the verifier report zero citation coverage for a correctly cited
      answer, which then abstained on its own evidence.
    """
    blocks: list[str] = []
    buf: list[str] = []
    for line in (draft or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            if buf:
                blocks.append(" ".join(buf))
                buf = []
            continue
        if s:
            buf.append(s)
    if buf:
        blocks.append(" ".join(buf))

    claims: list[str] = []
    for block in blocks:
        parts: list[str] = []
        for raw in SENT_SPLIT.split(block):
            part = raw.strip()
            if not part:
                continue
            # "…is a module. [E1]" splits into the sentence and the citation label. The label
            # belongs to the sentence it follows, so it is merged back; otherwise the claim
            # would carry no citation and the verifier would see an uncited claim.
            if parts and CITE_AT_START.match(part):
                parts[-1] = f"{parts[-1]} {part}"
            else:
                parts.append(part)
        for sent in parts:
            if (len(sent.split()) >= 4 or CITE_RE.search(sent)) and not sent.startswith("#"):
                claims.append(sent)
    return claims[:30]


def verify(draft: str, evidence: list[dict], plan: dict) -> dict:
    claims = split_claims(draft)
    by_e = {f"E{i+1}": c for i, c in enumerate(evidence)}
    verdicts: list[ClaimVerdict] = []
    for claim in claims:
        cites = CITE_RE.findall(claim)
        ev_ids = [by_e[f"E{n}"]["chunk_id"] for n in cites if f"E{n}" in by_e]
        supported = bool(ev_ids)
        # version/platform consistency: cited chunk must match requested filters
        vc = pc = True
        for n in cites:
            c = by_e.get(f"E{n}")
            if not c:
                continue
            if plan.get("releases") and plan.get("release_mode") == "exact":
                if c.get("autosar_release") not in plan["releases"]:
                    vc = False
            if plan.get("platforms") and c.get("platform") not in plan["platforms"]:
                pc = False
        score = 0.9 if supported and vc and pc else (0.4 if supported else 0.0)
        verdicts.append(ClaimVerdict(claim=claim[:300], supported=supported,
            support_score=score, evidence_ids=ev_ids, version_consistent=vc,
            platform_consistent=pc, citation_valid=bool(ev_ids),
            risk="low" if score >= 0.8 else ("medium" if score >= 0.4 else "high")))
    # coverage signals
    cited = {e for v in verdicts for e in v.evidence_ids}
    claim_support_rate = sum(v.supported for v in verdicts) / max(1, len(verdicts))
    # "did the answer cite its claims" — the signal that belongs in the confidence formula.
    # Dividing the cited-evidence count by the whole evidence pool punished a correct two
    # citation answer over twelve retrieved chunks with a score of 0.17.
    citation_coverage = (sum(1 for v in verdicts if v.evidence_ids) / len(verdicts)
                         if verdicts else 0.0)
    return {"verdicts": [v.model_dump() for v in verdicts],
            "claim_support_rate": round(claim_support_rate, 4),
            "citation_coverage": round(citation_coverage, 4),
            "evidence_cited": len(cited),
            "evidence_total": len(evidence)}


def confidence_score(retrieval_score: float, evidence: list, verification: dict, plan: dict) -> dict:
    n = len(evidence)
    evidence_coverage = min(1.0, n / 8.0)
    citation_coverage = verification["citation_coverage"]
    verifier = verification["claim_support_rate"]
    # `all([])` is True, so with no claims at all the version check used to look *perfect*.
    # An answer without a single verifiable claim is not version-consistent, it is unverified.
    # The bonus is earned only by claims that actually cite evidence: an uncited claim is
    # neither version-consistent nor inconsistent, it simply carries no weight.
    cited_verdicts = [v for v in verification["verdicts"] if v.get("evidence_ids")]
    version_ok = all(v["version_consistent"] for v in cited_verdicts) if cited_verdicts else False
    conf = (0.25 * retrieval_score + 0.20 * (1.0 if version_ok else 0.0)
            + 0.20 * evidence_coverage + 0.15 * citation_coverage + 0.20 * verifier)
    # The level must not depend on how many chunks happened to be retrieved: a fully cited
    # answer over three chunks is not "Low confidence" just because the retriever returned
    # fewer than four. Evidence sufficiency still contributes to the confidence value.
    level = "High" if (citation_coverage >= 0.5 and conf >= 0.7 and version_ok) \
        else ("Medium" if conf >= 0.45 else "Low")
    should_abstain = (n == 0) or (level == "Low" and verifier < 0.4)
    return {"confidence": round(float(conf), 4), "level": level,
            "should_abstain": should_abstain, "version_consistent": version_ok,
            "evidence_coverage": round(evidence_coverage, 4),
            "citation_coverage": round(citation_coverage, 4),
            "evidence_cited": verification.get("evidence_cited", 0),
            "evidence_total": verification.get("evidence_total", n)}


ABSTAIN_TEMPLATE = ("I could not verify this answer from the indexed AUTOSAR documents.\n\n"
                    "Missing evidence:\n{missing}\n\nAvailable evidence:\n{available}")


def abstain_message(query: str, plan: dict, evidence: list) -> str:
    missing = f"- query: {query}\n- releases: {plan.get('releases')}\n- modules: {plan.get('modules')}"
    avail = "\n".join(f"- {c.get('source_pdf')} p.{c.get('page_start')}" for c in evidence[:5]) or "- none"
    return ABSTAIN_TEMPLATE.format(missing=missing, available=avail)
