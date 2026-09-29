"""Canonical multimodal record (Part E). Text chunks remain the default; tables/figures
are supplemental evidence that always cite their source page — generated descriptions
never replace original evidence (is_inferred=True, uncitable alone)."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

Modality = Literal["text", "table", "figure", "diagram", "equation",
                   "requirement", "api", "configuration", "graph"]


class MultimodalEvidence(BaseModel):
    evidence_id: str
    document_id: str
    page_id: str = ""
    modality: Modality = "text"
    raw_content: str | None = None
    structured_content: dict | None = None
    image_path: str | None = None
    caption: str | None = None
    ocr_text: str | None = None
    autosar_release: str | None = None
    platform: str | None = None
    module: str | None = None
    chapter: str | None = None
    section: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    api_names: list[str] = Field(default_factory=list)
    source_pdf: str = ""
    printed_page: str | None = None
    pdf_page_index: int = 0
    quality_score: float = 1.0
    parent_evidence_id: str | None = None
    parser: str = ""
    parser_version: str = ""
    is_inferred: bool = False  # generated descriptions: supplemental only, never sole citation
