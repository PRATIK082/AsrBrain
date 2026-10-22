"""Evaluation runner: golden set -> pipeline -> per-item metrics -> aggregate report.

Two modes
---------
``retrieval``  no LLM. Measures whether the *right evidence* is retrieved. Runs over the whole
               golden set in seconds and is fully deterministic.
``full``       the legacy ``answer_query`` path (one LLM call). Measures the produced answer:
               faithfulness, answer correctness, citation precision, hallucinated identifiers,
               abstention behaviour and latency.

The split exists because a 14B local model answers at ~20-35 s per question: running the whole
golden set end-to-end would take hours, and the LLM's variance would drown the retrieval signal.
Retrieval metrics are therefore reported over 100% of the set and answer metrics over a
stratified subset, and every report states the n behind every number.

Failure diagnosis
-----------------
Every item gets one primary failure reason from an ordered rule list, so the "20 worst failures"
report says *why* an item failed rather than only that it did.
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict

from ..config.settings import settings
from ..generation.answer import generate as _generate
from ..generation.providers import ProviderSpec
from ..indexing.hybrid import HybridIndex, load_chunks
from ..retrieval.pipeline import RetrievalPipeline
from ..workflows.router import answer_query
from . import metrics as M
from .golden import coverage_report, load_golden
from .splits import apply_split, load_split, verify_split

#: Metrics that are means of ratios and therefore get a normal-approximation interval.
MEAN_METRICS = [
    "context_recall", "context_precision", "citation_precision", "citation_recall",
    "faithfulness", "answer_relevance", "answer_correctness", "exact_id_match",
    "requirement_recall",
]
#: Metrics that are proportions of independent trials and therefore get a Wilson interval.
BINARY_METRICS = ["abstention_accuracy", "hit_rate"]

#: Ordered failure rules. The first rule that matches names the failure.
FAILURE_RULES = [
    ("error", lambda r: r.get("error")),
    ("clarify_asked_instead_of_answering", lambda r: r.get("clarified")),
    ("no_evidence_for_unanswerable_question",
     lambda r: (not r.get("answerable")) and r.get("evidence_count", 0) == 0),
    ("no_evidence_retrieved", lambda r: r.get("evidence_count", 0) == 0),
    ("abstained_despite_gold_evidence",
     lambda r: r.get("abstained") and r.get("context_recall", 0) > 0),
    ("abstained_without_evidence", lambda r: r.get("abstained")),
    ("gold_evidence_not_retrieved",
     lambda r: r.get("answerable") and r.get("gold_evidence_ids") and r.get("context_recall", 0) == 0),
    ("hallucinated_identifier", lambda r: r.get("hallucinated_ids")),
    ("citation_not_supporting_claim",
     lambda r: bool(r.get("cited_ids")) and r.get("citation_precision", 1.0) < 0.5),
    ("answer_does_not_cover_gold",
     lambda r: r.get("answerable") and r.get("answer_correctness") is not None
     and r.get("answer_correctness", 1.0) < 0.15),
    ("unanswerable_question_was_answered",
     lambda r: (not r.get("answerable")) and r.get("abstained") is False),
    ("slow", lambda r: r.get("latency_s", 0) > 30),
]


def _diagnose(result: dict) -> str:
    for name, rule in FAILURE_RULES:
        try:
            if rule(result):
                return name
        except Exception:
            continue
    return "ok"


def _provider_spec(use_llm: bool) -> ProviderSpec | None:
    if not use_llm:
        return None
    from ..generation.answer import default_spec
    try:
        return default_spec()
    except Exception:
        return None


def _retrieval_only(pipe: RetrievalPipeline, item: dict) -> dict:
    """Measure retrieval for one item without calling the LLM.

    ``confidence`` is ``None`` because the answer engine never ran: abstention is *not
    measurable* in this mode, and reporting it as ``False`` would be a false measurement.
    """
    ret = pipe.retrieve(item["question"])
    evidence = ret["evidence"]
    return {
        "evidence": evidence,
        "plan": ret["plan"],
        "retrieval_score": ret["retrieval_score"],
        "answer": "",
        "draft": "",
        "abstained": None,
        "confidence": None,
        "verification": {},
    }


def _evaluate_item(item: dict, res: dict, latency_s: float) -> dict:
    """Turn one pipeline result into the metric row for that item."""
    evidence = res["evidence"]
    retrieved_ids = [c["chunk_id"] for c in evidence]
    gold_ids = list(item.get("gold_evidence_ids") or [])
    answer = res.get("answer", "")
    draft = res.get("draft", "") or answer
    evidence_texts = [c.get("text") or c.get("normalized_text") or "" for c in evidence]

    # citations: map [E1]..[En] in the produced answer back onto the retrieved chunks
    import re
    cite_pairs: list[dict] = []
    cited_ids: list[str] = []
    if draft:
        for label in sorted(set(re.findall(r"\[E(\d+)\]", draft)), key=int):
            idx = int(label) - 1
            if 0 <= idx < len(evidence):
                cited_ids.append(evidence[idx]["chunk_id"])
        for claim in (res.get("verification", {}) or {}).get("verdicts", []):
            claim_text = claim.get("claim", "")
            for ev_id in claim.get("evidence_ids", []):
                chunk = next((c for c in evidence if c["chunk_id"] == ev_id), None)
                if chunk is not None:
                    cite_pairs.append({
                        "claim": claim_text,
                        "cited_chunk_texts": [chunk.get("text") or chunk.get("normalized_text") or ""],
                    })

    claims = [v.get("claim", "") for v in (res.get("verification", {}) or {}).get("verdicts", [])]
    halluc_rate, halluc_ids = M.hallucinated_id_rate(answer or draft, evidence_texts)
    # abstention is only knowable when the answer engine actually ran
    confidence = res.get("confidence")
    abstained = bool((confidence or {}).get("should_abstain")) if confidence is not None else None

    gold_req_ids = list(item.get("gold_requirement_ids") or [])
    retrieved_req_ids = {r for c in evidence for r in (c.get("requirement_ids") or [])}
    requirement_recall = (round(len(set(gold_req_ids) & retrieved_req_ids) / len(set(gold_req_ids)), 4)
                          if gold_req_ids else None)

    row = {
        "query_id": item["query_id"],
        "category": item.get("category"),
        "difficulty": item.get("difficulty"),
        "answerable": bool(item.get("answerable")),
        "question": item["question"],
        "latency_s": round(latency_s, 3),
        "evidence_count": len(evidence),
        "retrieved_ids": retrieved_ids,
        "cited_ids": cited_ids,
        "gold_evidence_ids": gold_ids,
        "gold_requirement_ids": gold_req_ids,
        "abstained": abstained,
        "confidence": (confidence or {}).get("confidence"),
        "confidence_level": (confidence or {}).get("level"),
        "claim_support_rate": (res.get("verification", {}) or {}).get("claim_support_rate"),
        "context_recall": M.context_recall(retrieved_ids, gold_ids),
        "context_precision": M.context_precision(retrieved_ids, gold_ids),
        "requirement_recall": requirement_recall,
        "citation_precision": M.citation_precision(cite_pairs) if cite_pairs else None,
        "citation_recall": M.citation_recall(gold_ids, retrieved_ids, cited_ids) if cited_ids else None,
        "faithfulness": M.faithfulness(claims, evidence_texts) if claims else None,
        "answer_relevance": M.answer_relevance(item["question"], answer or draft) if answer else None,
        "answer_correctness": (M.rouge1_f1(answer or draft, item.get("gold_answer", ""))
                               if item.get("answerable") and item.get("gold_answer") and answer else None),
        "exact_id_match": (M.exact_id_match(gold_req_ids, answer or draft)
                           if gold_req_ids and answer else None),
        "hallucinated_id_rate": halluc_rate if answer else None,
        "hallucinated_ids": halluc_ids if answer else [],
        "abstention_accuracy": (M.abstention_accuracy(bool(item.get("answerable")), abstained)
                                 if abstained is not None else None),
        "recall_at_10": M.recall_at_k(retrieved_ids, gold_ids, 10),
        "mrr": M.mrr(retrieved_ids, gold_ids),
        "ndcg": M.ndcg(retrieved_ids, gold_ids, 10),
        "hit_rate": (1.0 if (set(retrieved_ids) & set(gold_ids)) else 0.0) if gold_ids else None,
        "intent": (res.get("plan") or {}).get("intent"),
    }
    row["failure"] = _diagnose(row)
    return row



def _aggregate(rows: list[dict]) -> dict:
    """Headline and per-category aggregates with the right interval per metric type."""
    def mean(key: str, subset: list[dict]) -> float | None:
        vals = [r[key] for r in subset if r.get(key) is not None]
        return round(sum(vals) / len(vals), 4) if vals else None

    def mean_block(key: str, subset: list[dict]) -> dict:
        vals = [r[key] for r in subset if r.get(key) is not None]
        if not vals:
            return {"value": None, "n": 0, "ci95": None}
        lo, hi = M.mean_ci95(vals)
        return {"value": round(sum(vals) / len(vals), 4), "n": len(vals), "ci95": [lo, hi]}

    def binary_block(key: str, subset: list[dict]) -> dict:
        vals = [r[key] for r in subset if r.get(key) is not None]
        if not vals:
            return {"value": None, "n": 0, "ci95": None}
        successes = sum(1 for v in vals if v >= 0.999)
        lo, hi = M.wilson_interval(successes, len(vals))
        return {"value": round(sum(vals) / len(vals), 4), "n": len(vals), "ci95": [lo, hi]}

    def block(subset: list[dict]) -> dict:
        return {
            "n": len(subset),
            "answerable": sum(1 for r in subset if r["answerable"]),
            "unanswerable": sum(1 for r in subset if not r["answerable"]),
            "abstention_rate": (round(sum(1 for r in subset if r["abstained"] is True) / max(1, len(subset)), 4)
                                if any(r["abstained"] is not None for r in subset) else None),
            "abstention_accuracy": binary_block("abstention_accuracy", subset),
            "context_recall": mean_block("context_recall", subset),
            "context_precision": mean_block("context_precision", subset),
            "requirement_recall": mean_block("requirement_recall", subset),
            "citation_precision": mean_block("citation_precision", subset),
            "citation_recall": mean_block("citation_recall", subset),
            "faithfulness": mean_block("faithfulness", subset),
            "answer_relevance": mean("answer_relevance", subset),
            "answer_correctness": mean("answer_correctness", subset),
            "exact_id_match": mean("exact_id_match", subset),
            "hallucinated_id_rate_mean": mean("hallucinated_id_rate", subset),
            "hallucinated_ids_total": sum(len(r.get("hallucinated_ids") or []) for r in subset),
            "recall_at_10": mean("recall_at_10", subset),
            "mrr": mean("mrr", subset),
            "ndcg": mean("ndcg", subset),
            "hit_rate": binary_block("hit_rate", subset),
            "latency_p50_s": M.percentile([r["latency_s"] for r in subset], 50),
            "latency_p95_s": M.percentile([r["latency_s"] for r in subset], 95),
            "failures": dict(sorted(defaultdict(int, {
                r["failure"]: sum(1 for x in subset if x["failure"] == r["failure"])
                for r in subset}).items())),
        }

    out = block(rows)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r["category"] or "unknown"].append(r)
    out["by_category"] = {cat: block(v) for cat, v in sorted(by_cat.items())}
    by_diff: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_diff[r["difficulty"] or "unknown"].append(r)
    out["by_difficulty"] = {d: block(v) for d, v in sorted(by_diff.items())}
    return out


def _worst(rows: list[dict], limit: int = 20) -> list[dict]:
    """The worst-scoring items, ordered by how badly they failed."""
    def severity(r: dict) -> tuple:
        penalty = {
            "error": 100, "clarify_asked_instead_of_answering": 95,
            "no_evidence_retrieved": 90, "abstained_despite_gold_evidence": 85,
            "abstained_without_evidence": 80, "gold_evidence_not_retrieved": 70,
            "hallucinated_identifier": 60, "citation_not_supporting_claim": 50,
            "answer_does_not_cover_gold": 40, "unanswerable_question_was_answered": 35,
            "slow": 10, "ok": 0,
        }.get(r["failure"], 0)
        return (penalty, -(r.get("context_recall") or 0), r.get("latency_s") or 0)

    return sorted(rows, key=severity, reverse=True)[:limit]


def run_evaluation(golden_path: str, canonical: str, index_path: str, out_dir: str,
                   split_path: str | None = None, split: str = "all", mode: str = "retrieval",
                   limit: int = 0, use_llm: bool = True, llm_sample: int = 40,
                   price_in: float = 0.0, price_out: float = 0.0,
                   label: str = "") -> dict:
    """Run the harness and write the report. Returns the full payload."""
    items = load_golden(golden_path)
    drift: list[str] = []
    if split_path and os.path.exists(split_path):
        manifest = load_split(split_path)
        drift = verify_split(items, manifest, golden_path)
        if split in ("train", "holdout", "dev"):
            train, holdout = apply_split(items, manifest)
            items = train if split == "train" else holdout
    if limit:
        items = items[:limit]

    chunks = load_chunks(canonical)
    try:
        idx = HybridIndex.load(index_path)
    except Exception:
        idx = HybridIndex()
        idx.build(chunks)
        idx.save(index_path)
    pipe = RetrievalPipeline(idx, chunks)

    spec = _provider_spec(use_llm and mode == "full")
    rows: list[dict] = []
    llm_ids: set[str] = set()
    if mode == "full" and spec is not None and llm_sample:
        # stratified LLM sample: keep the mix, shrink the size
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            by_cat[item.get("category", "unknown")].append(item)
        for cat in sorted(by_cat):
            take_n = max(1, round(llm_sample * len(by_cat[cat]) / len(items)))
            for item in by_cat[cat][:take_n]:
                llm_ids.add(item["query_id"])

    for item in items:
        t0 = time.time()
        error = ""
        try:
            if mode == "full" and item["query_id"] in llm_ids and spec is not None:
                res = answer_query(pipe, item["question"])
            else:
                res = _retrieval_only(pipe, item)
        except Exception as exc:  # keep going: one bad item must not kill the run
            error = f"{type(exc).__name__}: {exc}"[:300]
            res = {"evidence": [], "plan": {}, "answer": "", "draft": "",
                   "abstained": None, "confidence": None, "verification": {}}
        row = _evaluate_item(item, res, time.time() - t0)
        if error:
            row["error"] = error
            row["failure"] = "error"
        rows.append(row)

    aggregate = _aggregate(rows)
    payload = {
        "label": label or f"{mode}-{time.strftime('%Y%m%d-%H%M%S')}",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": mode,
        "split": split,
        "llm_model": spec.model if spec else None,
        "golden_path": golden_path,
        "golden_sha256": None,
        "split_drift": drift,
        "coverage": coverage_report(items),
        "metrics_methods": M.METHODS,
        "aggregate": aggregate,
        "worst": _worst(rows, 20),
        "results": rows,
    }
    if os.path.exists(golden_path):
        from .golden import file_sha256
        payload["golden_sha256"] = file_sha256(golden_path)
    _write_outputs(payload, out_dir)
    return payload


def _write_outputs(payload: dict, out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    stamp = payload["generated_at"].replace(":", "").replace("-", "")
    with open(os.path.join(out_dir, f"run-{stamp}.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(out_dir, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as fh:
        fh.write(render_report(payload))
    import csv
    with open(os.path.join(out_dir, "failures.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        cols = ["query_id", "category", "difficulty", "answerable", "failure", "latency_s",
                "evidence_count", "context_recall", "context_precision", "citation_precision",
                "citation_recall", "faithfulness", "answer_correctness", "exact_id_match",
                "hallucinated_id_rate", "hallucinated_ids", "abstained", "intent", "question"]
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in payload["results"]:
            out = dict(row)
            out["hallucinated_ids"] = " | ".join(row.get("hallucinated_ids") or [])
            writer.writerow(out)
    # run history for the Evaluation screen
    runs_dir = os.path.join(out_dir, "runs")
    os.makedirs(runs_dir, exist_ok=True)
    index_path = os.path.join(runs_dir, "index.json")
    history = []
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as fh:
                history = json.load(fh)
        except Exception:
            history = []
    agg = payload["aggregate"]
    history.append({
        "label": payload["label"],
        "generated_at": payload["generated_at"],
        "mode": payload["mode"],
        "split": payload["split"],
        "llm_model": payload["llm_model"],
        "n": agg["n"],
        "context_recall": agg["context_recall"]["value"],
        "citation_precision": agg["citation_precision"]["value"],
        "faithfulness": agg["faithfulness"]["value"],
        "answer_correctness": agg["answer_correctness"],
        "abstention_accuracy": agg["abstention_accuracy"]["value"],
        "hallucinated_id_rate_mean": agg["hallucinated_id_rate_mean"],
        "latency_p50_s": agg["latency_p50_s"],
        "latency_p95_s": agg["latency_p95_s"],
    })
    history = history[-50:]
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump(history, fh, indent=2)


def render_report(payload: dict) -> str:
    """Human-readable Markdown report."""
    agg = payload["aggregate"]
    lines = [
        f"# Evaluation report — {payload['label']}",
        "",
        f"- generated: `{payload['generated_at']}`",
        f"- mode: `{payload['mode']}` · split: `{payload['split']}` · n = {agg['n']}",
        f"- llm: `{payload['llm_model'] or 'none (retrieval only)'}`",
        f"- golden set sha256: `{payload['golden_sha256']}`",
    ]
    if payload.get("split_drift"):
        lines += ["", "> **Split drift detected**", ""]
        lines += [f"> - {d}" for d in payload["split_drift"]]
    lines += [
        "",
        "## Headline",
        "",
        "| Metric | Value | n | 95% CI |",
        "|---|---|---|---|",
    ]
    for key in MEAN_METRICS + BINARY_METRICS:
        block = agg.get(key) or {}
        if not isinstance(block, dict) or block.get("value") is None:
            continue
        ci = block.get("ci95")
        lines.append(f"| {key} | {block['value']} | {block.get('n')} | "
                     f"{f'[{ci[0]}, {ci[1]}]' if ci else '—'} |")
    lines += [
        "",
        "| Operational | Value |",
        "|---|---|",
        f"| latency p50 | {agg['latency_p50_s']} s |",
        f"| latency p95 | {agg['latency_p95_s']} s |",
        f"| abstention rate | {agg['abstention_rate']} |",
        f"| hallucinated identifiers (total) | {agg['hallucinated_ids_total']} |",
        f"| mean hallucinated-id rate | {agg['hallucinated_id_rate_mean']} |",
        "",
        "## Per category",
        "",
        "| Category | n | context_recall | citation_precision | faithfulness | abstention_acc | failures |",
        "|---|---|---|---|---|---|---|",
    ]
    for cat, block in agg["by_category"].items():
        fails = ", ".join(f"{k}={v}" for k, v in block["failures"].items() if k != "ok") or "—"
        lines.append(
            f"| {cat} | {block['n']} | {block['context_recall']['value']} | "
            f"{block['citation_precision']['value']} | {block['faithfulness']['value']} | "
            f"{block['abstention_accuracy']['value']} | {fails} |")
    lines += ["", "## 20 worst failures", "",
              "| query_id | category | failure | ctx_recall | faith | halluc | latency | question |",
              "|---|---|---|---|---|---|---|---|"]
    for row in payload["worst"]:
        lines.append(
            f"| {row['query_id']} | {row['category']} | {row['failure']} | "
            f"{row['context_recall']} | {row['faithfulness']} | "
            f"{row['hallucinated_id_rate']} | {row['latency_s']}s | "
            f"{row['question'][:70]} |")
    lines += ["", "## Metric methods", ""]
    for name, how in payload["metrics_methods"].items():
        lines.append(f"- **{name}** — {how}")
    lines += ["", "## Master prompt §3 targets", "",
              "| Target | Required | Measured | Status |", "|---|---|---|---|"]
    targets = [
        ("citation precision", 0.98, agg["citation_precision"]["value"]),
        ("faithfulness", 0.97, agg["faithfulness"]["value"]),
        ("answer correctness", 0.95, agg["answer_correctness"]),
        ("abstention accuracy", 0.95, agg["abstention_accuracy"]["value"]),
        ("hallucinated id rate (max)", 0.005, agg["hallucinated_id_rate_mean"]),
        ("latency p95 (s, max)", 8.0, agg["latency_p95_s"]),
    ]
    for name, required, measured in targets:
        if measured is None:
            status = "not measured"
        elif "max" in name:
            status = "MET" if measured <= required else "MISSED"
        else:
            status = "MET" if measured >= required else "MISSED"
        lines.append(f"| {name} | {required} | {measured} | {status} |")
    lines += ["", "---", "",
              "*Generated by `src.evaluation.runner`. Every number states the n behind it; "
              "proxy metrics are named in the methods section above.*", ""]
    return "\n".join(lines)
