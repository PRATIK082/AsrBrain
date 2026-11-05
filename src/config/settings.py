"""Central configuration (spec §21). All model/index selection via env."""
from __future__ import annotations
import os
from dataclasses import dataclass, field


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _load_token_caps() -> dict:
    """User-editable caps from config/generation.yaml; env LLM_NUM_PREDICT wins."""
    caps = {"concise": 400, "standard": 600, "detailed": 1200,
            "num_ctx": 8192, "eco": 4, "balanced": 8, "deep": 12}
    try:
        import os as _os
        root = _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__)))
        cfg = _os.path.join(root, "config", "generation.yaml")
        if _os.path.exists(cfg):
            cur: dict | None = None
            with open(cfg, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s.startswith("concise:"):
                        caps["concise"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("standard:"):
                        caps["standard"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("detailed:"):
                        caps["detailed"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("num_ctx:"):
                        caps["num_ctx"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("eco:"):
                        caps["eco"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("balanced:"):
                        caps["balanced"] = int(s.split(":")[1].split("#")[0])
                    elif s.startswith("deep:"):
                        caps["deep"] = int(s.split(":")[1].split("#")[0])
    except Exception:
        pass
    return caps


TOKEN_CAPS = _load_token_caps()


@dataclass
class Settings:
    llm_model: str = field(default_factory=lambda: _get("LLM_MODEL", "qwen3:14b"))
    embedding_model: str = field(default_factory=lambda: _get("EMBEDDING_MODEL", "all-mpnet-base-v2"))
    embedding_backend: str = field(default_factory=lambda: _get("EMBEDDING_BACKEND", "tfidf"))  # tfidf|sbert
    reranker_model: str = field(default_factory=lambda: _get("RERANKER_MODEL", "none"))
    ollama_base_url: str = field(default_factory=lambda: _get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    ollama_timeout_s: float = field(default_factory=lambda: float(_get("OLLAMA_TIMEOUT_S", "180")))
    llm_num_predict: int = field(default_factory=lambda: int(_get("LLM_NUM_PREDICT", str(TOKEN_CAPS.get("standard", 600)))))
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
    # One source of truth for the pipeline flag. The API, the compose file and
    # .env.example set RAG_PIPELINE_VERSION; the legacy ASRBRAIN_PIPELINE_VERSION
    # spelling is still honoured as a fallback.
    pipeline_version: str = field(default_factory=lambda: _get(
        "RAG_PIPELINE_VERSION", _get("ASRBRAIN_PIPELINE_VERSION", "v2")))
    arxml_enabled: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_ARXML_ENABLED", True))
    diff_enabled: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_DIFF_ENABLED", True))
    code_intel_enabled: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_CODE_INTELLIGENCE_ENABLED", True))
    cloud_routing_enabled: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_CLOUD_ROUTING_ENABLED", False))
    strict_local_only: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_STRICT_LOCAL_ONLY", True))
    vendor_plugins_enabled: bool = field(default_factory=lambda: _env_bool("ASRBRAIN_VENDOR_PLUGINS_ENABLED", False))
    deployment_profile: str = field(default_factory=lambda: _get("ASRBRAIN_DEPLOYMENT_PROFILE", "workstation"))


settings = Settings()
