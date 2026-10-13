"""OpenSearch document/field-level security helpers (Phase 2 §13).

Reads enforce DLS/FLS server-side; writes require separate authorization.
Client-supplied filters can never widen server scope.
"""
from __future__ import annotations


def build_security_filter(ctx) -> dict:
    tenant = getattr(ctx, "tenant_id", "") if not isinstance(ctx, dict) else ctx.get("tenant_id", "")
    if not tenant:
        raise PermissionError("mandatory tenant scope missing — OpenSearch query denied")
    must = [{"term": {"tenant_id": tenant}}]
    proj = getattr(ctx, "project_id", None) if not isinstance(ctx, dict) else ctx.get("project_id")
    ws = getattr(ctx, "workspace_id", None) if not isinstance(ctx, dict) else ctx.get("workspace_id")
    if proj:
        must.append({"term": {"project_id": proj}})
    if ws:
        must.append({"term": {"workspace_id": ws}})
    scopes = getattr(ctx, "allowed_vendor_scopes", []) if not isinstance(ctx, dict) else ctx.get("allowed_vendor_scopes", [])
    if scopes:
        must.append({"terms": {"vendor_scope": list(scopes) + ["generic_autosar"]}})
    return {"bool": {"filter": must}}


def secure_search_body(ctx, user_query: dict, size: int = 10) -> dict:
    """Merge user query under mandatory security filter. Tenant clause always wins."""
    sec = build_security_filter(ctx)
    q = (user_query or {}).get("query", {"match_all": {}})
    return {"size": size, "query": {"bool": {"must": [q], "filter": sec["bool"]["filter"]}}}


def check_write_authorized(ctx, doc_tenant: str) -> None:
    tenant = getattr(ctx, "tenant_id", "") if not isinstance(ctx, dict) else ctx.get("tenant_id", "")
    if not tenant or doc_tenant != tenant:
        raise PermissionError("cross-tenant write denied (DLS covers reads only; writes separately enforced)")
