"""Claim extraction + citation verification + confidence/abstain (spec §17–18)."""
from __future__ import annotations
import re
from ..schema.queries import ClaimVerdict

SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
CITE_RE = re.compile(r"\[E(\d+)\]")


def split_claims(draft: str) -> list[str]:
    sents = [s.strip() for s in SENT_SPLIT.split(draft) if s.strip()]
    # keep factual-looking sentences; skip pure headers
    return [s for s in sents if len(s.split()) >= 4 and not s.startswith("#")][:30]


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
    citation_coverage = len(cited) / max(1, len(evidence))
    return {"verdicts": [v.model_dump() for v in verdicts],
            "claim_support_rate": round(claim_support_rate, 4),
            "citation_coverage": round(citation_coverage, 4)}


def confidence_score(retrieval_score: float, evidence: list, verification: dict, plan: dict) -> dict:
    n = len(evidence)
    evidence_coverage = min(1.0, n / 8.0)
    citation_coverage = verification["citation_coverage"]
    verifier = verification["claim_support_rate"]
    version_ok = all(v["version_consistent"] for v in verification["verdicts"]) if verification["verdicts"] else True
    conf = (0.25 * retrieval_score + 0.20 * (1.0 if version_ok else 0.0)
            + 0.20 * evidence_coverage + 0.15 * citation_coverage + 0.20 * verifier)
    level = "High" if (evidence_coverage >= 0.9 and citation_coverage >= 0.5 and conf >= 0.7 and version_ok) \
        else ("Medium" if (evidence_coverage >= 0.5 and conf >= 0.45) else "Low")
    should_abstain = (n == 0) or (level == "Low" and verifier < 0.4)
    return {"confidence": round(float(conf), 4), "level": level,
            "should_abstain": should_abstain, "version_consistent": version_ok,
            "evidence_coverage": round(evidence_coverage, 4)}


ABSTAIN_TEMPLATE = ("I could not verify this answer from the indexed AUTOSAR documents.\n\n"
                    "Missing evidence:\n{missing}\n\nAvailable evidence:\n{available}")


def abstain_message(query: str, plan: dict, evidence: list) -> str:
    missing = f"- query: {query}\n- releases: {plan.get('releases')}\n- modules: {plan.get('modules')}"
    avail = "\n".join(f"- {c.get('source_pdf')} p.{c.get('page_start')}" for c in evidence[:5]) or "- none"
    return ABSTAIN_TEMPLATE.format(missing=missing, available=avail)
