"""Requirements intelligence (Phase 6).

Requirements arrive from many places — a CSV export from a requirement tool, a
JSON feed, a spreadsheet — and every source spells the same fields
differently. This module **normalises** them into one shape and records where
each field came from.

Two rules shape the module:

* **A machine may propose a trace link; only a human can approve it.** Every
  link carries a review state: `proposed`, `machine-extracted`, `reviewed`,
  `approved`, `rejected`.
* **Nothing here asserts compliance.** A requirement that has a test case has
  *evidence available for review* — it is not "ISO 26262 compliant", and the
  coverage report never says it is.
"""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from typing import Iterable

__all__ = [
    "LINK_REVIEW_STATES",
    "Requirement",
    "REVIEW_STATES",
    "ingest_requirements_csv",
    "ingest_requirements_json",
    "normalise_requirement",
]

#: The review state of a trace link.
LINK_REVIEW_STATES = ("proposed", "machine-extracted", "reviewed", "approved", "rejected")

#: The review state of a requirement itself.
REVIEW_STATES = ("machine-extracted", "reviewed", "approved", "rejected")

_ID_CLEAN = re.compile(r"[^A-Za-z0-9_.-]+")

#: Field aliases seen in the wild. The first match wins.
_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("id", "requirement_id", "requirementid", "req_id", "reqid", "key", "name"),
    "title": ("title", "name", "summary", "subject", "requirement", "description"),
    "revision": ("revision", "rev", "version", "rel", "release"),
    "status": ("status", "state", "lifecycle"),
    "source": ("source", "origin", "document", "source_document"),
    "parent_id": ("parent_id", "parentid", "parent", "parent_req",
                  "parent_requirement", "parent_requirement_id"),
    "verification_method": ("verification_method", "verification", "vm",
                            "verification_technique", "test_method"),
    "module": ("module", "subsystem", "component", "ecuc_module"),
    "autosar_release": ("autosar_release", "release", "autosar", "spec_release"),
    "description": ("description", "text", "detail", "details", "body"),
}

#: Status words that mean the same thing.
_STATUS_ALIASES = {
    "open": "open", "new": "open", "draft": "draft", "in progress": "in-progress",
    "in-progress": "in-progress", "inprogress": "in-progress",
    "implemented": "implemented", "done": "implemented", "complete": "implemented",
    "completed": "implemented", "closed": "implemented",
    "approved": "approved", "released": "approved", "verified": "approved",
    "rejected": "rejected", "obsolete": "rejected", "deprecated": "rejected",
}


@dataclass
class Requirement:
    """A normalised requirement."""

    id: str
    title: str = ""
    revision: str = ""
    status: str = ""
    source: str = ""
    parent_id: str = ""
    verification_method: str = ""
    module: str = ""
    autosar_release: str = ""
    description: str = ""
    project_id: str = ""
    artifact_version_id: str = ""
    review_state: str = "machine-extracted"
    properties: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "revision": self.revision,
            "status": self.status,
            "source": self.source,
            "parent_id": self.parent_id,
            "verification_method": self.verification_method,
            "module": self.module,
            "autosar_release": self.autosar_release,
            "description": self.description,
            "project_id": self.project_id,
            "artifact_version_id": self.artifact_version_id,
            "review_state": self.review_state,
            "properties": self.properties,
        }


def _pick(row: dict, field_name: str) -> str:
    for alias in _ALIASES[field_name]:
        if alias in row and row[alias] not in (None, ""):
            return str(row[alias]).strip()
    return ""


def _clean_id(value: str) -> str:
    """Normalise an identifier without changing its meaning."""
    value = (value or "").strip()
    value = _ID_CLEAN.sub("_", value)
    return value.strip("_")


def _normalise_status(value: str) -> str:
    key = (value or "").strip().lower()
    return _STATUS_ALIASES.get(key, key)


def normalise_requirement(row: dict, project_id: str = "",
                          artifact_version_id: str = "") -> Requirement:
    """Normalise one raw requirement row.

    Unknown columns are kept in `properties` — nothing from the source is
    thrown away silently.
    """
    known = {alias for aliases in _ALIASES.values() for alias in aliases}
    extra = {k: v for k, v in row.items() if k not in known and k not in ("artifact_version_id",)}

    requirement_id = _clean_id(_pick(row, "id"))
    title = _pick(row, "title")
    if title == requirement_id:
        title = ""
    return Requirement(
        id=requirement_id,
        title=title,
        revision=_pick(row, "revision"),
        status=_normalise_status(_pick(row, "status")),
        source=_pick(row, "source"),
        parent_id=_clean_id(_pick(row, "parent_id")),
        verification_method=_pick(row, "verification_method"),
        module=_pick(row, "module"),
        autosar_release=_pick(row, "autosar_release"),
        description=_pick(row, "description"),
        project_id=project_id,
        artifact_version_id=artifact_version_id or str(row.get("artifact_version_id") or ""),
        review_state=str(row.get("review_state") or "machine-extracted"),
        properties=extra,
    )


def ingest_requirements_csv(text: str, project_id: str = "",
                             artifact_version_id: str = "") -> list[Requirement]:
    """Read requirements from CSV text. A row without an id is skipped."""
    reader = csv.DictReader(io.StringIO(text))
    out: list[Requirement] = []
    for row in reader:
        if not any((v or "").strip() for v in row.values()):
            continue
        requirement = normalise_requirement(row, project_id, artifact_version_id)
        if requirement.id:
            out.append(requirement)
    return out


def ingest_requirements_json(text: str, project_id: str = "",
                              artifact_version_id: str = "") -> list[Requirement]:
    """Read requirements from JSON (a list, or an object with a `requirements` key)."""
    data = json.loads(text or "[]")
    if isinstance(data, dict):
        data = data.get("requirements") or data.get("items") or []
    out: list[Requirement] = []
    for row in data or []:
        if not isinstance(row, dict):
            continue
        requirement = normalise_requirement(row, project_id, artifact_version_id)
        if requirement.id:
            out.append(requirement)
    return out


def ingest_requirements(rows: Iterable[dict], project_id: str = "",
                        artifact_version_id: str = "") -> list[Requirement]:
    """Normalise a list of raw dicts."""
    out: list[Requirement] = []
    for row in rows:
        requirement = normalise_requirement(row, project_id, artifact_version_id)
        if requirement.id:
            out.append(requirement)
    return out
