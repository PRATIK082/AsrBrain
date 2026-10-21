"""Scope-first retrieval (Phase 5).

Filters are applied **before** anything is scored, so a chunk that is out of
scope can never be ranked into the answer. The rules that decide the scope
come first; retrieval only runs inside it.

Two honesty rules shape this module:

* **Nothing is dropped silently.** Every filter reports how many chunks it
  removed and why.
* **A filter that cannot be applied says so.** The canonical chunk rows carry
  release, platform, module and document type — they do not carry a project,
  branch, ECU or vendor. A scope that names one of those is reported as
  *unapplied* rather than silently ignored, because a filter that appears to
  work but does not is worse than no filter at all.
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["Scope", "ScopeResult", "apply_scope", "scope_from_dict"]


@dataclass
class Scope:
    """The scope of a question: what the answer is allowed to draw from."""

    project_id: str = ""
    branch: str = ""
    ecu: str = ""
    vendor: str = ""
    tenant_id: str = ""
    releases: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    document_types: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    artifact_versions: list[str] = field(default_factory=list)
    access_policy: dict = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not any([
            self.project_id, self.branch, self.ecu, self.vendor, self.tenant_id,
            self.releases, self.platforms, self.modules, self.document_types,
            self.source_types, self.artifact_versions, self.access_policy,
        ])


@dataclass
class ScopeResult:
    """The outcome of applying a scope, including what could not be applied."""

    kept: list[dict]
    dropped: dict = field(default_factory=dict)
    unapplied: list[str] = field(default_factory=list)
    scope: dict = field(default_factory=dict)
    total: int = 0

    def to_dict(self) -> dict:
        return {
            "kept": len(self.kept),
            "dropped": dict(self.dropped),
            "dropped_total": sum(self.dropped.values()),
            "unapplied": list(self.unapplied),
            "scope": dict(self.scope),
            "total": self.total,
        }


def scope_from_dict(data: dict | None) -> Scope:
    """Build a scope from a plain dict (an API request body, a slot set)."""
    data = data or {}
    return Scope(
        project_id=str(data.get("project_id") or ""),
        branch=str(data.get("branch") or ""),
        ecu=str(data.get("ecu") or ""),
        vendor=str(data.get("vendor") or ""),
        tenant_id=str(data.get("tenant_id") or ""),
        releases=[str(r) for r in (data.get("releases") or [])],
        platforms=[str(p) for p in (data.get("platforms") or [])],
        modules=[str(m) for m in (data.get("modules") or [])],
        document_types=[str(d) for d in (data.get("document_types") or [])],
        source_types=[str(s) for s in (data.get("source_types") or [])],
        artifact_versions=[str(a) for a in (data.get("artifact_versions") or [])],
        access_policy=dict(data.get("access_policy") or {}),
    )


def _keep(chunk: dict, key: str, wanted: list[str]) -> bool:
    if not wanted:
        return True
    value = str(chunk.get(key) or "")
    return value in wanted


def apply_scope(chunks: list[dict], scope: Scope | dict | None) -> ScopeResult:
    """Filter the corpus by scope and report exactly what happened."""
    if isinstance(scope, dict):
        scope = scope_from_dict(scope)
    total = len(chunks)
    echo = {
        "project_id": scope.project_id,
        "branch": scope.branch,
        "ecu": scope.ecu,
        "vendor": scope.vendor,
        "tenant_id": scope.tenant_id,
        "releases": list(scope.releases),
        "platforms": list(scope.platforms),
        "modules": list(scope.modules),
        "document_types": list(scope.document_types),
        "source_types": list(scope.source_types),
        "artifact_versions": list(scope.artifact_versions),
    }
    if scope is None or scope.is_empty():
        return ScopeResult(kept=list(chunks), dropped={}, unapplied=[], scope=echo, total=total)

    dropped: dict[str, int] = {}
    unapplied: list[str] = []
    kept: list[dict] = []

    for chunk in chunks:
        reasons: list[str] = []
        if scope.releases and not _keep(chunk, "autosar_release", scope.releases):
            reasons.append("release")
        if scope.platforms and not _keep(chunk, "platform", scope.platforms):
            reasons.append("platform")
        if scope.modules and not _keep(chunk, "module", scope.modules):
            reasons.append("module")
        if scope.document_types and not _keep(chunk, "document_type", scope.document_types):
            reasons.append("document_type")
        if reasons:
            for reason in reasons:
                dropped[reason] = dropped.get(reason, 0) + 1
            continue
        kept.append(chunk)

    # Filters the corpus rows cannot express.
    for name, requested in (("project_id", scope.project_id),
                             ("branch", scope.branch),
                             ("ecu", scope.ecu),
                             ("vendor", scope.vendor),
                             ("tenant_id", scope.tenant_id),
                             ("source_types", scope.source_types),
                             ("artifact_versions", scope.artifact_versions)):
        if requested:
            unapplied.append(name)

    return ScopeResult(kept=kept, dropped=dropped, unapplied=unapplied,
                       scope=echo, total=total)
