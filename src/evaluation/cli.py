"""Evaluation harness CLI.

    python -m src.evaluation.cli build    # build the golden set + freeze the split
    python -m src.evaluation.cli run      # run the harness
    python -m src.evaluation.cli gate     # compare a run against the thresholds
    python -m src.evaluation.cli review   # export the expert-review CSV
    python -m src.evaluation.cli coverage # show the golden-set coverage mix
"""
from __future__ import annotations

import argparse
import json

from .build import build, write_review_csv
from .gate import compare, load_gate
from .golden import coverage_report, expert_review_sample, load_golden
from .runner import run_evaluation

DEFAULT_GOLDEN = "data/benchmarks/autosar_golden_v2.jsonl"
DEFAULT_SPLIT = "data/benchmarks/holdout_v2.json"
DEFAULT_REVIEW = "data/benchmarks/expert_review_v2.csv"
DEFAULT_OUT = "reports/evaluation"


def cmd_build(args) -> int:
    report = build(args.canonical, args.golden, args.split, args.review,
                   target=args.target, review_size=args.review_size, seed=args.seed)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def cmd_run(args) -> int:
    payload = run_evaluation(
        golden_path=args.golden, canonical=args.canonical, index_path=args.index,
        out_dir=args.out, split_path=args.split, split=args.split_name, mode=args.mode,
        limit=args.limit, use_llm=not args.no_llm, llm_sample=args.llm_sample,
        label=args.label, allow_drift=args.allow_drift)
    agg = payload["aggregate"]
    print(json.dumps({
        "label": payload["label"], "mode": payload["mode"], "n": agg["n"],
        "context_recall": agg["context_recall"]["value"],
        "citation_precision": agg["citation_precision"]["value"],
        "faithfulness": agg["faithfulness"]["value"],
        "abstention_accuracy": agg["abstention_accuracy"]["value"],
        "answer_correctness": agg["answer_correctness"],
        "hallucinated_id_rate_mean": agg["hallucinated_id_rate_mean"],
        "latency_p50_s": agg["latency_p50_s"], "latency_p95_s": agg["latency_p95_s"],
        "failures": agg["failures"],
    }, indent=2))
    print(f"report: {args.out}/report.md")
    return 0


def cmd_gate(args) -> int:
    with open(args.run, encoding="utf-8") as fh:
        payload = json.load(fh)
    verdict = compare(payload, load_gate(args.gate))
    with open(args.report, "w", encoding="utf-8") as fh:
        json.dump(verdict, fh, indent=2)
    for check in verdict["checks"]:
        if check["status"] == "fail":
            print(f"FAIL {check['metric']}: measured {check['measured']} "
                  f"vs threshold {check['threshold']} (tolerance {check['tolerance']})")
        elif check["status"] == "pass":
            print(f"pass {check['metric']}: {check['measured']}")
        else:
            print(f"skip {check['metric']}: {check['reason']}")
    print("GATE PASSED" if verdict["passed"] else "GATE FAILED")
    return 0 if verdict["passed"] else 1


def cmd_review(args) -> int:
    items = load_golden(args.golden)
    sample = expert_review_sample(items, size=args.size, seed=args.seed)
    n = write_review_csv(args.out, sample)
    print(f"wrote {n} review rows to {args.out}")
    return 0


def cmd_coverage(args) -> int:
    items = load_golden(args.golden)
    print(json.dumps(coverage_report(items), indent=2, ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="src.evaluation.cli", description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build the golden set and freeze the hold-out split")
    b.add_argument("--canonical", default="data/canonical/canonical.db")
    b.add_argument("--golden", default=DEFAULT_GOLDEN)
    b.add_argument("--split", default=DEFAULT_SPLIT)
    b.add_argument("--review", default=DEFAULT_REVIEW)
    b.add_argument("--target", type=int, default=320)
    b.add_argument("--review-size", type=int, default=40)
    b.add_argument("--seed", type=int, default=20261021)
    b.set_defaults(func=cmd_build)

    r = sub.add_parser("run", help="run the evaluation harness")
    r.add_argument("--golden", default=DEFAULT_GOLDEN)
    r.add_argument("--split", default=DEFAULT_SPLIT)
    r.add_argument("--split-name", default="all", choices=["all", "train", "holdout", "dev"])
    r.add_argument("--canonical", default="data/canonical/canonical.db")
    r.add_argument("--index", default="data/indexes/hybrid")
    r.add_argument("--out", default=DEFAULT_OUT)
    r.add_argument("--mode", default="retrieval", choices=["retrieval", "full"])
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--llm-sample", type=int, default=40)
    r.add_argument("--no-llm", action="store_true")
    r.add_argument("--label", default="")
    r.add_argument("--allow-drift", action="store_true",
                   help="score despite split drift (records drift_acknowledged; re-freeze deliberately)")
    r.set_defaults(func=cmd_run)

    g = sub.add_parser("gate", help="compare a run against the thresholds")
    g.add_argument("--run", default=f"{DEFAULT_OUT}/latest.json")
    g.add_argument("--gate", default="data/benchmarks/eval_gate.json")
    g.add_argument("--report", default=f"{DEFAULT_OUT}/gate.json")
    g.set_defaults(func=cmd_gate)

    v = sub.add_parser("review", help="export the expert-review CSV")
    v.add_argument("--golden", default=DEFAULT_GOLDEN)
    v.add_argument("--out", default=DEFAULT_REVIEW)
    v.add_argument("--size", type=int, default=40)
    v.add_argument("--seed", type=int, default=20261021)
    v.set_defaults(func=cmd_review)

    c = sub.add_parser("coverage", help="show the golden-set coverage mix")
    c.add_argument("--golden", default=DEFAULT_GOLDEN)
    c.set_defaults(func=cmd_coverage)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
