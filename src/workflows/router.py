"""Typed workflow router (spec §19). Deterministic routing, bounded agent-like steps only."""
from __future__ import annotations
from ..retrieval.pipeline import RetrievalPipeline
from ..generation.answer import generate
from ..generation.verification import verify, confidence_score, abstain_message
from ..generation.citations import citation_block


def answer_query(pipe: RetrievalPipeline, query: str) -> dict:
    ret = pipe.retrieve(query)
    plan, evidence = ret["plan"], ret["evidence"]
    comparison = plan.get("release_mode") == "comparison"
    # one controlled retry: broaden to context chunks if atomic evidence is thin
    if len(evidence) < 3:
        ret2 = pipe.retrieve(query + " " + " ".join(plan.get("modules", [])), top_k_final=12)
        if len(ret2["evidence"]) > len(evidence):
            ret, evidence = ret2, ret2["evidence"]
    gen = generate(query, evidence, comparison)
    verification = verify(gen["draft"], evidence, plan)
    conf = confidence_score(ret["retrieval_score"], evidence, verification, plan)
    if conf["should_abstain"]:
        final = abstain_message(query, plan, evidence)
    else:
        final = gen["draft"] + "\n\n## Sources\n" + citation_block(evidence)
    trace = {"intent": plan.get("intent"), "release_mode": plan.get("release_mode"),
             "releases": plan.get("releases"), "candidates": len(evidence),
             "retrieval_score": ret["retrieval_score"], **conf,
             "claim_support_rate": verification["claim_support_rate"]}
    return {"answer": final, "draft": gen["draft"], "evidence": evidence, "plan": plan,
            "verification": verification, "confidence": conf, "trace": trace,
            "llm": gen.get("llm", "?")}
