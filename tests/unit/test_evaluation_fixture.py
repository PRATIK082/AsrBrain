"""End-to-end smoke test of the evaluation harness on the synthetic fixture corpus.

The fixture is the corpus the CI gate uses, so this test protects the gate itself: if the
harness stops working, the CI gate would pass silently.
"""
import json
import os
import tempfile

from src.evaluation.fixture import build
from src.evaluation.golden import load_golden, validate
from src.evaluation.runner import run_evaluation


def test_fixture_corpus_builds_and_the_harness_runs_end_to_end():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "fixture.db")
        index = os.path.join(tmp, "fixture")
        golden = os.path.join(tmp, "golden.jsonl")
        split = os.path.join(tmp, "split.json")
        out = os.path.join(tmp, "out")

        summary = build(db)
        assert summary["chunks"] > 50
        assert summary["tables"] > 0
        assert summary["figures"] > 0

        from src.evaluation.build import build as build_golden
        report = build_golden(db, golden, split, os.path.join(tmp, "review.csv"),
                              target=200, review_size=10)
        assert report["n"] >= 150
        assert report["meets_coverage_targets"] is True
        assert validate(load_golden(golden)) == []

        from src.indexing.build import main as build_index
        import sys
        argv = sys.argv
        sys.argv = ["build", "--canonical", db, "--out", index]
        try:
            build_index()
        finally:
            sys.argv = argv

        payload = run_evaluation(golden_path=golden, canonical=db, index_path=index,
                                 out_dir=out, split_path=split, split="all",
                                 mode="retrieval", use_llm=False, label="test")
        agg = payload["aggregate"]
        assert agg["n"] == report["n"]
        assert agg["context_recall"]["value"] is not None
        # the synthetic corpus is small and its identifiers are unique, so the retriever
        # should find most of the gold evidence
        assert agg["context_recall"]["value"] > 0.3
        assert os.path.exists(os.path.join(out, "report.md"))
        assert os.path.exists(os.path.join(out, "failures.csv"))
        assert os.path.exists(os.path.join(out, "runs", "index.json"))
        with open(os.path.join(out, "runs", "index.json"), encoding="utf-8") as fh:
            assert len(json.load(fh)) == 1


def test_report_states_the_target_comparison():
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "fixture.db")
        golden = os.path.join(tmp, "golden.jsonl")
        split = os.path.join(tmp, "split.json")
        out = os.path.join(tmp, "out")
        build(db)
        from src.evaluation.build import build as build_golden
        build_golden(db, golden, split, os.path.join(tmp, "review.csv"), target=200,
                     review_size=10)
        from src.indexing.build import main as build_index
        import sys
        argv = sys.argv
        sys.argv = ["build", "--canonical", db, "--out", os.path.join(tmp, "idx")]
        try:
            build_index()
        finally:
            sys.argv = argv
        run_evaluation(golden_path=golden, canonical=db, index_path=os.path.join(tmp, "idx"),
                       out_dir=out, split_path=split, mode="retrieval", use_llm=False)
        with open(os.path.join(out, "report.md"), encoding="utf-8") as fh:
            report = fh.read()
        assert "Master prompt §3 targets" in report
        assert "MET" in report or "MISSED" in report
        assert "20 worst failures" in report
