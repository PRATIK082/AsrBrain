"""Follow-up question suggestions (3–4 clickable chips). Deterministic and grounded:
built from the detected plan + retrieved evidence (APIs, requirements, modules),
never from free LLM text — so chips always lead somewhere indexed."""
from __future__ import annotations


def suggest(plan: dict, evidence: list[dict], max_n: int = 4) -> list[str]:
    mods = [m for m in plan.get("modules", [])]
    rels = plan.get("releases", [])
    intent = plan.get("intent", "")
    apis: list[str] = []
    reqs: list[str] = []
    for c in evidence:
        for a in c.get("api_names", []):
            if a not in apis and not a.startswith(("SWS_", "RS_", "PRS_")):
                apis.append(a)
        for r in c.get("requirement_ids", []):
            if r not in reqs:
                reqs.append(r)
    out: list[str] = []
    rel_txt = f" in {rels[0]}" if len(rels) == 1 else ""
    if apis:
        out.append(f"What are the preconditions for {apis[0]}?")
        if reqs:
            out.append(f"Which requirement defines {apis[0]}?")
        else:
            out.append(f"What is the return and error behavior of {apis[0]}?")
    if len(mods) >= 2:
        out.append(f"How does {mods[0]} interact with {mods[1]}?")
    elif mods:
        out.append(f"How is {mods[0]} configured{rel_txt}?".replace("  ", " "))
    if reqs and not any("requirement" in s.lower() for s in out):
        out.append(f"What does {reqs[0]} specify?")
    if intent != "troubleshooting" and mods:
        out.append(f"How do I troubleshoot {mods[0]} errors?")
    if intent != "comparison" and len(rels) == 1 and mods:
        out.append(f"What changed for {mods[0]} across releases?")
    # generic grounded fallbacks
    for fb in ("Explain the initialization sequence step by step.",
               "Summarize the key requirements on this page range."):
        if len(out) >= max_n:
            break
        out.append(fb)
    seen, deduped = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped[:max_n]
