"""Unit tests for the golden set, the frozen split and the CI gate."""
import json
import os
import tempfile

from src.evaluation.golden import (COVERAGE_TARGETS, coverage_report, expert_review_sample,
                                   load_golden, new_item, validate, write_golden)
from src.evaluation.gate import DEFAULT_GATE, compare, load_gate
from src.evaluation.splits import apply_split, load_split, save_split, split_ids, verify_split


def _item(qid: str, **kw) -> dict:
    kwargs = {"gold_answer": "a verbatim span", "gold_evidence_ids": ["chunk-1"]}
    kwargs.update(kw)
    return new_item(qid, f"question {qid}", kwargs.pop("category", "definition"), **kwargs)


def test_new_item_has_every_required_field():
    item = _item("q-1")
    for field in ("query_id", "question", "category", "difficulty", "answerable",
                  "gold_evidence_ids", "gold_answer", "needs_expert_review"):
        assert field in item


def test_new_item_rejects_unknown_fields():
    try:
        _item("q-1", nonsense=1)
    except TypeError:
        return
    raise AssertionError("unknown fields must be rejected")


def test_validate_catches_missing_evidence_on_an_answerable_item():
    problems = validate([{"query_id": "q-1", "question": "x", "category": "definition",
                          "difficulty": "easy", "answerable": True, "gold_evidence_ids": [],
                          "gold_answer": "", "needs_expert_review": True}])
    assert any("gold_evidence_ids" in p for p in problems)
    assert any("gold_answer" in p for p in problems)


def test_validate_catches_gold_evidence_on_an_unanswerable_item():
    item = _item("q-2", answerable=False, gold_answer="", gold_evidence_ids=[])
    item["gold_evidence_ids"] = ["chunk-1"]
    problems = validate([item])
    assert any("must not carry" in p for p in problems)


def test_validate_catches_duplicate_ids_and_unknown_categories():
    problems = validate([_item("q-1"), _item("q-1"), _item("q-2", category="nonsense")])
    assert any("duplicate" in p for p in problems)
    assert any("unknown category" in p for p in problems)


def test_coverage_report_counts_tags_as_well_as_categories():
    items = [
        _item("q-1", category="unanswerable", answerable=False, gold_answer="",
              gold_evidence_ids=[], tags=["unanswerable"]),
        _item("q-2", category="adversarial", answerable=False, gold_answer="",
              gold_evidence_ids=[], tags=["adversarial", "unanswerable"]),
    ]
    report = coverage_report(items)
    # category count 1 + tag count 1 for "unanswerable"
    assert report["by_category"]["unanswerable"] == 1
    assert report["unanswerable"] == 2
    assert report["coverage_gaps"] == [] or all(
        g["slice"] != "unanswerable" for g in report["coverage_gaps"])


def test_expert_review_sample_is_deterministic_and_stratified():
    items = [_item(f"q-{i:03d}", category=c) for i, c in
             enumerate(["definition"] * 10 + ["api_lookup"] * 10)]
    a = expert_review_sample(items, size=8, seed=7)
    b = expert_review_sample(items, size=8, seed=7)
    assert [x["query_id"] for x in a] == [x["query_id"] for x in b]
    assert len(a) == 8
    assert len({x["category"] for x in a}) == 2


def test_split_is_deterministic_and_disjoint():
    items = [_item(f"q-{i:04d}") for i in range(200)]
    a = split_ids(items)
    b = split_ids(items)
    assert a == b
    assert not set(a["train"]) & set(a["holdout"])
    assert len(a["train"]) + len(a["holdout"]) == 200
    # roughly the requested ratio
    assert 0.1 < len(a["holdout"]) / 200 < 0.35


def test_split_survives_a_reorder_of_the_items():
    items = [_item(f"q-{i:04d}") for i in range(200)]
    forward = split_ids(items)
    backward = split_ids(list(reversed(items)))
    assert set(forward["holdout"]) == set(backward["holdout"])


def test_freeze_and_drift_detection():
    with tempfile.TemporaryDirectory() as tmp:
        golden = os.path.join(tmp, "golden.jsonl")
        split = os.path.join(tmp, "split.json")
        items = [_item(f"q-{i:04d}") for i in range(50)]
        write_golden(golden, items)
        manifest = save_split(split, items, golden)
        assert load_split(split)["counts"]["holdout"] > 0
        assert verify_split(load_golden(golden), manifest, golden) == []

        # a change to the golden set must be reported as drift
        items.append(_item("q-9999"))
        write_golden(golden, items)
        drift = verify_split(load_golden(golden), manifest, golden)
        assert drift and "changed since the split was frozen" in drift[0]


def test_apply_split_uses_the_manifest():
    items = [_item(f"q-{i:04d}") for i in range(50)]
    manifest = {"holdout": ["q-0000", "q-0001"], "train": []}
    train, holdout = apply_split(items, manifest)
    assert len(holdout) == 2
    assert len(train) == 48


def test_gate_passes_when_metrics_hold_and_fails_when_they_regress():
    payload = {"aggregate": {"context_recall": {"value": 0.5},
                              "hallucinated_id_rate_mean": 0.1,
                              "latency_p95_s": 5.0}}
    verdict = compare(payload, {"context_recall": {"min": 0.4, "tolerance": 0.02},
                                "hallucinated_id_rate_mean": {"max": 0.2, "tolerance": 0.01},
                                "latency_p95_s": {"max": 8.0, "tolerance": 1.0}})
    assert verdict["passed"] is True

    payload["aggregate"]["context_recall"]["value"] = 0.3
    verdict = compare(payload, {"context_recall": {"min": 0.4, "tolerance": 0.02}})
    assert verdict["passed"] is False
    assert verdict["checks"][0]["status"] == "fail"


def test_gate_skips_metrics_that_were_not_measured():
    payload = {"aggregate": {"context_recall": {"value": None}}}
    verdict = compare(payload, {"context_recall": {"min": 0.4}, "answer_correctness": {"min": 0.9}})
    assert verdict["passed"] is True
    assert any(c["status"] == "skipped" for c in verdict["checks"])


def test_default_gate_covers_the_headline_metrics():
    for metric in ("context_recall", "citation_precision", "faithfulness",
                   "abstention_accuracy", "hallucinated_id_rate_mean"):
        assert metric in DEFAULT_GATE


def test_committed_gate_file_is_valid():
    gate = load_gate("data/benchmarks/eval_gate.json")
    assert "context_recall" in gate
    for rule in gate.values():
        assert "min" in rule or "max" in rule
        assert "tolerance" in rule
