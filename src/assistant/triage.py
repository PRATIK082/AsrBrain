"""Evidence-grounded issue triage.

The triage engine is deterministic: it retrieves the passages that actually
mention the reported symptom, extracts the normative statements from them, and
proposes checks. Nothing is invented — every cause, check hint and fix
candidate carries the source it came from, and an unreferenced corpus yields
an explicit abstention.

An optional LLM may rephrase the deterministic triage into a narrative; its
claims are verified against the same evidence and unsupported claims are dropped
before they reach the user.
"""
from __future__ import annotations

import re

from ..config.settings import settings
from ..generation.answer import generate
from ..generation.citations import citation_block
from ..generation.verification import confidence_score, split_claims, verify

# --------------------------------------------------------------------------- #
# symptom taxonomy
# --------------------------------------------------------------------------- #

CATEGORIES: list[dict] = [
    {
        "id": "signal_not_transmitted",
        "title": "Signal / frame is not transmitted",
        "keywords": ["transmit", "transmitted", "transmission", "frame", "send", "sent",
                     "not sent", "no frame", "lost"],
        "checks": [
            {"question": "Is the sending runnable actually reached?",
             "how": "Confirm the runnable is triggered by its configured trigger and not "
                    "blocked by a mode guard."},
            {"question": "Is the port connected in the composition?",
             "how": "Check the client/server port connection and the mapping to the "
                    "underlying communication channel."},
            {"question": "Is the signal mapped to a PDU that is actually scheduled?",
             "how": "Verify the PDU routing and the transmission mode of the PDU group."},
        ],
    },
    {
        "id": "timeout",
        "title": "Timeout / periodic timing violation",
        "keywords": ["timeout", "time out", "timed out", "deadline", "not received",
                     "late", "jitter", "period", "cyclic"],
        "checks": [
            {"question": "Which timeout parameter is in effect for this signal?",
             "how": "Read the ECUC value and its documented unit and range; compare it "
                    "with the actual cycle time."},
            {"question": "Is the timeout derived from a cycle that is itself configured?",
             "how": "Trace the timeout configuration back to the underlying cycle; a "
                    "mismatched cycle invalidates the derived timeout."},
            {"question": "What is the documented reaction on timeout?",
             "how": "Check the error/recovery reaction defined for the affected API."},
        ],
    },
    {
        "id": "port_connection",
        "title": "Port not connected / mapping invalid",
        "keywords": ["port", "not connected", "unconnected", "mapping", "connector",
                     "composable", "interface"],
        "checks": [
            {"question": "Is the required connector present in the composition?",
             "how": "Compare the composition with the port requirements of the component."},
            {"question": "Does the port name match the data element contract?",
             "how": "Check the data type and range agreement between both port ends."},
        ],
    },
    {
        "id": "state_machine",
        "title": "State machine / mode transition",
        "keywords": ["state", "transition", "mode", "nm", "com manager", "bus start",
                     "full communication", "no communication"],
        "checks": [
            {"question": "Is the requested transition allowed from the current state?",
             "how": "Look up the transition table in the specification and confirm the "
                    "source state."},
            {"question": "Is the mode request accepted by the mode manager?",
             "how": "Check the mode request/acceptance protocol and its timing."},
        ],
    },
    {
        "id": "initialisation",
        "title": "Initialisation / startup / shutdown",
        "keywords": ["init", "initialisation", "initialization", "startup", "start up",
                     "shutdown", "deinit", "not initialised", "never runs"],
        "checks": [
            {"question": "Is the init API called in the documented order?",
             "how": "Check the required initialisation sequence and its preconditions."},
            {"question": "Are all preconditions of the init API met?",
             "how": "Verify each precondition listed for the API in the specification."},
        ],
    },
    {
        "id": "configuration",
        "title": "Configuration value out of range or missing",
        "keywords": ["config", "ecuc", "parameter", "value", "threshold", "range",
                     "invalid", "not set", "default"],
        "checks": [
            {"question": "What is the documented value range for this parameter?",
             "how": "Read the parameter definition and its permitted range."},
            {"question": "Is the configured value in the permitted range?",
             "how": "Compare the active configuration with the range from the spec."},
        ],
    },
    {
        "id": "api_mismatch",
        "title": "API signature / prototype mismatch",
        "keywords": ["api", "signature", "prototype", "mismatch", "does not match",
                     "wrong argument", "parameter type", "undefined", "declaration"],
        "checks": [
            {"question": "Does the implemented signature match the specified one?",
             "how": "Compare the header implementation with the API definition in the spec."},
            {"question": "Is the API part of the release being compiled against?",
             "how": "Check the release and platform scope of the API definition."},
        ],
    },
    {
        "id": "diagnostic",
        "title": "Diagnostic / error reporting",
        "keywords": ["error", "dem", "dtc", "diagnostic", "fault", "reported", "not stored"],
        "checks": [
            {"question": "Is the event mapped to a diagnostic event in the configuration?",
             "how": "Check the Dem configuration for the event id."},
            {"question": "Is the error confirmed by the component before reporting?",
             "how": "Check the documented confirmation/debounce behaviour."},
        ],
    },
    {
        "id": "general",
        "title": "General behaviour question",
        "keywords": [],
        "checks": [
            {"question": "Which requirement states the expected behaviour?",
             "how": "Search the indexed documents for the normative statement and read it "
                    "in context."},
            {"question": "Which API documents the observed behaviour?",
             "how": "Locate the API definition and check its preconditions and postconditions."},
        ],
    },
]

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "not", "are", "was", "has",
    "have", "but", "you", "our", "its", "his", "her", "they", "them", "their", "when",
    "what", "which", "why", "how", "does", "did", "can", "could", "would", "should",
    "there", "here", "into", "than", "then", "them", "some", "any", "all", "one",
    "after", "before", "because", "while", "about", "over", "been", "being", "very",
    "just", "also", "only", "even", "much", "such", "these", "those", "issue",
    "problem", "error", "issue", "problem", "please", "help", "need", "want", "get",
    "make", "made", "like", "does", "works", "work", "fails", "fail", "failing",
}


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _tokens(text: str) -> list[str]:
    """Meaningful lowercase terms + identifier-shaped tokens."""
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or "")
    out: list[str] = []
    for w in words:
        if w.lower() in _STOPWORDS:
            continue
        out.append(w.lower())
        if re.search(r"[A-Z]", w[1:] or " ") or "_" in w:
            out.append(w)  # keep the original casing for API/requirement matching
    return out


