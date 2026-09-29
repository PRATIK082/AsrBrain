"""Citation-grounded prompts (spec §16)."""
from __future__ import annotations

SYSTEM = ("You are an AUTOSAR specification assistant. Answer ONLY from the provided evidence. "
          "Every factual claim must carry a citation like [E1]. Never mix releases or modules. "
          "If evidence is insufficient, say what is missing instead of guessing.")

EVIDENCE_HEADER = ("[Evidence {eid}] Document: {doc} | Release: {rel} | Platform: {plat} | "
                   "Module: {mod} | Type: {dt} | Section: {sec} | Pages: {p0}-{p1} | "
                   "Requirements: {reqs}")


def format_evidence(evidence: list[dict]) -> str:
    blocks = []
    for i, c in enumerate(evidence, start=1):
        blocks.append(EVIDENCE_HEADER.format(
            eid=f"E{i}", doc=c.get("source_pdf", c.get("document_id", "?")),
            rel=c.get("autosar_release") or "unknown", plat=c.get("platform") or "unknown",
            mod=c.get("module") or "unknown", dt=c.get("document_type") or "unknown",
            sec=f"{c.get('section_number','')} {c.get('section_title','')}".strip() or "—",
            p0=c.get("page_start"), p1=c.get("page_end"),
            reqs=", ".join(c.get("requirement_ids", [])[:5]) or "—")
            + "\n" + c.get("compressed", c.get("normalized_text", "")))
    return "\n\n".join(blocks)


def build_prompt(query: str, evidence: list[dict], comparison: bool = False,
                 intent: str = "") -> str:
    ctx = format_evidence(evidence)
    if comparison:
        task = ("Compare per release in a table with columns | Topic | <release A> | <release B> | Evidence |. "
                "Sections: ## Comparison (table), ## Interpretation, ## Sources. "
                "Each difference must cite both sides where applicable; report missing evidence explicitly.")
    elif intent == "troubleshooting":
        task = ("Sections: ## Likely cause, ## Diagnostic sequence (numbered, each step cited), "
                "## Evidence, ## Sources.")
    elif intent == "configuration":
        task = ("Sections: ## Direct answer, ## Configuration procedure (numbered, cite container/parameter/"
                "multiplicity/default/range), ## Related APIs/requirements, ## Sources.")
    else:
        task = ("Structure: ## Direct answer, ## Technical explanation, "
                "## Configuration or integration details (if relevant), ## Version notes, ## Sources.")
    return (f"{SYSTEM}\n\nEvidence:\n{ctx}\n\nQuestion: {query}\n\n{task}\n"
            "Cite every factual claim with [E<number>]. Preserve shall/should/may/negations exactly.")
