"""Canonical multimodal data model (spec §3). Additive; existing Chunk/MultimodalEvidence untouched."""
from __future__ import annotations
import hashlib
from typing import Literal
from pydantic import BaseModel, Field

ContentType = Literal["text", "requirement", "api", "configuration", "table",
                      "image", "diagram", "equation", "audio", "video", "graph"]


class CanonicalContent(BaseModel):
    content_id: str
    document_id: str
    content_type: ContentType
    raw_text: str | None = None
    structured_data: dict | None = None
    source_pdf: str = ""
    source_sha256: str = ""
    page_index: int | None = None
    printed_page: str | None = None
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    autosar_release: str | None = None
    platform: str | None = None
    module: str | None = None
    document_type: str | None = None
    requirement_ids: list[str] = Field(default_factory=list)
    api_names: list[str] = Field(default_factory=list)
    ecu_parameters: list[str] = Field(default_factory=list)
    image_path: str | None = None
    table_html: str | None = None
    table_markdown: str | None = None
    equation_latex: str | None = None
    caption: str | None = None
    ocr_text: str | None = None
    generated_description: str | None = None  # supplementary only, never authoritative
    parent_content_id: str | None = None
    related_content_ids: list[str] = Field(default_factory=list)
    parser_name: str | None = None
    parser_version: str | None = None
    quality_score: float = 1.0
    requires_review: bool = False

    def provenance(self) -> dict:
        return {"source_content_id": self.content_id, "source_pdf": self.source_pdf,
                "page_index": self.page_index, "section": self.section,
                "release": self.autosar_release, "platform": self.platform}


def make_content_id(document_id: str, kind: str, page: int, n: int, text: str = "") -> str:
    h = hashlib.sha256(f"{document_id}|{kind}|{page}|{n}|{text[:200]}".encode()).hexdigest()[:12]
    return f"{kind}-{document_id}-{page}-{n}-{h}"


def from_chunk(c) -> "CanonicalContent":
    """Convert legacy Chunk dataclass → CanonicalContent (text default; requirement if IDs)."""
    d = c.to_dict() if hasattr(c, "to_dict") else dict(c)
    is_req = bool(d.get("requirement_ids"))
    return CanonicalContent(
        content_id=d.get("chunk_id", ""), document_id=d.get("document_id", ""),
        content_type="requirement" if is_req else "text",
        raw_text=d.get("text"), structured_data=None,
        source_pdf=d.get("source_pdf", ""), source_sha256=d.get("source_sha256", ""),
        page_index=d.get("pdf_page_index"), printed_page=d.get("printed_page_number") or None,
        chapter=d.get("chapter_title") or None, section=d.get("section_number") or None,
        subsection=None, autosar_release=d.get("autosar_release") or None,
        platform=d.get("platform") or None, module=d.get("module") or None,
        document_type=d.get("document_type") or None,
        requirement_ids=list(d.get("requirement_ids") or []),
        api_names=list(d.get("api_names") or []),
        ecu_parameters=list(d.get("ecu_parameters") or []),
        parent_content_id=d.get("parent_chunk_id") or None,
        parser_name="legacy-chunking", quality_score=1.0)