def _code_identifiers(code: str) -> list[str]:
    """API-like identifiers lifted from a pasted snippet."""
    ids: set[str] = set()
    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b", code or ""):
        name = m.group(1)
        if len(name) > 4 and not name.startswith(("if_", "for_", "while_")):
            ids.add(name)
    for m in re.finditer(r"\b([A-Z][A-Za-z0-9]{2,})\s*\(", code or ""):
        ids.add(m.group(1))
    return sorted(ids)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.;:])\s+|\n{2,}", text or "")
    return [p.strip() for p in parts if len(p.strip()) > 40]


_NORMATIVE = re.compile(
    r"\b(shall|must|has to|is required to|are required to|is not allowed|shall not|"
    r"is mandatory|is permitted|is forbidden|shall be|is expected)\b", re.IGNORECASE)


def _overlap_score(sentence: str, terms: set[str]) -> int:
    low = sentence.lower()
    return sum(1 for t in terms if t in low)


def classify(symptom: str) -> dict:
    """Pick the closest symptom category (deterministic keyword match)."""
    low = (symptom or "").lower()
    best = CATEGORIES[-1]
    best_hits: list[str] = []
    best_score = 0
    for cat in CATEGORIES:
        hits = [k for k in cat["keywords"] if k in low]
        score = len(hits)
        if score > best_score:
            best, best_hits, best_score = cat, hits, score
    if best_score == 0:
        return {"id": best["id"], "title": best["title"], "matched": [],
                "confidence": 0.2, "checks": best["checks"]}
    return {
        "id": best["id"],
        "title": best["title"],
        "matched": best_hits,
        "confidence": min(0.9, 0.4 + 0.1 * best_score),
        "checks": best["checks"],
    }


# --------------------------------------------------------------------------- #
# triage
# --------------------------------------------------------------------------- #


