"""Extended multimodal KG vocabulary + provenance (spec §7). Existing GraphEdge retained."""
from __future__ import annotations
from pydantic import BaseModel

NODES = ["document", "release", "platform", "module", "chapter", "section", "subsection",
         "requirement", "api", "ecuc_parameter", "table", "image", "diagram",
         "equation", "interface", "error_code", "state", "event"]

RELATIONS = ["contains", "belongs_to", "available_in", "defined_in", "depends_on",
             "interacts_with", "routes_through", "configured_by", "satisfies",
             "references", "has_table", "has_image", "has_diagram", "explains",
             "precedes", "transitions_to", "differs_from", "supported_by"]


class Provenance(BaseModel):
    source_content_id: str = ""
    source_pdf: str = ""
    page_index: int = 0
    section: str = ""
    release: str = ""
    platform: str = ""
    confidence: float = 0.8
    is_inferred: bool = False  # inferred: visible + never normative alone


class TypedEdge(BaseModel):
    subject: str
    subject_type: str = "api"
    predicate: str = "references"
    object: str = ""
    object_type: str = "requirement"
    provenance: Provenance = Provenance()

    def model_valid(self) -> bool:
        return self.subject_type in NODES and self.object_type in NODES and self.predicate in RELATIONS
