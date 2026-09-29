"""Lightweight dependency graph from co-mention + API/requirement signals (spec §12, Phase-3 ready)."""
from __future__ import annotations
from ..schema.graph import GraphEdge

MODULES = ["CanIf", "CanDrv", "CanSM", "PduR", "Com", "SOME-IP", "ECUC", "Dcm", "Dem", "DoIP"]


def extract_edges(chunks: list[dict]) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    for c in chunks:
        text = c.get("normalized_text", "")
        present = [m for m in MODULES if m.lower() in text.lower()]
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                edges.append(GraphEdge(subject=present[i], predicate="co_mentioned_with",
                    object=present[j], source_chunk_id=c["chunk_id"],
                    source_evidence_id=c["chunk_id"],
                    source_pdf=c.get("source_pdf", ""), page=int(c.get("page_start") or 0),
                    release=c.get("autosar_release", ""), confidence=0.7, is_inferred=True))
        for api in c.get("api_names", [])[:5]:
            if present:
                edges.append(GraphEdge(subject=present[0], predicate="implements", object=api,
                    source_chunk_id=c["chunk_id"], source_evidence_id=c["chunk_id"],
                    source_pdf=c.get("source_pdf", ""),
                    page=int(c.get("page_start") or 0), release=c.get("autosar_release", ""),
                    confidence=0.9, is_inferred=False))
    return edges