def diagnose(symptom: str, code: str = "", module: str = "", release: str = "",
             spec=None, top_k: int = 8, pipe=None) -> dict:
    """Diagnose a reported symptom against the indexed corpus.

    Returns a structured triage: category, likely causes (each cited), checks to
    run, fix candidates (each cited), a narrative summary, confidence and the
    evidence that was used.
    """
    symptom = (symptom or "").strip()
    if not symptom:
        return {"ok": False, "error": "symptom is required", "abstained": True,
                "category": classify(""), "likely_causes": [], "checks": [],
                "fix_candidates": [], "evidence": [], "confidence": 0.0, "level": "Low"}

    category = classify(symptom)

    if pipe is None:
        from ..indexing.hybrid import HybridIndex, load_chunks
        from ..retrieval.pipeline import RetrievalPipeline
        chunks = load_chunks(settings.canonical_db)
        if not chunks:
            return {"ok": False, "error": "canonical store is empty — run ingestion first",
                    "abstained": True, "category": category, "likely_causes": [],
                    "checks": category["checks"], "fix_candidates": [], "evidence": [],
                    "confidence": 0.0, "level": "Low"}
        try:
            idx = HybridIndex.load("data/indexes/hybrid")
            if len(idx.chunk_ids) != len(chunks):
                raise ValueError("stale index")
        except Exception:
            idx = HybridIndex()
            idx.build(chunks)
            idx.save("data/indexes/hybrid")
        pipe = RetrievalPipeline(idx, chunks)

    query = symptom
    if module:
        query += f" {module}"
    if release:
        query += f" {release}"
    code_ids = _code_identifiers(code)
    for ident in code_ids[:5]:
        query += f" {ident}"

    result = pipe.retrieve(query, top_k_final=top_k)
    evidence = result["evidence"]
    plan = result["plan"]

    if not evidence:
        return {
            "ok": True, "abstained": True, "category": category,
            "likely_causes": [], "checks": category["checks"], "fix_candidates": [],
            "evidence": [], "confidence": 0.0, "level": "Low",
            "summary": "No indexed passage mentions this symptom. The corpus does not "
                       "cover it — nothing is asserted here.",
            "followups": ["Which release and platform are you working on?",
                          "Which module or API is involved?"],
        }

    terms = set(_tokens(symptom)) | {i.lower() for i in code_ids}
    for ident in code_ids:
        terms.add(ident)

    # ---- likely causes: normative statements that mention the symptom -------
    causes: list[dict] = []
    fixes: list[dict] = []
    for i, chunk in enumerate(evidence):
        label = f"E{i + 1}"
        text = chunk.get("normalized_text") or chunk.get("text") or ""
        best_sentences = sorted(
            (_score_sentence(s, terms) for s in _sentences(text)),
            key=lambda s: -s["score"])
        for sent in best_sentences[:2]:
            if sent["score"] <= 0:
                continue
            item = {
                "cause": sent["text"][:400],
                "label": label,
                "source_id": chunk.get("chunk_id", ""),
                "source_pdf": chunk.get("source_pdf", ""),
                "page": chunk.get("page_start"),
                "section": f"{chunk.get('section_number','')} {chunk.get('section_title','')}".strip(),
                "release": chunk.get("autosar_release", ""),
                "module": chunk.get("module", ""),
                "normative": bool(_NORMATIVE.search(sent["text"])),
                "relevance": round(sent["score"] / 10.0, 3),
            }
            if item["normative"] and len(fixes) < 6:
                fixes.append({**item, "suggestion": _as_suggestion(sent["text"], chunk)})
            elif len(causes) < 6:
                causes.append(item)

    if not causes and fixes:
        causes = fixes[:4]
        fixes = fixes[:6]

    # ---- checks: category checks + parameter mentions found in the corpus ---
    checks = [dict(c) for c in category["checks"]]
    params = _config_mentions(evidence)
    for p in params[:3]:
        checks.append({
            "question": f"What does the parameter {p['name']} control?",
            "how": f"See {p['source_pdf']} p.{p['page']} ({p['section']}).",
            "source_id": p["source_id"],
        })

    # ---- summary -----------------------------------------------------------
    summary = _deterministic_summary(symptom, category, causes, checks, fixes, evidence)
    llm_used = ""
    if spec is not None:
        draft = generate(query, evidence, comparison=False, spec=spec)
        if draft.get("draft") and draft.get("llm") != "fallback":
            verification = verify(draft["draft"], evidence, plan)
            if verification["claim_support_rate"] >= 0.5:
                summary = draft["draft"] + "\n\n## Sources\n" + citation_block(evidence)
                llm_used = draft.get("llm", "")

    conf = confidence_score(result["retrieval_score"], evidence,
                            {"citation_coverage": 1.0 if causes else 0.0,
                             "claim_support_rate": 1.0 if causes else 0.0,
                             "verdicts": []},
                            plan)
    followups = _followups(category, causes)

    return {
        "ok": True,
        "abstained": False,
        "symptom": symptom,
        "category": category,
        "likely_causes": causes,
        "checks": checks,
        "fix_candidates": fixes,
        "summary": summary,
        "confidence": conf["confidence"],
        "level": conf["level"],
        "llm": llm_used,
        "plan": {k: plan.get(k) for k in ("intent", "releases", "modules", "release_mode")},
        "followups": followups,
        "evidence": [
            {
                "label": f"E{i + 1}",
                "source_id": c.get("chunk_id", ""),
                "source_pdf": c.get("source_pdf", ""),
                "page": c.get("page_start"),
                "page_end": c.get("page_end"),
                "section": f"{c.get('section_number','')} {c.get('section_title','')}".strip(),
                "release": c.get("autosar_release", ""),
                "platform": c.get("platform", ""),
                "module": c.get("module", ""),
                "requirement_ids": list(c.get("requirement_ids", []) or [])[:5],
                "snippet": (c.get("compressed") or c.get("normalized_text", ""))[:400],
                "relevance": c.get("rerank_score", 0.0),
            }
            for i, c in enumerate(evidence)
        ],
    }


