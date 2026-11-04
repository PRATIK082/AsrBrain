"""Deployment profile loading and layered defaults."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .settings import settings


def _profile_path(name: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    return root / "config" / "profiles" / f"{name}.json"


def load_profile(name: str | None = None) -> dict[str, Any]:
    profile = name or settings.deployment_profile
    if profile not in {"workstation", "onprem-server", "cloud-saas"}:
        profile = "workstation"
    path = _profile_path(profile)
    if not path.exists():
        return {"profile": profile, "defaults": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"profile": profile, "defaults": {}}


def profile_defaults(name: str | None = None) -> dict[str, Any]:
    return load_profile(name).get("defaults", {}) or {}