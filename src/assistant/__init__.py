"""Institutional assistant services.

`knowledge` — the assistant's self-description: what it knows (corpus manifest),
the project overview, and the curated prompt library.
`triage` — evidence-grounded issue diagnosis.

Both modules are deterministic and read-only: the assistant describes its own
knowledge from the canonical store instead of claiming capabilities it cannot
back with indexed evidence.
"""
from __future__ import annotations

from .knowledge import capabilities, project_overview, starter_prompts
from .triage import diagnose, triage_categories

__all__ = [
    "capabilities",
    "project_overview",
    "starter_prompts",
    "diagnose",
    "triage_categories",
]
