"""Automated embedding-backend benchmark against the golden set.

Runs the retrieval-mode evaluation harness for each backend in a separate process
so settings are reloaded cleanly, then writes a comparison JSON.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKENDS = ["tfidf", "sbert"]
GOLDEN = "data/benchmarks/autosar_golden_v2.jsonl"
CANONICAL = "data/canonical/canonical.db"
OUT_ROOT = "reports/embedding-benchmark"


def main() -> int:
    results = {}
    for backend in BACKENDS:
        index_path = f"data/indexes/hybrid-{backend}"
        out_dir = f"{OUT_ROOT}/{backend}"
        if Path(index_path).exists():
            shutil.rmtree(index_path, ignore_errors=True)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["ASRBRAIN_EMBEDDING_BACKEND"] = backend
        cmd = [
            sys.executable, "-m", "src.evaluation.cli", "run",
            "--golden", GOLDEN,
            "--canonical", CANONICAL,
            "--index", index_path,
            "--out", out_dir,
            "--mode", "retrieval",
            "--label", f"embedding-{backend}",
        ]
        print(f"=== Running backend: {backend} ===")
        proc = subprocess.run(cmd, cwd=ROOT, env=env, text=True)
        if proc.returncode != 0:
            results[backend] = {"error": f"exit {proc.returncode}"}
            continue
        latest = Path(out_dir) / "latest.json"
        if latest.exists():
            payload = json.loads(latest.read_text(encoding="utf-8"))
            agg = payload.get("aggregate", {})
            results[backend] = {
                "context_recall": agg.get("context_recall", {}).get("value"),
                "context_precision": agg.get("context_precision", {}).get("value"),
                "citation_precision": agg.get("citation_precision", {}).get("value"),
                "exact_id_match": agg.get("exact_id_match", {}).get("value"),
                "latency_p95_s": agg.get("latency_p95_s"),
                "n": agg.get("n"),
            }
    out = Path(OUT_ROOT) / "comparison.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY