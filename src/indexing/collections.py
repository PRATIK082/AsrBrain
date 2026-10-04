"""Typed vector collections + payload contract (spec §8). Backend-agnostic (Qdrant or existing)."""
from __future__ import annotations

COLLECTIONS = ["text", "requirement", "api", "ecuc", "table", "image", "diagram", "equation"]

PAYLOAD_FIELDS = ["content_type", "document_id", "source_pdf", "page_index", "printed_page",
                  "release", "platform", "module", "section", "requirement_ids",
                  "api_names", "ecuc_names", "parent_content_id", "quality_score", "parser_name"]

# Exact keyword fields: no stemming, case-sensitive match (e.g. SWS_CANIF_00001, CanIf_Init).
EXACT_KEYWORD_FIELDS = ["requirement_ids", "api_names", "ecuc_names", "release", "platform", "module"]


def payload_for(c) -> dict:
    d = c.model_dump() if hasattr(c, "model_dump") else dict(c)
    return {
        "content_type": d.get("content_type"), "document_id": d.get("document_id"),
        "source_pdf": d.get("source_pdf"), "page_index": d.get("page_index"),
        "printed_page": d.get("printed_page"), "release": d.get("autosar_release"),
        "platform": d.get("platform"), "module": d.get("module"),
        "section": d.get("section"), "requirement_ids": d.get("requirement_ids", []),
        "api_names": d.get("api_names", []), "ecuc_names": d.get("ecu_parameters", []),
        "parent_content_id": d.get("parent_content_id"),
        "quality_score": d.get("quality_score", 1.0), "parser_name": d.get("parser_name")}


def collection_for(content_type: str) -> str:
    return content_type if content_type in COLLECTIONS else "text"
