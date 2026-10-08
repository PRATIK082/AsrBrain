"""Typed vector collections + payload contract (spec §8). Backend-agnostic (Qdrant or existing)."""
from __future__ import annotations

COLLECTIONS = ["text", "requirement", "api", "ecuc", "table", "image", "diagram", "equation"]

PAYLOAD_FIELDS = ["content_type", "document_id", "source_pdf", "page_index", "printed_page",
                  "release", "platform", "module", "section", "requirement_ids",
                  "api_names", "ecuc_names", "parent_content_id", "quality_score", "parser_name",
                  "tenant_id", "project_id", "workspace_id", "vendor_scope", "data_classification",
                  "artifact_type", "security_labels"]

# Exact keyword fields: no stemming, case-sensitive match (e.g. SWS_CANIF_00001, CanIf_Init).
EXACT_KEYWORD_FIELDS = ["requirement_ids", "api_names", "ecuc_names", "release", "platform", "module",
                        "tenant_id", "project_id", "workspace_id", "vendor_scope"]


def payload_for(c, tenant_id: str = "default", project_id: str = "",
                workspace_id: str = "", vendor_scope: str = "generic_autosar",
                data_classification: str = "internal", artifact_type: str = "spec") -> dict:
    d = c.model_dump() if hasattr(c, "model_dump") else dict(c)
    return {
        "content_type": d.get("content_type"), "document_id": d.get("document_id"),
        "source_pdf": d.get("source_pdf"), "page_index": d.get("page_index"),
        "printed_page": d.get("printed_page"), "release": d.get("autosar_release"),
        "platform": d.get("platform"), "module": d.get("module"),
        "section": d.get("section"), "requirement_ids": d.get("requirement_ids", []),
        "api_names": d.get("api_names", []), "ecuc_names": d.get("ecu_parameters", []),
        "parent_content_id": d.get("parent_content_id"),
        "quality_score": d.get("quality_score", 1.0), "parser_name": d.get("parser_name"),
        "tenant_id": d.get("tenant_id", tenant_id), "project_id": d.get("project_id", project_id),
        "workspace_id": d.get("workspace_id", workspace_id),
        "vendor_scope": d.get("vendor_scope", vendor_scope),
        "data_classification": d.get("data_classification", data_classification),
        "artifact_type": d.get("artifact_type", artifact_type),
        "security_labels": d.get("security_labels", [])}


def collection_for(content_type: str) -> str:
    return content_type if content_type in COLLECTIONS else "text"
