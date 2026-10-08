"""Deterministic query understanding (spec §8). No LLM needed for routing."""
from __future__ import annotations
import re
from ..schema.queries import QueryPlan
from ..ingestion.metadata import MODULE_ALIASES, MODULE_GROUPS, PLATFORM_WORDS, module_for_api, word_hit

API_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*_[A-Za-z0-9_]+)\b")
REQ_RE = re.compile(r"\b((?:SWS|RS|PRS)_[A-Za-z0-9_\-]+|\[PRS_[A-Za-z0-9_\-]+\])")
REL_CLASSIC = re.compile(r"\b4\.[2-4](?:\.\d)?\b")
REL_ADAPTIVE = re.compile(r"\bR\d{2}-11\b")
COMPARE_WORDS = {"compare", "comparison", "difference", "differences", "changed", "vs", "versus", "between"}
TROUBLE_WORDS = {"why", "error", "errors", "fail", "fails", "failure", "e_not_ok", "det",
                 "not reaching", "mismatch", "troubleshoot", "troubleshooting"}
CONFIG_WORDS = {"configure", "configures", "configured", "configuring", "configuration",
                "configurations", "config", "ecuc", "parameter", "parameters",
                "container", "containers", "mandatory", "default"}
API_WORDS = {"api", "apis", "function", "functions", "return value", "precondition",
             "preconditions", "init", "transmit"}


def parse(query: str) -> QueryPlan:
    q = query.strip()
    ql = q.lower()
    plan = QueryPlan(original_query=q, normalized_query=re.sub(r"\s+", " ", q).strip())
    # releases
    rels = REL_CLASSIC.findall(q) + REL_ADAPTIVE.findall(q)
    if len(rels) >= 2 or any(word_hit(ql, w) for w in COMPARE_WORDS) and rels:
        plan.release_mode = "comparison"
        plan.needs_comparison_table = True
    elif len(rels) == 1:
        plan.release_mode = "exact"
    plan.releases = sorted(set(rels))
    # platforms
    for w, canon in PLATFORM_WORDS.items():
        if w in ql:
            plan.platforms.append(canon)
    # modules via aliases — whole-word match only, so "com" never fires on
    # "communication"/"component"/"complete"/"compare" (the Com-flavor bug).
    for alias, canon in MODULE_ALIASES.items():
        if word_hit(ql, alias) and canon not in plan.modules:
            plan.modules.append(canon)
    # umbrella words span several modules (diagnostic → Dcm + Dem)
    for group_word, canons in MODULE_GROUPS.items():
        if word_hit(ql, group_word):
            for canon in canons:
                if canon not in plan.modules:
                    plan.modules.append(canon)
    plan.api_names = sorted(set(API_RE.findall(q)))
    # API prefix implies its owning module (Rte_Read→RTE, Dem_GetStatus→Dem)
    for api in plan.api_names:
        canon = module_for_api(api)
        if canon and canon not in plan.modules:
            plan.modules.append(canon)
    plan.requirement_ids = sorted(set(r.strip("[]") for r in REQ_RE.findall(q) if isinstance(r, str)))
    # document types
    for dt in ("SWS", "PRS", "RS", "TPS", "TR"):
        if dt.lower() in ql or dt in q:
            plan.document_types.append(dt)
    # intent (whole-word matching: "det" must not fire on "details",
    # "init" must not hijack "initialization sequence")
    if plan.release_mode == "comparison":
        plan.intent = "comparison"
    elif any(word_hit(ql, w) for w in TROUBLE_WORDS):
        plan.intent = "troubleshooting"
    elif any(word_hit(ql, w) for w in CONFIG_WORDS):
        plan.intent = "configuration"
    elif plan.requirement_ids:
        plan.intent = "requirement_lookup"
    elif plan.api_names or any(word_hit(ql, w) for w in API_WORDS):
        plan.intent = "api_lookup"
    elif word_hit(ql, "initialization sequence"):
        plan.intent = "deep_explanation"
        plan.needs_graph_search = True
    elif any(word_hit(ql, w) for w in ("interact", "interacts", "interaction", "interactions",
                                        "relationship", "relationships", "depend", "depends",
                                        "depending", "dependency", "dependencies",
                                        "which module", "path from", "sequence")):
        plan.intent = "dependency"
        plan.needs_graph_search = True
    elif any(word_hit(ql, w) for w in ("explain", "describe", "complete", "initialization sequence", "receive path")):
        plan.intent = "deep_explanation"
    elif ql.startswith(("what is", "what are", "define", "meaning of", "purpose of")):
        plan.intent = "definition"
    else:
        plan.intent = "unknown"
    plan.entities = list(plan.modules) + list(plan.api_names) + list(plan.requirement_ids)
    if plan.intent in ("dependency", "deep_explanation"):
        plan.needs_graph_search = True
    plan.confidence = 0.9 if (plan.modules or plan.api_names or plan.requirement_ids) else 0.5
    return plan
