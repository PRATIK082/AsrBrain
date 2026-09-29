"""Graph edge with provenance + inference flag (Part J). Additive over previous schema."""
from __future__ import annotations
from pydantic import BaseModel, Field


class GraphEdge(BaseModel):
    subject: str
    predicate: str
    object: str
    source_chunk_id: str = ""
    source_evidence_id: str = ""   # multimodal evidence id (== chunk id for text)
    source_pdf: str = ""
    page: int = 0
    release: str = ""
    confidence: float = 0.8
    is_inferred: bool = False      # inferred edges are never authoritative alone
