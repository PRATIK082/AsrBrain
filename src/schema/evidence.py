"""Shared evidence contract for retrieval, API, and UI (Slice 2)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class EvidenceItem:
    evidence_id: str
    document_id: str
    source_pdf: str
    page_start: int | None = None
    page_end: int | None = None
    pdf_page_index: int | None = None
    printed_page_number: str = ""
    char_start: int | None = None
    char_end: int | None = None
    section_number: str = ""
    section_title: str = ""
    chapter_number: str = ""
    chapter_title: str = ""
    autosar_release: str = ""
    platform: str = ""
    module: str = ""
    document_type: str = ""
    requirement_ids: list = field(default_factory=list)
    api_names: list = field(default_factory=list)
    ecu_parameters: list = field(default_factory=list)
    source_sha256: str = ""
    text: str = ""
    compressed_text: str = ""
    fused_score: float | None = None
    rerank_score: float | None = None
    exact_hit: bool = False
    rank: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_evidence(chunk: dict, rank: int | None = None) -> dict:
    item = EvidenceItem(
        evidence_id=chunk.get("chunk_id", ""),
        document_id=chunk.get("document_id", ""),
        source_pdf=chunk.get("source_pdf", ""),
        page_start=chunk.get("page_start"),
        page_end=chunk.get("page_end"),
        pdf_page_index=chunk.get("pdf_page_index"),
        printed_page_number=chunk.get("printed_page_number", "") or "",
        char_start=chunk.get("char_start"),
        char_end=chunk.get("char_end"),
        section_number=chunk.get("section_number", "") or "",
        section_title=chunk.get("section_title", "") or "",
        chapter_number=chunk.get("chapter_number", "") or "",
        chapter_title=chunk.get("chapter_title", "") or "",
        autosar_release=chunk.get("autosar_release", "") or "",
        platform=chunk.get("platform", "") or "",
        module=chunk.get("module", "") or "",
        document_type=chunk.get("document_type", "") or "",
        requirement_ids=list(chunk.get("requirement_ids") or []),
        api_names=list(chunk.get("api_names") or []),
        ecu_parameters=list(chunk.get("ecu_parameters") or []),
        source_sha256=chunk.get("source_sha256", "") or "",
        text=chunk.get("text", "") or chunk.get("normalized_text", "") or "",
        compressed_text=chunk.get("compressed", "") or "",
        fused_score=chunk.get("fused_score"),
        rerank_score=chunk.get("rerank_score"),
        exact_hit=bool(chunk.get("exact_hit", False)),
        rank=rank,
    )
    return item.to_dict()
