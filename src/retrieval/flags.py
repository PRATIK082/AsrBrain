"""Retrieval feature flags: every retrieval component behind an env-driven switch.

Each component (channels, fusion mode, reranking weights, filters, expansion, exact-ID
path, rewrite, corrective loop) can be toggled independently so that ablations on the
golden set measure instead of argue. There is a single source of truth for flags here:
the pipeline flag is read from ``RAG_PIPELINE_VERSION`` with the legacy
``ASRBRAIN_PIPELINE_VERSION`` spelling as fallback, because two spellings of one flag
is how a reversible setup quietly stops being reversible.

Environment variables use the ``ASRBRAIN_RETRIEVAL_`` prefix and a boolean or numeric value::

    ASRBRAIN_RETRIEVAL_USE_DENSE=false
    ASRBRAIN_RETRIEVAL_W_FUSED=0.6
    ASRBRAIN_RETRIEVAL_EXACT_ID_FAST_PATH=false
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields, replace

ENV_PREFIX = "ASRBRAIN_RETRIEVAL_"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(ENV_PREFIX + name.upper())
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(ENV_PREFIX + name.upper())
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class RetrievalFlags:
    """Which retrieval components are active.

    The default weights are the starting point; keep the set that the ablation
    measurements support and change the rest with the numbers on record.
    """

    # --- channels -------------------------------------------------------------
    use_dense: bool = True
    use_bm25: bool = True
    #: ``rrf`` = reciprocal rank fusion, ``weighted`` = per-intent min-max normalised fusion
    fusion: str = "weighted"

    # --- reranking ------------------------------------------------------------
    use_rerank: bool = True
    w_fused: float = 0.50
    w_overlap: float = 0.20
    w_exact: float = 0.30

    # --- filtering ------------------------------------------------------------
    version_filter: bool = True
    module_filter: bool = True
    #: relax the module filter when the surviving pool is smaller than this share of
    #: the corpus (a module absent from the indexed documents would otherwise leave
    #: only the module-less project-source chunks and answer from almost nothing)
    pool_relax_ratio: float = 0.02

    # --- expansion ------------------------------------------------------------
    parent_expand: bool = True

    # --- exact identifier path ------------------------------------------------
    exact_id_fast_path: bool = True
    exact_id_weight: float = 1.0

    # --- query handling -------------------------------------------------------
    use_rewrite: bool = True
    corrective_loop: bool = True
    corrective_min_evidence: int = 3

    @classmethod
    def from_env(cls) -> "RetrievalFlags":
        defaults = cls()
        return cls(
            use_dense=_env_bool("use_dense", defaults.use_dense),
            use_bm25=_env_bool("use_bm25", defaults.use_bm25),
            fusion=os.environ.get(ENV_PREFIX + "FUSION", defaults.fusion).strip().lower(),
            use_rerank=_env_bool("use_rerank", defaults.use_rerank),
            w_fused=_env_float("w_fused", defaults.w_fused),
            w_overlap=_env_float("w_overlap", defaults.w_overlap),
            w_exact=_env_float("w_exact", defaults.w_exact),
            version_filter=_env_bool("version_filter", defaults.version_filter),
            module_filter=_env_bool("module_filter", defaults.module_filter),
            pool_relax_ratio=_env_float("pool_relax_ratio", defaults.pool_relax_ratio),
            parent_expand=_env_bool("parent_expand", defaults.parent_expand),
            exact_id_fast_path=_env_bool("exact_id_fast_path", defaults.exact_id_fast_path),
            exact_id_weight=_env_float("exact_id_weight", defaults.exact_id_weight),
            use_rewrite=_env_bool("use_rewrite", defaults.use_rewrite),
            corrective_loop=_env_bool("corrective_loop", defaults.corrective_loop),
            corrective_min_evidence=_env_int("corrective_min_evidence",
                                             defaults.corrective_min_evidence),
        )

    def with_overrides(self, **kw) -> "RetrievalFlags":
        """Return a copy with the given fields replaced. Unknown fields are rejected."""
        known = {f.name for f in fields(self)}
        unknown = set(kw) - known
        if unknown:
            raise TypeError(f"unknown retrieval flags: {sorted(unknown)}")
        return replace(self, **kw)

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(ENV_PREFIX + name.upper())
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_flags() -> RetrievalFlags:
    """The flags in force for this process."""
    return RetrievalFlags.from_env()
