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


def upload(chunks: list[dict], vectors, url: str, collection: str, tenant_id: str = "default"):
    from qdrant_client import QdrantClient
    from qdrant_client.models import VectorParams, Distance, PointStruct
    client = QdrantClient(url=url)
    dim = int(vectors.shape[1])
    try:
        client.recreate_collection(collection,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
    except Exception:
        pass
    points = [PointStruct(id=i, vector=vectors[i].tolist(), payload={
        "chunk_id": c["chunk_id"], "document_id": c["document_id"], "source_pdf": c["source_pdf"],
        "page_start": c["page_start"], "page_end": c["page_end"], "platform": c.get("platform", ""),
        "autosar_release": c.get("autosar_release", ""), "module": c.get("module", ""),
        "document_type": c.get("document_type", ""), "requirement_ids": c.get("requirement_ids", []),
        "api_names": c.get("api_names", []), "chunk_kind": c.get("chunk_kind", ""),
        "tenant_id": c.get("tenant_id", tenant_id), "project_id": c.get("project_id", ""),
        "workspace_id": c.get("workspace_id", ""), "vendor_scope": c.get("vendor_scope", "generic_autosar"),
        "data_classification": c.get("data_classification", "internal"),
        "artifact_type": c.get("artifact_type", "spec"),
        "text": (c.get("normalized_text") or "")[:4000]}) for i, c in enumerate(chunks)]
    for p in points:
        if not p.payload.get("tenant_id"):
            raise ValueError("tenant_id required on every vector point")
    client.upload_points(collection, points)
    return len(points)


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
    return client.search(collection_name=collection, query_vector=vector, query_filter=qfilter, limit=limit)
