"""Canonical document model (spec §3). JSON-serialisable dataclasses; SQLite persistence in indexing."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    source_pdf: str
    source_sha256: str
    page_start: int
    page_end: int
    pdf_page_index: int
    printed_page_number: str = ""
    autosar_release: str = ""
    platform: str = ""          # Classic | Adaptive | Foundation | unknown
    module: str = ""            # CanIf, SOME-IP, ...
    document_type: str = ""     # SWS | PRS | RS | TPS | TR | unknown
    chapter_number: str = ""
    chapter_title: str = ""
    section_number: str = ""
    section_title: str = ""
    requirement_ids: list = field(default_factory=list)
    api_names: list = field(default_factory=list)
    ecu_parameters: list = field(default_factory=list)
    entity_tags: list = field(default_factory=list)
    parent_chunk_id: str = ""
    chunk_kind: str = "atomic"  # atomic | context | parent | summary
    text: str = ""
    normalized_text: str = ""
    table_data: Any = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def source_locator(self) -> str:
        return f"pdf://{self.document_id}/page/{self.page_start}"


@dataclass
class DocumentRecord:
    document_id: str
    source_pdf: str
    sha256: str
    title: str = ""
    autosar_release: str = ""
    platform: str = ""
    module: str = ""
    document_type: str = ""
    page_count: int = 0
    quality_score: float = 0.0
