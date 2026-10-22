"""CI gate: fail the build when a headline metric regresses beyond its tolerance.

The gate is deliberately dull: a JSON file of thresholds, a run payload, a comparison and an
exit code. The thresholds live in the repository so that a regression has to be *accepted
deliberately* — someone edits the threshold file in a reviewed commit — rather than discovered
later.
"""
from __future__ import annotations

import json
import os

#: Metric direction: "min" means a *higher* value is better, "max" means lower is better.
DEFAULT_GATE = {
    "context_recall": {"min": 0.0, "tolerance": 0.02},
    "citation_precision": {"min": 0.0, "tolerance": 0.02},
    "faithfulness": {"min": 0.0, "tolerance": 0.02},
    "abstention_accuracy": {"min": 0.0, "tolerance": 0.02},
    "answer_correctness": {"min": 0.0, "tolerance": 0.05},
    "hallucinated_id_rate_mean": {"max": 1.0, "tolerance": 0.005},
    "latency_p95_s": {"max": 1e9, "tolerance": 2.0},
}


def _value(payload: dict, metric: str):
    agg = payload.get("aggregate", {})
    block = agg.get(metric)
    if isinstance(block, dict):
        return block.get("value")
    return block


def compare(payload: dict, gate: dict | None = None) -> dict:
    """Compare a run against the gate. Returns the verdict, never raises."""
    gate = gate or DEFAULT_GATE
    checks: list[dict] = []
    passed = True
    for metric, rule in sorted(gate.items()):
        measured = _value(payload, metric)
        if measured is None:
            checks.append({"metric": metric, "status": "skipped", "reason": "not measured"})
            continue
        if "min" in rule:
            baseline = rule["min"]
            tolerance = rule.get("tolerance", 0.0)
            ok = measured >= baseline - tolerance
            checks.append({
                "metric": metric, "measured": measured, "threshold": baseline,
                "tolerance": tolerance, "direction": "min", "status": "pass" if ok else "fail",
            })
        else:
            baseline = rule["max"]
            tolerance = rule.get("tolerance", 0.0)
            ok = measured <= baseline + tolerance
            checks.append({
                "metric": metric, "measured": measured, "threshold": baseline,
                "tolerance": tolerance, "direction": "max", "status": "pass" if ok else "fail",
            })
        if not ok:
            passed = False
    return {
        "passed": passed,
        "label": payload.get("label"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "split": payload.get("split"),
        "checks": checks,
    }


def load_gate(path: str) -> dict:
    if not os.path.exists(path):
        return dict(DEFAULT_GATE)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("metrics", data)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Fail when a headline metric regresses")
    ap.add_argument("--run", default="reports/evaluation/latest.json")
    ap.add_argument("--gate", default="data/benchmarks/eval_gate.json")
    ap.add_argument("--report", default="reports/evaluation/gate.json")
    args = ap.parse_args()
    with open(args.run, encoding="utf-8") as fh:
        payload = json.load(fh)
    verdict = compare(payload, load_gate(args.gate))
    os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
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


if __name__ == "__main__":
    raise SystemExit(main())
