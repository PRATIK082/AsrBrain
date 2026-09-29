"""Qdrant mirror (Phase 1 optional): dense+BM25 payloads with metadata filters (spec §11).

Requires qdrant-client + running Qdrant. Local HybridIndex remains the default;
this module is used by ops to push the same canonical chunks to Qdrant.
"""
from __future__ import annotations

COLLECTION_SCHEMA = {
    "vectors": {"size": 0, "distance": "Cosine"},  # size set at upload from local matrix width
    "payload": ["platform", "autosar_release", "module", "document_type",
                "page_start", "requirement_ids", "api_names", "chunk_kind", "document_id"],
}


def upload(chunks: list[dict], vectors, url: str, collection: str):
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
        "text": (c.get("normalized_text") or "")[:4000]}) for i, c in enumerate(chunks)]
    client.upload_points(collection, points)
    return len(points)
