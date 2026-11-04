"""Role and permission definitions for Slice 1."""
from __future__ import annotations

ROLES = ("owner", "admin", "member", "viewer")

PERMISSIONS = {
    "workspace.read": {"owner", "admin", "member", "viewer"},
    "workspace.manage": {"owner"},
    "members.manage": {"owner", "admin"},
    "collection.create": {"owner", "admin", "member"},
    "collection.read": {"owner", "admin", "member", "viewer"},
    "collection.update": {"owner", "admin", "member"},
    "collection.delete": {"owner", "admin"},
    "document.upload": {"owner", "admin", "member"},
    "document.read": {"owner", "admin", "member", "viewer"},
    "document.delete": {"owner", "admin"},
    "conversation.create": {"owner", "admin", "member"},
    "conversation.read": {"owner", "admin", "member", "viewer"},
    "conversation.share": {"owner", "admin", "member"},
    "audit.read": {"owner", "admin"},
}


def has_permission(role: str, permission: str) -> bool:
    allowed = PERMISSIONS.get(permission, set())
    return role in allowed


def require_role(role: str, permission: str) -> None:
    if not has_permission(role, permission):
        raise PermissionError(f"role {role!r} lacks permission {permission!r}")
