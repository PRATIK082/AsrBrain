"""Qdrant mirror (Phase 1 optional): dense+BM25 payloads with metadata filters (spec §11).

Requires qdrant-client + running Qdrant. Local HybridIndex remains the default;
this module is used by ops to push the same canonical chunks to Qdrant.
"""
from __future__ import annotations

COLLECTION_SCHEMA = {
    "vectors": {"size": 0, "distance": "Cosine"},  # size set at upload from local matrix width
    "payload": ["platform", "autosar_release", "module", "document_type",
                "page_start", "requirement_ids", "api_names", "chunk_kind", "document_id",
                "tenant_id", "project_id", "workspace_id", "vendor_scope",
                "data_classification", "artifact_type"],
    "required_filters": ["tenant_id"],  # mandatory on every query — never search without tenant scope
}


def build_mandatory_filter(ctx) -> dict:
    """Server-side mandatory Qdrant filter. Raises if tenant scope missing (default-deny)."""
    tenant = getattr(ctx, "tenant_id", "") if not isinstance(ctx, dict) else ctx.get("tenant_id", "")
    if not tenant:
        raise PermissionError("mandatory tenant_id filter missing — query denied")
    f: dict = {"tenant_id": tenant}
    proj = getattr(ctx, "project_id", None) if not isinstance(ctx, dict) else ctx.get("project_id")
    ws = getattr(ctx, "workspace_id", None) if not isinstance(ctx, dict) else ctx.get("workspace_id")
    if proj:
        f["project_id"] = proj
    if ws:
        f["workspace_id"] = ws
    return f


def search(client, collection: str, vector: list[float], ctx, limit: int = 10,
           extra_filter: dict | None = None) -> list:
    """Tenant-enforced search wrapper. Mandatory filter cannot be overridden by callers."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    must = build_mandatory_filter(ctx)
    if extra_filter:
        for k in ("tenant_id", "project_id", "workspace_id"):
            if k in extra_filter and extra_filter[k] != must.get(k, extra_filter[k]):
                raise PermissionError(f"client filter override denied for '{k}'")
        must = {**must, **{k: v for k, v in extra_filter.items() if k not in must}}
    qfilter = Filter(must=[FieldCondition(key=k, match=MatchValue(value=v)) for k, v in must.items()])
    res = client.query_points(collection_name=collection, query=vector, query_filter=qfilter, limit=limit)
    return res.points
