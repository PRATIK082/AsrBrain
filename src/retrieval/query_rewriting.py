"""Controlled query rewriting (spec §9): alias/registry expansions only, no free hallucination."""
from __future__ import annotations
from ..schema.queries import QueryPlan

MODULE_EXPANSIONS = {
    "CanIf": ["CAN Interface", "CanIf_Init", "CanIf_Transmit"],
    "PduR": ["PDU Router", "PduR routing"],
    "CanDrv": ["CAN Driver"],
    "CanSM": ["CAN State Manager"],
    "SOME-IP": ["SOMEIP", "SOME/IP", "service oriented communication"],
}


def rewrite(plan: QueryPlan) -> dict:
    lexical = [plan.original_query]
    semantic = [plan.normalized_query or plan.original_query]
    entity_q, req_q, comp_q = [], [], []
    for m in plan.modules:
        lexical.append(m)
        for exp in MODULE_EXPANSIONS.get(m, []):
            lexical.append(exp)
    for a in plan.api_names:
        entity_q.append(a)
        lexical.append(a)
    for r in plan.requirement_ids:
        req_q.append(r)
        lexical.append(r)
    if plan.release_mode == "comparison" and len(plan.releases) >= 2:
        comp_q = [f"{plan.original_query} {r}" for r in plan.releases]
    elif plan.release_mode == "comparison":
        comp_q = [plan.original_query]
    # dedup preserve order
    def dedup(xs):
        seen, out = set(), []
        for x in xs:
            if x not in seen:
                seen.add(x); out.append(x)
        return out
    return {"original_query": plan.original_query, "lexical_queries": dedup(lexical),
            "semantic_queries": dedup(semantic), "entity_queries": dedup(entity_q),
            "requirement_queries": dedup(req_q), "comparison_queries": dedup(comp_q)}
