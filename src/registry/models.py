"""Typed records of the provenance-first registry (ADR-0002).

Every record carries its provenance: the artifact version it came from, the
source location, how it was extracted, how confident the extraction is and the
lifecycle state of the record. Nothing in this model is "just a string".
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AnswerabilityStatus = Literal[
    "VERIFIED",
    "EVIDENCE_SUPPORTED",
    "NEEDS_ENGINEER_REVIEW",
    "INSUFFICIENT_EVIDENCE",
]

ArtifactKind = Literal[
    "spec", "arxml", "source", "requirement_set", "test_report", "diagram", "external",
]

LocatorType = Literal[
    "pdf_page", "arxml_xpath", "source_symbol", "test_case", "row_range", "json_pointer",
]

ClaimType = Literal["fact", "interpretation", "assumption", "recommendation"]

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class _Base(BaseModel):
    model_config = {"extra": "forbid"}


class Project(_Base):
    id: str
    name: str
    description: str = ""
    owner: str = ""
    data_classification: str = "internal"
    access_policy: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class Workspace(_Base):
    id: str
    project_id: str
    name: str
    description: str = ""
    scope: str = ""
    created_at: str = ""
    updated_at: str = ""


class Artifact(_Base):
    id: str
    project_id: str
    workspace_id: str = ""
    kind: ArtifactKind = "external"
    name: str
    source_uri: str = ""
    content_hash: str = ""
    owner: str = ""
    branch: str = ""
    autosar_release: str = ""
    data_classification: str = "internal"
    access_policy: dict = Field(default_factory=dict)
    lifecycle_state: str = "active"
    created_at: str = ""
    updated_at: str = ""


class ArtifactVersion(_Base):
    id: str
    artifact_id: str
    version_label: str = ""
    content_hash: str = ""
    size_bytes: int = 0
    storage_uri: str = ""
    source_uri: str = ""
    extracted_at: str = ""
    extractor_name: str = ""
    extractor_version: str = ""
    extraction_confidence: float = 1.0
    metadata: dict = Field(default_factory=dict)
    lifecycle_state: str = "active"
    created_at: str = ""


class SourceLocation(_Base):
    id: str
    artifact_version_id: str
    locator_type: LocatorType
    locator: str
    page_start: int | None = None
    page_end: int | None = None
    section: str = ""
    line_start: int | None = None
    line_end: int | None = None
    release: str = ""
    module: str = ""
    snippet: str = ""
    chunk_id: str = ""
    created_at: str = ""


class Citation(_Base):
    id: str
    source_location_id: str
    answer_id: str = ""
    conversation_id: str = ""
    message_id: str = ""
    artifact_version_id: str = ""
    label: str = ""
    claim: str = ""
    created_at: str = ""


class EvidenceClaim(_Base):
    id: str
    claim: str
    answer_id: str = ""
    claim_type: ClaimType = "fact"
    status: AnswerabilityStatus = "EVIDENCE_SUPPORTED"
    reason: str = ""
    citation_ids: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    checked: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    created_at: str = ""


class ValidationResult(_Base):
    id: str
    artifact_version_id: str
    tool_name: str
    status: str = "unknown"
    severity: str = "info"
    message: str = ""
    details: dict = Field(default_factory=dict)
    created_at: str = ""


class Job(_Base):
    id: str
    kind: str
    payload: dict = Field(default_factory=dict)
    status: JobStatus = "queued"
    priority: int = 0
    attempts: int = 0
    max_attempts: int = 3
    project_id: str = ""
    workspace_id: str = ""
    artifact_version_id: str = ""
    error: str = ""
    result: dict = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    started_at: str = ""
    finished_at: str = ""


class AnswerAudit(_Base):
    id: str
    request_id: str = ""
    conversation_id: str = ""
    message_id: str = ""
    question: str = ""
    answer: str = ""
    answerability_status: str = ""
    project_id: str = ""
    scope: dict = Field(default_factory=dict)
    citations: list[dict] = Field(default_factory=list)
    tool_calls: list[dict] = Field(default_factory=list)
    model_provider: str = ""
    model_name: str = ""
    routing_reason: str = ""
    latency_ms: int = 0
    created_at: str = ""
