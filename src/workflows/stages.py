"""Staged orchestration with streaming events (Part G). The existing deterministic
router stays the engine; this layer wraps it in workflow stages emitting
status/evidence/token/complete events (Part D contract). No LangGraph/LlamaIndex
dependency — stages are explicit and cancellable.
"""
from __future__ import annotations
from typing import Iterator
from ..retrieval.pipeline import RetrievalPipeline
from ..retrieval.clarify import missing_slots, clarification_question
from ..generation.answer import generate as _generate, extractive_fallback
from ..generation.providers import ProviderSpec, stream as _stream_tokens
from ..generation.prompts import build_prompt
from ..generation.verification import verify, confidence_score, abstain_message
from ..generation.citations import citation_block
from ..retrieval.graph import extract_edges

STAGES = ["query_understanding", "retrieval_planning", "text_retrieval", "table_retrieval",
          "graph_retrieval", "fusion_rerank", "expansion_compression", "answer_drafting",
          "citation_validation", "confidence"]


def run_staged(pipe: RetrievalPipeline, query: str, spec: ProviderSpec | None = None,
               cancel: dict | None = None, known_slots: dict | None = None,
               top_k: int = 0) -> Iterator[dict]:
    """Yield event dicts: status | clarify | evidence | token | complete."""
    from ..retrieval.query_understanding import parse  # noqa: F401 (stage marker)
    from ..retrieval.normalize import correct_query
    from .suggest import suggest
    cancel = cancel or {}
    # spell-tolerant input: auto-correct before anything else, keep the record
    corrected, corrections = correct_query(query)
    if corrections:
        yield {"event": "status", "stage": "normalizing",
               "message": "Interpreted as: “" + corrected + "”",
               "corrections": corrections}
        query = corrected
    yield {"event": "status", "stage": "query_understanding",
           "message": "Identifying release, platform, module, and intent"}
    if cancel.get("stop"):
        return
    ret = pipe.retrieve(query, top_k_final=top_k or 0)
    plan = ret["plan"]
    if known_slots:
        for k in ("releases", "platforms", "modules"):
            if known_slots.get(k):
                plan[k] = known_slots[k]
        if known_slots.get("releases"):
            plan["release_mode"] = "exact" if len(known_slots["releases"]) == 1 else "comparison"
    # clarification gate (req. 1): ask back only when corpus actually spans versions
    try:
        corpus_releases = sorted({c.get("autosar_release", "") for c in pipe.chunks if c.get("autosar_release")})
        corpus_platforms = sorted({c.get("platform", "") for c in pipe.chunks if c.get("platform")})
    except Exception:
        corpus_releases, corpus_platforms = [], []
    missing = missing_slots(plan, corpus_releases, corpus_platforms)
    # NOTE: plan here is a dict (model_dump); clarify helpers accept dicts.
    if missing and not (known_slots and known_slots.get("skip_clarify")):
        yield {"event": "clarify", "missing": missing,
               "detected_modules": plan.get("modules", []),
               "question": clarification_question(plan, missing),
               "plan": plan}
        return
    yield {"event": "status", "stage": "retrieval_planning",
           "message": f"Intent: {plan.get('intent')} · releases: {plan.get('releases') or 'auto'} · modules: {plan.get('modules') or 'auto'}",
           "plan": plan}
    if cancel.get("stop"):
        return
    evidence = ret["evidence"]
    for branch in ("text_retrieval", "table_retrieval", "graph_retrieval", "fusion_rerank",
                   "expansion_compression"):
        yield {"event": "status", "stage": branch,
               "message": {"text_retrieval": f"Dense+BM25 candidates scored",
                           "table_retrieval": "Table/figure stores checked",
                           "graph_retrieval": "Module/API relationship edges traversed",
                           "fusion_rerank": f"RRF fused, reranked to {len(evidence)}",
                           "expansion_compression": "Parent contexts merged, passages compressed"}[branch]}
        if cancel.get("stop"):
            return
    for i, c in enumerate(evidence, 1):
        yield {"event": "evidence", "source_id": c["chunk_id"], "source_pdf": c.get("source_pdf", ""),
               "page": c.get("page_start"), "section": f"{c.get('section_number','')} {c.get('section_title','')}".strip(),
               "release": c.get("autosar_release", ""), "platform": c.get("platform", ""),
               "module": c.get("module", ""), "requirement_ids": c.get("requirement_ids", [])[:5],
               "snippet": (c.get("compressed") or c.get("normalized_text", ""))[:400],
               "relevance": c.get("rerank_score", 0.0), "label": f"E{i}"}
    yield {"event": "status", "stage": "answer_drafting", "message": "Drafting cited answer"}
    comparison = plan.get("release_mode") == "comparison"
    gen = _generate(query, evidence, comparison, spec)
    draft = gen["draft"]
    # stream draft tokens (real provider stream when available, else chunked replay)
    if spec is not None:
        streamed = "".join(_stream_tokens(build_prompt(query, evidence, comparison,
                                                        plan.get("intent", "")), spec))
        tokens_text = streamed or draft
    else:
        tokens_text = draft
    step = 120
    for j in range(0, len(tokens_text), step):
        if cancel.get("stop"):
            yield {"event": "status", "stage": "cancelled", "message": "Generation stopped by user"}
            return
        yield {"event": "token", "text": tokens_text[j:j + step]}
    yield {"event": "status", "stage": "citation_validation", "message": "Validating claims against evidence"}
    verification = verify(tokens_text, evidence, plan)
    conf = confidence_score(ret["retrieval_score"], evidence, verification, plan)
    if conf["should_abstain"]:
        final = abstain_message(query, plan, evidence)
    else:
        final = tokens_text + "\n\n## Sources\n" + citation_block(evidence)
    try:
        edges = [e.model_dump() for e in extract_edges(evidence)]
    except Exception:
        edges = []
    plan["normalized_query"] = query
    plan["corrections"] = [{"from": a, "to": b} for a, b in corrections]
    yield {"event": "complete", "answer": final, "confidence": conf["confidence"],
           "level": conf["level"], "citation_coverage": verification["citation_coverage"],
           "evidence_coverage": conf["evidence_coverage"],
           "claim_support_rate": verification["claim_support_rate"],
           "followups": suggest(plan, evidence),
           "trace": {"intent": plan.get("intent"), "release_mode": plan.get("release_mode"),
                     "releases": plan.get("releases"), "candidates": len(evidence),
                     "retrieval_score": ret["retrieval_score"], **conf},
           "graph": edges, "plan": plan, "llm": gen.get("llm", "?")}
