"""Build the golden set, freeze the hold-out split and export the expert-review sample.

    python -m src.evaluation.build --canonical data/canonical/canonical.db

Outputs
-------
``data/benchmarks/autosar_golden_v2.jsonl``  the golden set (one JSON object per line)
``data/benchmarks/holdout_v2.json``          the frozen hold-out manifest
``data/benchmarks/expert_review_v2.csv``     the stratified sample for expert review
"""
from __future__ import annotations

import argparse
import csv
import json
import os

from .generate import generate
from .golden import (coverage_report, expert_review_sample, load_golden, validate, write_golden)
from .splits import save_split, verify_split

DEFAULT_GOLDEN = "data/benchmarks/autosar_golden_v2.jsonl"
DEFAULT_SPLIT = "data/benchmarks/holdout_v2.json"
DEFAULT_REVIEW = "data/benchmarks/expert_review_v2.csv"
REVIEW_COLUMNS = [
    "query_id", "category", "difficulty", "answerable", "question", "gold_answer",
    "gold_evidence_ids", "gold_source_documents", "gold_pages", "gold_requirement_ids",
    "needs_expert_review", "review_decision", "review_notes", "corrected_answer",
]


def write_review_csv(path: str, items: list[dict]) -> int:
    """Export the expert-review sample as a CSV with empty decision columns."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for item in items:
            row = dict(item)
            row["gold_evidence_ids"] = " | ".join(item.get("gold_evidence_ids", []))
            row["gold_source_documents"] = " | ".join(item.get("gold_source_documents", []))
            row["gold_pages"] = " | ".join(str(p) for p in item.get("gold_pages", []))
            row["gold_requirement_ids"] = " | ".join(item.get("gold_requirement_ids", []))
            row["review_decision"] = ""       # expert fills: accept | reject | edit
            row["review_notes"] = ""
            row["corrected_answer"] = ""
            writer.writerow(row)
    return len(items)


def build(canonical: str, golden_path: str, split_path: str, review_path: str,
          target: int = 320, review_size: int = 40, seed: int = 20261021) -> dict:
    items = generate(canonical, target=target, seed=seed)
    problems = validate(items)
    if problems:
        raise SystemExit("golden set failed validation:\n  " + "\n  ".join(problems[:20]))
    n = write_golden(golden_path, items)
    manifest = save_split(split_path, items, golden_path)
    drift = verify_split(load_golden(golden_path), manifest, golden_path)
    sample = expert_review_sample(items, size=review_size, seed=seed)
    write_review_csv(review_path, sample)
    report = coverage_report(items)
    report["golden_path"] = golden_path
    report["split_path"] = split_path
    report["review_csv"] = review_path
    report["split_counts"] = manifest["counts"]
    report["split_drift"] = drift
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the golden set and freeze the hold-out split")
    ap.add_argument("--canonical", default="data/canonical/canonical.db")
    ap.add_argument("--golden", default=DEFAULT_GOLDEN)
    ap.add_argument("--split", default=DEFAULT_SPLIT)
    ap.add_argument("--review", default=DEFAULT_REVIEW)
    ap.add_argument("--target", type=int, default=320)
    ap.add_argument("--review-size", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261021)
    args = ap.parse_args()
    report = build(args.canonical, args.golden, args.split, args.review,
                   target=args.target, review_size=args.review_size, seed=args.seed)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
