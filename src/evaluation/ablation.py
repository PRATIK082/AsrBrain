"""Ablation arms for the retrieval upgrade. Each arm is a set of RetrievalFlags
overrides; the empty dict is the full pipeline. Run one arm per harness invocation
and compare the aggregates — that table decides what stays.

Arms (each disables or swaps exactly one component of the full pipeline):
"""
from __future__ import annotations

import os

ARMS: dict[str, dict] = {
    "A_full": {},
    "B_no_dense": {"use_dense": False},
    "C_no_bm25": {"use_bm25": False},
    "D_fusion_rrf": {"fusion": "rrf"},
    "E_no_rerank": {"use_rerank": False},
    "F_no_exact_path": {"exact_id_fast_path": False},
    "G_no_rewrite": {"use_rewrite": False},
    "H_no_corrective": {"corrective_loop": False},
    "I_no_parent_expand": {"parent_expand": False},
    "J_no_module_filter": {"module_filter": False},
    "K_no_version_filter": {"version_filter": False},
}

METRIC_COLUMNS = ["arm", "n", "context_recall", "no_evidence", "p50_s", "p95_s"]


def run_ablation(golden_path: str, canonical: str, index_path: str,
                 split_path: str | None, out_root: str,
                 arms: dict[str, dict] | None = None) -> list[dict]:
    """Run every arm on the train split in retrieval mode; return one row per arm."""
    from .runner import run_evaluation
    rows = []
    for name, overrides in (arms or ARMS).items():
        out_dir = os.path.join(out_root, name)
        payload = run_evaluation(golden_path=golden_path, canonical=canonical,
                                 index_path=index_path, out_dir=out_dir,
                                 split_path=split_path, split="train",
                                 mode="retrieval", use_llm=False,
                                 label=f"ablation-{name}",
                                 flag_overrides=overrides or None)
        agg = payload["aggregate"]
        fails = (agg.get("failures") or {})
        if isinstance(fails, dict):
            no_ev = fails.get("no_evidence_retrieved", 0)
        else:
            no_ev = 0
        rows.append({
            "arm": name,
            "n": agg.get("n", 0),
            "context_recall": round((agg.get("context_recall") or {}).get("value") or 0.0, 4),
            "no_evidence": no_ev,
            "p50_s": agg.get("latency_p50_s"),
            "p95_s": agg.get("latency_p95_s"),
        })
        print(row_line(rows[-1]), flush=True)
    return rows


def row_line(r: dict) -> str:
    return (f"{r['arm']:18s} n={r['n']:<4d} recall={r['context_recall']:.4f} "
            f"no_ev={r['no_evidence']:<3d} p50={r['p50_s']:.3f}s p95={r['p95_s']:.3f}s")


def markdown_table(rows: list[dict]) -> str:
    base = next(r for r in rows if r["arm"] == "A_full")
    out = ["| arm | n | recall | Δ vs full | no_evidence | p50 (s) | p95 (s) |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        delta = r["context_recall"] - base["context_recall"]
        out.append(f"| {r['arm']} | {r['n']} | {r['context_recall']:.4f} | "
                   f"{delta:+.4f} | {r['no_evidence']} | {r['p50_s']:.3f} | {r['p95_s']:.3f} |")
    return "\n".join(out)
