"""Build a machine-readable description of the running AsrBrain instance.

The self-context manifest lets the UI, agents and operators adapt to the
actual deployment instead of assuming features, data or models are present.
"""

from __future__ import annotations

import json
import sqlite3
import urllib.request
from pathlib import Path
from typing import Any

from src.config.settings import settings
from src.config.deployment import load_profile


PROFILES = ("workstation", "onprem-server", "cloud-saas")


def _safe_count(db_path: str, table: str) -> int:
    if not db_path or not Path(db_path).exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not row or row[0] == 0:
                return 0
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()
    except Exception:
        return 0


def _table_counts(db_path: str, tables: list[str]) -> dict[str, int]:
    return {t: _safe_count(db_path, t) for t in tables}


def _llm_health() -> dict[str, Any]:
    url = settings.ollama_base_url.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name") for m in data.get("models", []) if m.get("name")]
        return {"status": "ok", "models": models}
    except Exception as exc:
        return {"status": "unreachable", "error": str(exc), "models": []}


def _capabilities() -> dict[str, bool]:
    return {
        "auth": True,
        "workspaces": True,
        "collections": True,
        "document_preview": True,
        "evidence_api": True,
        "provider_registry": True,
        "pipeline_config_versioning": True,
        "multi_hop": _env_bool("ASRBRAIN_RETRIEVAL_USE_MULTI_HOP", False),
        "arxml": settings.arxml_enabled,
        "diff": settings.diff_enabled,
        "code_intelligence": settings.code_intel_enabled,
        "cloud_routing": settings.cloud_routing_enabled,
        "vendor_plugins": settings.vendor_plugins_enabled,
        "strict_local_only": settings.strict_local_only,
    }


def _env_bool(name: str, default: bool = False) -> bool:
    import os

    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _feature_catalog() -> list[dict[str, Any]]:
    caps = _capabilities()
    features = [
        {
            "id": "chat.ask",
            "name": "Ask with citations",
            "category": "chat",
            "status": "available",
            "requires": ["auth"],
        },
        {
            "id": "ingest.documents",
            "name": "Ingest PDFs and documents",
            "category": "knowledge",
            "status": "available",
            "requires": [],
        },
        {
            "id": "arxml.topology",
            "name": "ARXML topology analysis",
            "category": "autosar",
            "status": "available" if caps["arxml"] else "disabled",
            "requires": ["arxml"],
        },
        {
            "id": "retrieval.multi_hop",
            "name": "Multi-hop reasoning",
            "category": "retrieval",
            "status": "available" if caps["multi_hop"] else "needs_setup",
            "requires": ["multi_hop"],
        },
        {
            "id": "admin.models",
            "name": "Model provider management",
            "category": "admin",
            "status": "available",
            "requires": ["provider_registry"],
        },
        {
            "id": "admin.config",
            "name": "Pipeline configuration versioning",
            "category": "admin",
            "status": "available",
            "requires": ["pipeline_config_versioning"],
        },
    ]
    return features


def build_self_context() -> dict[str, Any]:
    profile = settings.deployment_profile if settings.deployment_profile in PROFILES else "workstation"
    canonical = settings.canonical_db
    chat_db = "data/canonical/chat.db"

    canonical_counts = _table_counts(
        canonical,
        ["documents", "chunks", "tables", "figures", "collections", "users", "model_providers"],
    )
    chat_counts = _table_counts(chat_db, ["conversations", "messages"])

    caps = _capabilities()
    features = _feature_catalog()

    recommended: list[str] = []
    if canonical_counts["documents"] == 0:
        recommended.append("Ingest your first document or ARXML file.")
    if not caps["multi_hop"]:
        recommended.append("Enable ASRBRAIN_RETRIEVAL_USE_MULTI_HOP for complex questions.")
    if profile == "workstation":
        recommended.append("You are in workstation mode; enable onprem-server profile for team use.")

    return {
        "profile": profile,
        "profile_config": load_profile(profile),
        "version": {
            "app": "asrbrain",
            "pipeline": settings.pipeline_version,
            "git_commit": _git_commit(),
        },
        "capabilities": caps,
        "features": features,
        "data": {
            "canonical_db": canonical,
            "counts": {**canonical_counts, "conversations": chat_counts["conversations"], "messages": chat_counts["messages"]},
        },
        "models": {
            "llm_model": settings.llm_model,
            "embedding_backend": settings.embedding_backend,
            "ollama": _llm_health(),
        },
        "storage": {
            "canonical_db_exists": Path(canonical).exists(),
            "chat_db_exists": Path(chat_db).exists(),
        },
        "limits": {
            "final_evidence": settings.final_evidence,
            "topk_bm25": settings.topk_bm25,
            "topk_dense": settings.topk_dense,
        },
        "security": {
            "strict_local_only": settings.strict_local_only,
            "cloud_routing_enabled": settings.cloud_routing_enabled,
        },
        "health": {
            "canonical_db": "ok" if Path(canonical).exists() else "missing",
            "chat_db": "ok" if Path(chat_db).exists() else "missing",
        },
        "recommended_actions": recommended,
    }


def _git_commit() -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except Exception:
        return "unknown"