def _score_sentence(sentence: str, terms: set[str]) -> dict:
    score = _overlap_score(sentence, terms)
    if _NORMATIVE.search(sentence):
        score += 3
    if re.search(r"\bSWS_[A-Za-z]+_\d+\b", sentence):
        score += 2
    return {"text": sentence, "score": score}


def _as_suggestion(sentence: str, chunk: dict) -> str:
    req = (chunk.get("requirement_ids") or [""])[0]
    prefix = f"{req}: " if req else ""
    return f"{prefix}{sentence[:300]}"


def _config_mentions(evidence: list[dict]) -> list[dict]:
    """ECUC-ish parameter names that appear in the retrieved passages."""
    out: list[dict] = []
    seen: set[str] = set()
    pattern = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:Timeout|Period|Time|Threshold|Size|"
                          r"Count|Interval|Delay|Limit|Enable|Value|Config|Timeout)[A-Za-z0-9]*)\b")
    for i, chunk in enumerate(evidence):
        text = chunk.get("normalized_text") or chunk.get("text") or ""
        for name in pattern.findall(text):
            if name in seen or len(name) < 6:
                continue
            seen.add(name)
            out.append({
                "name": name,
                "source_id": chunk.get("chunk_id", ""),
                "source_pdf": chunk.get("source_pdf", ""),
                "page": chunk.get("page_start"),
                "section": f"{chunk.get('section_number','')} {chunk.get('section_title','')}".strip(),
            })
            if len(out) >= 8:
                return out
    return out


def _deterministic_summary(symptom: str, category: dict, causes: list[dict],
                            checks: list[dict], fixes: list[dict],
                            evidence: list[dict]) -> str:
    lines = [f"## Triage: {category['title']}", ""]
    lines.append(f"Reported symptom: {symptom}")
    lines.append("")
    if causes:
        lines.append("### Most likely causes (from the indexed specification)")
        for c in causes[:4]:
            lines.append(f"- {c['cause']} — [{c['label']}] {c['source_pdf']} p.{c['page']} "
                         f"({c['section'] or 'section n/a'})")
        lines.append("")
    else:
        lines.append("### Most likely causes")
        lines.append("- No passage states this behaviour explicitly. Review the evidence below "
                     "and confirm the context before acting.")
        lines.append("")
    if checks:
        lines.append("### Checks to run")
        for chk in checks[:6]:
            lines.append(f"- **{chk['question']}** — {chk['how']}")
        lines.append("")
    if fixes:
        lines.append("### Candidate fixes (advisory — review before applying)")
        for f in fixes[:4]:
            lines.append(f"- {f.get('suggestion') or f.get('cause','')} — [{f['label']}] "
                         f"{f['source_pdf']} p.{f['page']} ({f['section'] or 'section n/a'})")
        lines.append("")
    lines.append("### Evidence")
    for i, c in enumerate(evidence[:5], start=1):
        lines.append(f"[E{i}] {c.get('source_pdf')} p.{c.get('page_start')}"
                     f" ({c.get('autosar_release') or 'unknown'}) — "
                     f"{(c.get('compressed') or c.get('normalized_text',''))[:220]}")
    return "\n".join(lines)


def _followups(category: dict, causes: list[dict]) -> list[str]:
    out = ["Which release and platform are you running?",
           "Can you paste the exact API call or error you observe?"]
    if causes:
        out.append(f"Can you show the code around {causes[0].get('source_id','')}?")
    return out


def triage_categories() -> list[dict]:
    """Public taxonomy (id, title, checks) for UI filters."""
    return [{"id": c["id"], "title": c["title"], "keywords": c["keywords"],
             "checks": c["checks"]} for c in CATEGORIES]
