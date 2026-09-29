"""Ablation matrix A–J (spec §23). Each arm toggles a pipeline stage; reports shared metrics."""
from __future__ import annotations
import copy

ARMS = {
    "B_dense_only": {"use_bm25": False, "rrf": False, "rerank": False},
    "C_bm25_only": {"use_dense": False, "rrf": False, "rerank": False},
    "D_dense_bm25": {"rrf": False, "rerank": False},
    "E_rrf": {"rerank": False},
    "F_reranked": {},
    "G_version_filtered": {"version_filter": True},
    "H_hierarchical": {"version_filter": True, "parent_expand": True},
    "J_full_verified": {"version_filter": True, "parent_expand": True, "verify": True},
}

METRIC_COLUMNS = ["Recall@10", "MRR", "Faithfulness(proxy: claim_support)", "Citation precision",
                  "Version accuracy", "Latency", "Memory"]
