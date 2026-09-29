"""Evaluation runner: benchmark -> pipeline -> metrics JSON (no LLM-as-judge for gold)."""
from __future__ import annotations
import argparse
import json
import time
from ..indexing.hybrid import HybridIndex, load_chunks
from ..retrieval.pipeline import RetrievalPipeline
from ..workflows.router import answer_query
from .metrics import recall_at_k, mrr, ndcg


def run_benchmark(benchmark: str, canonical: str, index_path: str, out: str) -> dict:
    chunks = load_chunks(canonical)
    try:
        idx = HybridIndex.load(index_path)
    except Exception:
        idx = HybridIndex()
        idx.build(chunks)
        idx.save(index_path)
    pipe = RetrievalPipeline(idx, chunks)
    items = [json.loads(l) for l in open(benchmark) if l.strip()]
    results = []
    for it in items:
        t0 = time.time()
        res = answer_query(pipe, it["question"])
        dt = round(time.time() - t0, 3)
        ev_ids = [c["chunk_id"] for c in res["evidence"]]
        gold_docs = set(it.get("gold_source_documents", []))
        hit = any(g in (c.get("source_pdf", "")) for g in gold_docs for c in res["evidence"]) if gold_docs else None
        # Part M: requirement/API recall + version/module precision (additive)
        gold_reqs = set(it.get("gold_requirement_ids", []))
        ev_reqs = {r for c in res["evidence"] for r in c.get("requirement_ids", [])}
        req_recall = len(gold_reqs & ev_reqs) / len(gold_reqs) if gold_reqs else None
        want_rels = set(it.get("required_versions", []))
        want_mods = set(it.get("required_modules", []))
        ev_rels = {c.get("autosar_release", "") for c in res["evidence"]}
        ev_mods = {c.get("module", "") for c in res["evidence"]}
        version_ok = (not want_rels) or bool(ev_rels & want_rels) or res["confidence"]["should_abstain"]
        module_ok = (not want_mods) or bool(ev_mods & want_mods) or res["confidence"]["should_abstain"]
        results.append({"query_id": it["query_id"], "intent": res["plan"]["intent"],
                        "hit": hit, "evidence": len(ev_ids),
                        "req_recall": req_recall, "version_ok": version_ok, "module_ok": module_ok,
                        "claim_support_rate": res["verification"]["claim_support_rate"],
                        "confidence": res["confidence"], "latency_s": dt,
                        "abstained": res["confidence"]["should_abstain"]})
    def _mean(key):
        vals = [r[key] for r in results if r[key] is not None]
        return round(sum(vals) / len(vals), 4) if vals else None
    summary = {"n": len(results),
               "hit_rate": round(sum(1 for r in results if r["hit"]) / max(1, sum(1 for r in results if r["hit"] is not None)), 4),
               "abstention_rate": round(sum(1 for r in results if r["abstained"]) / max(1, len(results)), 4),
               "mean_claim_support": round(sum(r["claim_support_rate"] for r in results) / max(1, len(results)), 4),
               "mean_req_recall": _mean("req_recall"),
               "version_precision": _mean("version_ok"),
               "module_precision": _mean("module_ok"),
               "p50_latency_s": sorted(r["latency_s"] for r in results)[len(results) // 2] if results else 0}
    payload = {"summary": summary, "results": results,
               "note": "95%-style claims forbidden: report named metrics + slices only."}
    with open(out, "w") as f:
        json.dump(payload, f, indent=2)
    return payload


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", default="data/benchmarks/autosar_benchmark_v1.jsonl")
    ap.add_argument("--canonical", default="data/canonical/canonical.db")
    ap.add_argument("--index", default="data/indexes/hybrid")
    ap.add_argument("--out", default="reports/evaluation/validated.json")
    args = ap.parse_args()
    print(json.dumps(run_benchmark(args.benchmark, args.canonical, args.index, args.out)["summary"], indent=2))


if __name__ == "__main__":
    main()
