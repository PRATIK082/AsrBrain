"""Typed ARXML engineering model (Phase 2 §5). Deterministic parse-first; RAG only explains."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class ArxmlArtifact(BaseModel):
    artifact_id: str
    source_path: str
    source_sha256: str
    autosar_schema_version: str | None = None
    autosar_release: str | None = None
    project_scope: str = ""
    tenant_id: str = "default"
    parse_status: str = "ok"
    validation_warnings: list[str] = Field(default_factory=list)


class SoftwareComponent(BaseModel):
    uuid: str | None = None
    short_name: str
    qualified_name: str
    component_type: str
    package_path: str
    ports: list[str] = Field(default_factory=list)
    runnables: list[str] = Field(default_factory=list)
    internal_behaviors: list[str] = Field(default_factory=list)
    source_artifact_id: str = ""
    source_xpath: str = ""


class Port(BaseModel):
    uuid: str | None = None
    short_name: str
    qualified_name: str
    direction: Literal["P", "R", "PR"] = "R"
    interface_ref: str | None = None
    interface_type: str | None = None
    comspec: dict = Field(default_factory=dict)
    component_ref: str = ""
    source_artifact_id: str = ""
    source_xpath: str = ""


class PortInterface(BaseModel):
    uuid: str | None = None
    short_name: str
    qualified_name: str
    interface_type: Literal["sender_receiver", "client_server", "mode_switch",
                            "parameter", "nv_data", "trigger", "unknown"] = "unknown"
    data_elements: list[dict] = Field(default_factory=list)
    operations: list[dict] = Field(default_factory=list)
    source_artifact_id: str = ""
    source_xpath: str = ""


class RteConnector(BaseModel):
    connector_type: Literal["assembly", "delegation", "unknown"] = "unknown"
    provider_component_ref: str | None = None
    provider_port_ref: str | None = None
    requester_component_ref: str | None = None
    requester_port_ref: str | None = None
    composition_ref: str | None = None
    source_artifact_id: str = ""
    source_xpath: str = ""


class RunnableEntity(BaseModel):
    short_name: str
    qualified_name: str
    symbol: str | None = None
    events: list[str] = Field(default_factory=list)
    data_accesses: list[dict] = Field(default_factory=list)
    server_call_points: list[dict] = Field(default_factory=list)
    source_artifact_id: str = ""
    source_xpath: str = ""


class EcucParameter(BaseModel):
    short_name: str
    qualified_path: str
    definition_ref: str | None = None
    value_type: str | None = None
    value: str | int | float | bool | None = None
    reference_target: str | None = None
    container_path: str = ""
    source_artifact_id: str = ""
    source_xpath: str = ""


class ArxmlTopology(BaseModel):
    artifact: ArxmlArtifact
    components: list[SoftwareComponent] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    interfaces: list[PortInterface] = Field(default_factory=list)
    connectors: list[RteConnector] = Field(default_factory=list)
    runnables: list[RunnableEntity] = Field(default_factory=list)
    ecuc_parameters: list[EcucParameter] = Field(default_factory=list)
    unresolved_refs: list[dict] = Field(default_factory=list)
