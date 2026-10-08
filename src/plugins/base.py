"""Vendor plugin contract + registry (Phase 2 §12). No proprietary knowledge in generic layer."""
from __future__ import annotations

from typing import Protocol
from src.security.context import SecurityContext


class VendorPlugin(Protocol):
    plugin_id: str
    display_name: str
    supported_platforms: list[str]

    def detect(self, artifact_metadata: dict) -> float: ...
    def enrich_arxml(self, entities: list[dict], context: SecurityContext) -> list[dict]: ...
    def enrich_code(self, code_metadata: dict, context: SecurityContext) -> dict: ...
    def provide_search_synonyms(self) -> dict: ...
    def provide_rules(self) -> list[dict]: ...
    def provide_ui_extensions(self) -> list[dict]: ...


class PluginRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, VendorPlugin] = {}
        self._enabled: dict[str, set[str]] = {}  # plugin_id -> set of "tenant/project"

    def register(self, plugin: VendorPlugin) -> None:
        self._plugins[plugin.plugin_id] = plugin

    def enable(self, plugin_id: str, tenant_id: str, project_id: str = "*") -> None:
        self._enabled.setdefault(plugin_id, set()).add(f"{tenant_id}/{project_id}")

    def is_enabled(self, plugin_id: str, ctx: SecurityContext) -> bool:
        scopes = self._enabled.get(plugin_id, set())
        return f"{ctx.tenant_id}/*" in scopes or f"{ctx.tenant_id}/{ctx.project_id}" in scopes

    def active_for(self, ctx: SecurityContext) -> list[VendorPlugin]:
        return [p for pid, p in self._plugins.items()
                if pid in ctx.allowed_vendor_scopes or self.is_enabled(pid, ctx)]


REGISTRY = PluginRegistry()
