"""Central configuration (spec §21). All model/index selection via env."""
from __future__ import annotations
import os
from dataclasses import dataclass, field


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass
class Settings:
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "qwen3:14b"))
    embedding_model: str = field(default_factory=lambda: _get("EMBEDDING_MODEL", "all-mpnet-base-v2"))
    embedding_backend: str = field(default_factory=lambda: _get("EMBEDDING_BACKEND", "tfidf"))  # tfidf|sbert
    reranker_model: str = field(default_factory=lambda: _get("RERANKER_MODEL", "none"))
    ollama_base_url: str = field(default_factory=lambda: _get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    ollama_timeout_s: float = field(default_factory=lambda: float(_get("OLLAMA_TIMEOUT_S", "180")))
    llm_num_predict: int = field(default_factory=lambda: int(_get("LLM_NUM_PREDICT", "600")))
    topk_bm25: int = field(default_factory=lambda: int(_get("TOPK_BM25", "50")))
    topk_dense: int = field(default_factory=lambda: int(_get("TOPK_DENSE", "50")))
    fusion_pool: int = field(default_factory=lambda: int(_get("FUSION_POOL", "100")))
    rerank_pool: int = field(default_factory=lambda: int(_get("RERANK_POOL", "60")))
    final_evidence: int = field(default_factory=lambda: int(_get("FINAL_EVIDENCE", "12")))
    rrf_k: int = field(default_factory=lambda: int(_get("RRF_K", "60")))
    canonical_db: str = field(default_factory=lambda: _get("CANONICAL_DB", "data/canonical/canonical.db"))
    pdf_dir: str = field(default_factory=lambda: _get("PDF_DIR", "pdf"))
    qdrant_url: str = field(default_factory=lambda: _get("QDRANT_URL", "http://localhost:6333"))
    qdrant_collection: str = field(default_factory=lambda: _get("QDRANT_COLLECTION", "autosar_chunks"))
    # Enterprise orchestration Phase 2/3 feature flags (reversible migration)
    pipeline_version: str = field(default_factory=lambda: _get("ASRBRAIN_PIPELINE_VERSION", "v1"))
    arxml_enabled: bool = field(default_factory=lambda: _get("ASRBRAIN_ARXML_ENABLED", "true").lower() == "true")
    diff_enabled: bool = field(default_factory=lambda: _get("ASRBRAIN_DIFF_ENABLED", "true").lower() == "true")
    code_intel_enabled: bool = field(default_factory=lambda: _get("ASRBRAIN_CODE_INTELLIGENCE_ENABLED", "true").lower() == "true")
    cloud_routing_enabled: bool = field(default_factory=lambda: _get("ASRBRAIN_CLOUD_ROUTING_ENABLED", "false").lower() == "true")
    strict_local_only: bool = field(default_factory=lambda: _get("ASRBRAIN_STRICT_LOCAL_ONLY", "true").lower() == "true")
    vendor_plugins_enabled: bool = field(default_factory=lambda: _get("ASRBRAIN_VENDOR_PLUGINS_ENABLED", "false").lower() == "true")


settings = Settings()
