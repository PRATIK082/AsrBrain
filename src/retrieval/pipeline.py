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

    def retrieve(self, query: str, top_k_final: int = 0) -> dict:
        top_k_final = top_k_final or settings.final_evidence
        plan: QueryPlan = parse(query)
        rw = rewrite(plan)

        def per_release(release: str) -> list[dict]:
            pool = apply_filters(self.chunks, plan, release_override=release)
            idx_map = [self.chunks.index(c) for c in pool] or list(range(len(self.chunks)))
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
                "retrieval_score": round(retrieval_score, 4)}
