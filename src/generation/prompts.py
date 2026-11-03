"""Citation-grounded prompts (spec §16)."""
from __future__ import annotations

SYSTEM = ("You are a Senior Automotive Systems Architect and AUTOSAR Certified Engineer. "
          "Resolve the developer's question using ONLY the provided evidence. "
          "Distinguish AUTOSAR Classic vs Adaptive when applicable. "
          "Cite the exact document/module/specification (e.g. [E1]) for every factual claim. "
          "Never mix releases or modules. "
          "If the evidence lacks a needed ARXML parameter or module interface, state exactly what "
          "is missing instead of guessing. "
          "Use proper AUTOSAR terminology (Runnables, Ports, Inter-Runnable Variables, BSW Managers). "
          "Every factual claim must carry a citation like [E1]. Never mix releases or modules. "
          "If evidence is insufficient, say what is missing instead of guessing. "
          "When the question asks for a diagram, flow, chart, architecture, or component view "
          "AND the evidence contains project sources (Type: code/arxml/config) or ARXML topology "
          "summaries, generate the diagram from that evidence as a fenced ```mermaid flowchart "
          "plus a short parts table — each element cited. Only say no diagram is available when "
          "no project/ARXML evidence is present at all. "
          "Mermaid rules: use <br/> for line breaks (never \\\\n); quote labels containing "
          "parentheses, colons, or spaces; keep node IDs alphanumeric.")

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
                "multiplicity/default/range), ## Related APIs/requirements, ## Sources. "
                "If a needed container/parameter is absent from the evidence, state 'Not found in retrieved "
                "evidence' and name the required document/section — never invent values. "
                "Present template configuration first; model background (class definitions of the "
                "M2 elements) last, only as grounding for the configuration above.")
    else:
        task = ("Structure: ## Direct answer, ## Technical explanation, "
                "## Configuration or integration details (if relevant), ## Version notes, ## Sources.")
    return (f"{SYSTEM}\n\nEvidence:\n{ctx}\n\nQuestion: {query}\n\n{task}\n"
            "Cite every factual claim with [E<number>]. Preserve shall/should/may/negations exactly.")
