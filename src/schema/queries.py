"""Typed query-understanding schema (spec §8)."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    original_query: str
    normalized_query: str = ""
    intent: Literal["definition", "api_lookup", "requirement_lookup", "configuration",
                    "comparison", "dependency", "architecture", "troubleshooting",
                    "sequence", "state_machine", "deep_explanation", "unknown"] = "unknown"
    platforms: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    releases: list[str] = Field(default_factory=list)
    release_mode: Literal["none", "exact", "family", "comparison", "range", "latest"] = "none"
    document_types: list[str] = Field(default_factory=list)
    api_names: list[str] = Field(default_factory=list)
    requirement_ids: list[str] = Field(default_factory=list)
    configuration_parameters: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_evidence: list[str] = Field(default_factory=list)
    needs_graph_search: bool = False
    needs_comparison_table: bool = False
    confidence: float = 0.0


class ClaimVerdict(BaseModel):
    claim: str
    supported: bool
    support_score: float = 0.0
    evidence_ids: list[str] = Field(default_factory=list)
    version_consistent: bool = True
    platform_consistent: bool = True
    citation_valid: bool = True
    risk: Literal["low", "medium", "high"] = "low"
