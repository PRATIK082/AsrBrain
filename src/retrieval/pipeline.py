"""Multi-stage retrieval pipeline (spec §10)."""
from __future__ import annotations
import numpy as np
from ..config.settings import settings
from ..indexing.hybrid import HybridIndex
from ..schema.queries import QueryPlan
from .query_understanding import parse
from .query_rewriting import rewrite
from .metadata_filter import apply_filters
from .fusion import rrf, weighted_fusion
from .reranking import rerank
from .context import parent_expand, compress


class RetrievalPipeline:
    def __init__(self, index: HybridIndex, chunks: list[dict]):
        self.index = index
        self.chunks = chunks
        self.by_id = {c["chunk_id"]: c for c in chunks}

    def retrieve(self, query: str, top_k_final: int = 0, scope=None) -> dict:
        """Retrieve evidence inside a scope.

        The scope is applied **before** anything is scored (Phase 5): a chunk
        that is out of scope can never be ranked into the answer. The scope
        report travels with the result so the caller can show what was
        filtered and which filters could not be applied at all.
        """
        top_k_final = top_k_final or settings.final_evidence
        plan: QueryPlan = parse(query)
        rw = rewrite(plan)

        # Scope first (Phase 5): the caller's scope decides the plan before
        # anything is scored, so the release/platform/module filters that run
        # later can never contradict the scope.
        if scope is not None:
            from .scope import scope_from_dict
            scope_obj = scope_from_dict(scope) if isinstance(scope, dict) else scope
            if scope_obj.releases:
                plan.releases = list(scope_obj.releases)
                plan.release_mode = ("exact" if len(scope_obj.releases) == 1
                                     else "comparison")
            if scope_obj.platforms:
                plan.platforms = list(scope_obj.platforms)
            if scope_obj.modules:
                plan.modules = list(scope_obj.modules)
            if scope_obj.document_types:
                plan.document_types = list(scope_obj.document_types)

        scoped = self.chunks
        scope_report: dict = {"applied": False, "kept": len(self.chunks),
                              "dropped": {}, "dropped_total": 0, "unapplied": [],
                              "scope": {}, "total": len(self.chunks)}
        if scope is not None:
            from .scope import apply_scope
            result = apply_scope(self.chunks, scope)
            scoped = result.kept
            scope_report = result.to_dict()
            scope_report["applied"] = True

        def per_release(release: str) -> list[dict]:
            pool = apply_filters(scoped, plan, release_override=release)
            # score only the filtered pool; fuse the raw AND the corrected query
            # so a bad auto-correction can never sink a good original (and vice
            # versa) — the "Interpreted as" form only ADDS recall.
            dense_all = self.index.dense_scores(query)
            bm25_all = self.index.bm25_scores(query)
            norm_q = plan.normalized_query or query
            if norm_q != query:
                dense_all = (dense_all + self.index.dense_scores(norm_q)) / 2.0
                bm25_all = (bm25_all + self.index.bm25_scores(norm_q)) / 2.0
            order = np.argsort(-dense_all)[: settings.topk_dense]
            dense_rank = [self.index.chunk_ids[i] for i in order if self.index.chunk_ids[i] in {c["chunk_id"] for c in pool}]
            order_b = np.argsort(-bm25_all)[: settings.topk_bm25]
            bm25_rank = [self.index.chunk_ids[i] for i in order_b if self.index.chunk_ids[i] in {c["chunk_id"] for c in pool}]
            # exact-identifier fast path (§19 workflow A): requirement/API hit jumps the queue
            fused = rrf([bm25_rank, dense_rank], k=settings.rrf_k)
            cands = []
            for cid, s in sorted(fused.items(), key=lambda kv: -kv[1])[: settings.rerank_pool]:
                c = dict(self.by_id[cid])
                c["fused_score"] = round(float(s), 5)
                cands.append(c)
            ranked = rerank(query, cands, top_n=settings.rerank_pool)
            expanded = parent_expand(ranked, self.by_id)
            final = expanded[:top_k_final]
            for c in final:
                c["compressed"] = compress(c.get("normalized_text", ""), query)
            return final

        if plan.release_mode == "comparison" and plan.releases:
            per_rel = {r: per_release(r) for r in plan.releases}
            # interleave for balanced comparison evidence
            merged, seen = [], set()
            for i in range(top_k_final):
                for r in plan.releases:
                    if i < len(per_rel[r]) and per_rel[r][i]["chunk_id"] not in seen:
                        merged.append(per_rel[r][i])
                        seen.add(per_rel[r][i]["chunk_id"])
            evidence = merged[:top_k_final]
        else:
            per_rel = {}
            evidence = per_release("")

        # evidence sufficiency signals for confidence/abstain (§18)
        retrieval_score = float(np.mean([c.get("rerank_score", 0) for c in evidence])) if evidence else 0.0
        return {"plan": plan.model_dump(), "rewrites": rw, "evidence": evidence,
                "per_release": {k: len(v) for k, v in per_rel.items()},
                "retrieval_score": round(retrieval_score, 4),
                "scope": scope_report}
