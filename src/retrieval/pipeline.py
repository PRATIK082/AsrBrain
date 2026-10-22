"""Retrieval pipeline: plan -> filter -> hybrid channels -> fuse -> rerank -> expand.

Every stage is behind a feature flag (``src/retrieval/flags.py``) so ablations on the
golden set decide what stays. The design points:

* **exact-ID fast path** — a query that names a requirement id, an API name or an ECUC
  parameter retrieves the chunks that carry it directly, without waiting for the scorers.
  A post-hoc rerank boost alone cannot recover a chunk the channels never returned.
* **the rewrite is used** — the corrected query form is scored and fused together with
  the original instead of being thrown away.
* **the corrective loop** — when the evidence is too thin the query is retried without
  the module constraint before the system gives up.
* **per-intent weighted fusion** — both channels are min-max normalised per intent, so
  the fused score weighs against the overlap and exact-identifier signals on the same
  scale (raw RRF values around 0.02 carried almost none of the final ranking).
"""
from __future__ import annotations

import re

import numpy as np

from ..config.settings import settings
from ..indexing.hybrid import HybridIndex
from ..schema.queries import QueryPlan
from .context import compress, order_evidence, parent_expand
from .flags import RetrievalFlags, default_flags
from .fusion import normalise_scores, rrf, weighted_fusion
from .metadata_filter import apply_filters_ex
from .query_rewriting import rewrite
from .query_understanding import parse
from .reranking import rerank

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class RetrievalPipeline:
    def __init__(self, index: HybridIndex, chunks: list[dict],
                 flags: RetrievalFlags | None = None):
        self.index = index
        self.chunks = chunks
        self.flags = flags or default_flags()
        self.by_id = {c["chunk_id"]: c for c in chunks}
        self._exact_index = self._build_exact_index()

    # ------------------------------------------------------------------ planning
    def plan_for(self, query: str) -> QueryPlan:
        """The query plan, without retrieving anything.

        The clarify gate needs the plan and the corpus statistics but not the evidence, so
        that a clarification no longer pays for a full retrieval that is then discarded.
        """
        return parse(query)

    # ------------------------------------------------------------------ exact path
    def _build_exact_index(self) -> dict[str, list[str]]:
        """identifier (lower-cased) -> chunk ids that carry it."""
        index: dict[str, list[str]] = {}
        for c in self.chunks:
            for field in ("requirement_ids", "api_names", "ecu_parameters"):
                for ident in (c.get(field) or []):
                    key = str(ident).lower()
                    index.setdefault(key, []).append(c["chunk_id"])
        return index

    def _exact_candidates(self, plan: QueryPlan, pool_ids: set[str]) -> list[str]:
        """Chunk ids that carry an identifier named in the query."""
        if not self.flags.exact_id_fast_path:
            return []
        wanted: list[str] = []
        for ident in (list(plan.requirement_ids or []) + list(plan.api_names or [])
                      + list(plan.configuration_parameters or [])):
            key = str(ident).lower()
            if len(key) < 4:
                continue
            wanted.extend(self._exact_index.get(key, []))
            # the signal extractor sometimes stores a truncated identifier ("PRS_E2E_"),
            # so a prefix of a whole query token also counts
            if key.endswith("_"):
                for other, ids in self._exact_index.items():
                    if other.startswith(key) and other != key:
                        wanted.extend(ids)
        seen: set[str] = set()
        out: list[str] = []
        for cid in wanted:
            if cid in seen or cid not in pool_ids:
                continue
            seen.add(cid)
            out.append(cid)
        return out

    # ------------------------------------------------------------------ channels
    def _channel_scores(self, queries: list[str]) -> tuple[dict[str, float], dict[str, float]]:
        """Mean dense and BM25 score per chunk id over the query variants."""
        ids = self.index.chunk_ids
        n = len(ids)
        dense = np.zeros(n)
        bm25 = np.zeros(n)
        used = 0
        for q in queries:
            if self.flags.use_dense:
                dense += self.index.dense_scores(q)
            if self.flags.use_bm25:
                bm25 += self.index.bm25_scores(q)
            used += 1
        used = max(1, used)
        dense /= used
        bm25 /= used
        pool = settings.fusion_pool
        dense_rank = np.argsort(-dense)[:pool]
        bm25_rank = np.argsort(-bm25)[:pool]
        dense_scores = {ids[i]: float(dense[i]) for i in dense_rank}
        bm25_scores = {ids[i]: float(bm25[i]) for i in bm25_rank}
        return dense_scores, bm25_scores

    def _fuse(self, dense_scores: dict[str, float], bm25_scores: dict[str, float],
              plan: QueryPlan) -> dict[str, float]:
        if self.flags.fusion == "rrf":
            # RRF works on ranks; the dense and BM25 channel scores are turned into rank
            # lists and the result is min-max normalised so that the reranker can weigh it
            # against the other two signals on the same scale.
            def to_ranks(scores: dict[str, float]) -> list[str]:
                return [cid for cid, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
            fused = rrf([to_ranks(bm25_scores), to_ranks(dense_scores)], k=settings.rrf_k)
            return normalise_scores(fused)
        return weighted_fusion(bm25_scores, dense_scores, plan.intent)

    # ------------------------------------------------------------------ one release
    def _retrieve_release(self, release: str, queries: list[str], plan: QueryPlan,
                          top_k_final: int) -> tuple[list[dict], dict]:
        pool, filter_trace = apply_filters_ex(self.chunks, plan, release_override=release,
                                               flags=self.flags)
        pool_ids = {c["chunk_id"] for c in pool}
        dense_scores, bm25_scores = self._channel_scores(queries)
        fused = self._fuse(dense_scores, bm25_scores, plan)

        exact_ids = self._exact_candidates(plan, pool_ids)
        for cid in exact_ids:
            fused[cid] = max(fused.get(cid, 0.0), self.flags.exact_id_weight)

        cands = []
        for cid, score in sorted(fused.items(), key=lambda kv: -kv[1])[: settings.rerank_pool]:
            # The metadata filter is a hard constraint, not a suggestion: channel scores
            # are computed over the whole corpus, so candidates must be re-checked
            # against the pool. (A release-excluded chunk was leaking back in here.)
            if cid not in pool_ids:
                continue
            chunk = self.by_id.get(cid)
            if chunk is None:
                continue
            cands.append({**chunk, "fused_score": round(float(score), 5),
                          "exact_hit": cid in set(exact_ids)})

        ranked = (rerank(queries[0], cands, top_n=settings.rerank_pool, flags=self.flags)
                  if self.flags.use_rerank else cands)
        expanded = parent_expand(ranked, self.by_id) if self.flags.parent_expand else ranked
        final = expanded[:top_k_final]
        if self.flags.order_model_last:
            final = order_evidence(final)
        for c in final:
            c["compressed"] = compress(c.get("normalized_text", ""), queries[0])
        filter_trace["exact_candidates"] = len(exact_ids)
        return final, filter_trace

    # ------------------------------------------------------------------ corrective
    def _corrective(self, queries: list[str], plan: QueryPlan, evidence: list[dict],
                    top_k_final: int) -> list[dict]:
        """Retry with the module constraint dropped before giving up (§6.2)."""
        if len(evidence) >= self.flags.corrective_min_evidence:
            return evidence
        relaxed = self.flags.with_overrides(module_filter=False)
        saved = self.flags
        try:
            self.flags = relaxed
            retry, _ = self._retrieve_release("", queries, plan, top_k_final)
        finally:
            self.flags = saved
        if len(retry) > len(evidence):
            return retry
        return evidence

    # ------------------------------------------------------------------ public
    def retrieve(self, query: str, top_k_final: int = 0, plan: QueryPlan | None = None) -> dict:
        top_k_final = top_k_final or settings.final_evidence
        plan = plan or self.plan_for(query)

        queries = [query]
        if self.flags.use_rewrite:
            rewrite(plan)  # populates plan.normalized_query / corrections
            norm_q = plan.normalized_query
            if norm_q and norm_q != query:
                queries.append(norm_q)

        per_rel: dict[str, int] = {}
        filter_traces: list[dict] = []
        if plan.release_mode == "comparison" and plan.releases:
            merged: list[dict] = []
            seen: set[str] = set()
            for release in plan.releases:
                rel_evidence, trace = self._retrieve_release(release, queries, plan, top_k_final)
                per_rel[release] = len(rel_evidence)
                filter_traces.append(trace)
                for i in range(top_k_final):
                    if i < len(rel_evidence) and rel_evidence[i]["chunk_id"] not in seen:
                        seen.add(rel_evidence[i]["chunk_id"])
                        merged.append(rel_evidence[i])
            evidence = merged[:top_k_final]
        else:
            evidence, trace = self._retrieve_release("", queries, plan, top_k_final)
            filter_traces.append(trace)

        if self.flags.corrective_loop:
            evidence = self._corrective(queries, plan, evidence, top_k_final)

        retrieval_score = (float(np.mean([c.get("rerank_score", 0) for c in evidence]))
                           if evidence else 0.0)
        return {"plan": plan.model_dump(), "rewrites": getattr(plan, "corrections", []),
                "evidence": evidence, "per_release": per_rel,
                "retrieval_score": round(retrieval_score, 4),
                "filter_trace": filter_traces,
                "flags": self.flags.as_dict()}
