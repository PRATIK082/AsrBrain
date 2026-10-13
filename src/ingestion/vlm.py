"""VLM diagram analysis (Phase 2 §15, P2). Local VLM by default; descriptions are
supplemental — every statement keeps original figure/page provenance and graph links
are confidence-scored, never authoritative facts.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class DiagramEvidence(BaseModel):
    evidence_id: str
    source_document: str = ""
    page: int = 0
    caption: str = ""
    ocr_text: str = ""
    vlm_description: str = ""
    linked_entities: list[dict] = Field(default_factory=list)
    is_inferred: bool = True
    provenance: dict = Field(default_factory=dict)


def analyze_diagram(image_path: str, caption: str = "", ocr_text: str = "",
                    page: int = 0, document_id: str = "",
                    local_vlm: object | None = None) -> DiagramEvidence:
    """Run local VLM (or deterministic fallback) and wrap output with provenance."""
    desc = ""
    if local_vlm is not None and hasattr(local_vlm, "describe"):
        desc = str(local_vlm.describe(image_path))
    else:
        desc = f"Diagram supplemental description pending local-VLM review. Caption: {caption or 'n/a'}."
    eid = f"fig-{abs(hash(image_path)) % 10**8:08d}"
    return DiagramEvidence(
        evidence_id=eid, source_document=document_id, page=page, caption=caption,
        ocr_text=ocr_text, vlm_description=desc, is_inferred=True,
        provenance={"image_path": image_path, "page": page, "document_id": document_id,
                    "caption": caption, "model": getattr(local_vlm, "model_name", "local-vlm-fallback"),
                    "note": "VLM output is supplemental; cite original figure for normative claims"})
