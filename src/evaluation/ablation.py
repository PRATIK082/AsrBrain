"""Ablation arms for the retrieval upgrade. Each arm is a set of RetrievalFlags
overrides; the empty dict is the full pipeline. Run one arm per harness invocation
and compare the aggregates — that table decides what stays.

Arms (each disables or swaps exactly one component of the full pipeline):
"""
from __future__ import annotations

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



