"""Enterprise security: mandatory request context, RBAC, tenant isolation (Phase 2 §3, §13)."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


class SecurityContext(BaseModel):
    """Immutable per-request authorization scope. Server-derived only — never trust browser input."""

    user_id: str
    tenant_id: str
    project_id: str | None = None
    workspace_id: str | None = None
    roles: list[str] = Field(default_factory=list)
    allowed_vendor_scopes: list[str] = Field(default_factory=lambda: ["generic_autosar"])
    allowed_document_scopes: list[str] = Field(default_factory=list)
    data_classification: Literal["public", "internal", "confidential", "restricted"] = "internal"
    cloud_policy: Literal["local_only", "cloud_metadata_only", "cloud_redacted_only", "cloud_allowed"] = "local_only"
    allowed_model_providers: list[str] = Field(default_factory=lambda: ["ollama"])
    audit_request_id: str = ""


DEFAULT_CONTEXT = SecurityContext(user_id="local-operator", tenant_id="default",
                                  roles=["engineer"], audit_request_id="local")


def derive_context(user_id: str, tenant_id: str, roles: list[str] | None = None,
                   cloud_allowed: bool = False, **kw) -> SecurityContext:
    """Server-side derivation helper. `cloud_allowed` must come from tenant policy, not request."""
    return SecurityContext(user_id=user_id, tenant_id=tenant_id,
                           roles=roles or ["engineer"],
                           cloud_policy="cloud_allowed" if cloud_allowed else "local_only",
                           allowed_model_providers=["ollama"] if not cloud_allowed else ["ollama", "openai_compat"],
                           **kw)


def scope_filter(ctx: SecurityContext) -> dict:
    """Canonical payload filter every retrieval/graph/object-store query must apply."""
    f: dict = {"tenant_id": ctx.tenant_id}
    if ctx.project_id:
        f["project_id"] = ctx.project_id
    if ctx.workspace_id:
        f["workspace_id"] = ctx.workspace_id
    return f


def check_access(ctx: SecurityContext, resource_scope: dict) -> tuple[bool, str]:
    """Mandatory server-side check. Returns (allowed, reason). Default-deny on tenant mismatch."""
    if not ctx.tenant_id or not ctx.user_id:
        return False, "missing security context"
    if resource_scope.get("tenant_id") and resource_scope["tenant_id"] != ctx.tenant_id:
        return False, "cross-tenant access denied"
    if ctx.project_id and resource_scope.get("project_id") and resource_scope["project_id"] != ctx.project_id:
        return False, "project scope denied"
    vendor = resource_scope.get("vendor_scope")
    if vendor and vendor != "generic_autosar" and vendor not in ctx.allowed_vendor_scopes:
        return False, f"vendor scope '{vendor}' not authorized"
    return True, "allowed"


def require_access(ctx: SecurityContext, resource_scope: dict) -> None:
    from fastapi import HTTPException
    ok, reason = check_access(ctx, resource_scope)
    if not ok:
        raise HTTPException(status_code=403, detail=reason)
