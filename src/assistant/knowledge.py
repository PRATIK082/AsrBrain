"""Assistant knowledge manifest, project overview and starter prompt library.

Everything is derived from the canonical store (SQLite) — never from a model —
so the assistant can describe its own knowledge honestly and the UI can show
grounded "what do you know about this project" information.

Design rules (docs/featureupdate.md §20, §23):
  * no invented metadata — every number here comes from a COUNT/SELECT;
  * read-only — this module never writes to the canonical store;
  * deterministic — same store, same answer.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from ..config.settings import settings

# Requirement identifiers look like `SWS_CanIf_00123` / `PRS_SOMEIP_00163`.
# The chunker also stores these in `api_names` (the API regex accepts any
# underscored token), so they are filtered out of the API facet to keep the
# entity views meaningful.
_REQ_ID = re.compile(r"^[A-Z][A-Za-z0-9]*_[A-Za-z0-9]+_\d+$")


def _is_requirement_id(value: str) -> bool:
    return bool(_REQ_ID.match(value or ""))

# --------------------------------------------------------------------------- #
# store access
# --------------------------------------------------------------------------- #


def _db_path(canonical_db: str | None = None) -> str:
    return canonical_db or settings.canonical_db


def _connect(canonical_db: str | None = None) -> sqlite3.Connection | None:
    path = _db_path(canonical_db)
    if not path or not Path(path).exists():
        return None
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
        return int(row["n"]) if row else 0
    except sqlite3.Error:
        return 0


def _json_list(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = json.loads(value)
        return [str(v) for v in parsed] if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


# --------------------------------------------------------------------------- #
# corpus manifest
# --------------------------------------------------------------------------- #


def corpus_manifest(canonical_db: str | None = None) -> dict:
    """Counts and facet values of the indexed corpus."""
    conn = _connect(canonical_db)
    if conn is None:
        return {
            "available": False,
            "canonical_db": _db_path(canonical_db),
            "documents": 0, "chunks": 0, "tables": 0, "figures": 0,
            "requirements": 0, "apis": 0, "ecu_parameters": 0,
            "releases": [], "platforms": [], "modules": [], "document_types": [],
        }

    requirement_ids: set[str] = set()
    api_names: set[str] = set()
    ecu_params: set[str] = set()
    for row in conn.execute(
        "SELECT requirement_ids, api_names, ecu_parameters FROM chunks"
    ).fetchall():
        requirement_ids.update(r for r in _json_list(row["requirement_ids"]) if _is_requirement_id(r))
        api_names.update(a for a in _json_list(row["api_names"]) if not _is_requirement_id(a))
        ecu_params.update(_json_list(row["ecu_parameters"]))

    def facet(column: str) -> list[str]:
        try:
            rows = conn.execute(
                f"SELECT DISTINCT {column} AS v FROM chunks WHERE {column} IS NOT NULL AND {column} != ''"
            ).fetchall()
            return sorted({r["v"] for r in rows})
        except sqlite3.Error:
            return []

    manifest = {
        "available": True,
        "canonical_db": _db_path(canonical_db),
        "documents": _count(conn, "documents"),
        "chunks": _count(conn, "chunks"),
        "tables": _count(conn, "tables"),
        "figures": _count(conn, "figures"),
        "requirements": len(requirement_ids),
        "apis": len(api_names),
        "ecu_parameters": len(ecu_params),
        "releases": facet("autosar_release"),
        "platforms": facet("platform"),
        "modules": facet("module"),
        "document_types": facet("document_type"),
    }
    conn.close()
    return manifest


# --------------------------------------------------------------------------- #
# capabilities
# --------------------------------------------------------------------------- #

_MODES = [
    {"id": "auto", "title": "Auto",
     "description": "Let the router pick the retrieval strategy from the question."},
    {"id": "exact_lookup", "title": "Exact lookup",
     "description": "Single authoritative answer for a named requirement, API or parameter."},
    {"id": "comparison", "title": "Comparison",
     "description": "Contrast two AUTOSAR releases or platforms side by side."},
    {"id": "troubleshooting", "title": "Troubleshooting",
     "description": "Work a reported symptom back to a spec statement and a check list."},
    {"id": "deep_explanation", "title": "Deep explanation",
     "description": "Explain a concept, its context and the surrounding concept flow."},
]

_SURFACES = [
    {"id": "chat", "title": "Assistant", "route": "/",
     "description": "Conversation with cited answers, visible retrieval steps and sources."},
    {"id": "arxml", "title": "ARXML Explorer", "route": "/arxml",
     "description": "Deterministic ARXML topology with XPath provenance."},
    {"id": "diff", "title": "Diff Studio", "route": "/diff",
     "description": "Evidence-aligned structural diff between two API sets."},
    {"id": "code", "title": "Code Review", "route": "/code",
     "description": "Advisory static checks; human approval required before any fix."},
    {"id": "diagrams", "title": "Diagram Studio", "route": "/diagrams",
     "description": "Render, analyse and recreate Mermaid/PDF diagrams."},
]


def capabilities(canonical_db: str | None = None) -> dict:
    """What the assistant can do and what it can be asked about."""
    manifest = corpus_manifest(canonical_db)
    return {
        "assistant": "AsrBrain",
        "kind": "citation-grounded AUTOSAR engineering assistant",
        "corpus": manifest,
        "modes": _MODES,
        "surfaces": _SURFACES,
        "guarantees": [
            "Every factual claim carries a source reference (document, page, section).",
            "Unverifiable questions abstain instead of guessing.",
            "Code findings are advisory — a human approves every change.",
            "Processing stays local unless an explicit provider is selected.",
            "Retrieval steps are shown, so the reasoning path is inspectable.",
        ],
        "ready": manifest.get("available", False) and manifest.get("chunks", 0) > 0,
    }


# --------------------------------------------------------------------------- #
# project overview
# --------------------------------------------------------------------------- #


def project_overview(canonical_db: str | None = None, flow_limit: int = 40) -> dict:
    """Project-level knowledge: what is indexed, and how the entities flow together.

    `concept_flow` is derived from co-occurrence inside a single chunk, so every
    entry can be traced back to one passage of one document.
    """
    conn = _connect(canonical_db)
    if conn is None:
        return {"available": False, "modules": [], "releases": [], "documents": [],
                "concept_flow": [], "entity_anchors": {"requirements": [], "apis": []}}

    documents = [
        {
            "document_id": r["document_id"],
            "source_pdf": r["source_pdf"],
            "title": r["title"] or r["source_pdf"],
            "release": r["autosar_release"] or "",
            "platform": r["platform"] or "",
            "module": r["module"] or "",
            "document_type": r["document_type"] or "",
            "pages": r["page_count"] or 0,
            "quality": r["quality"],
        }
        for r in conn.execute(
            "SELECT document_id, source_pdf, title, autosar_release, platform, module,"
            " document_type, page_count, quality FROM documents ORDER BY module, title"
        ).fetchall()
    ]

    module_rows = conn.execute(
        "SELECT COALESCE(module,'') AS m, COALESCE(autosar_release,'') AS r,"
        " COALESCE(platform,'') AS p, COUNT(*) AS n FROM chunks"
        " GROUP BY m, r, p ORDER BY n DESC"
    ).fetchall()

    modules: dict[str, dict] = {}
    for row in module_rows:
        name = row["m"] or "(unassigned)"
        entry = modules.setdefault(name, {
            "module": name, "chunks": 0, "releases": [], "platforms": [],
            "requirements": 0, "apis": 0, "document_types": [],
        })
        entry["chunks"] += int(row["n"])
        if row["r"] and row["r"] not in entry["releases"]:
            entry["releases"].append(row["r"])
        if row["p"] and row["p"] not in entry["platforms"]:
            entry["platforms"].append(row["p"])

    releases: dict[tuple[str, str], dict] = {}
    for row in module_rows:
        key = (row["r"] or "unknown", row["p"] or "unknown")
        entry = releases.setdefault(key, {"release": key[0], "platform": key[1], "chunks": 0})
        entry["chunks"] += int(row["n"])

    flow: list[dict] = []
    requirement_counts: dict[str, int] = {}
    api_counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT chunk_id, source_pdf, page_start, autosar_release, platform, module,"
        " section_number, section_title, requirement_ids, api_names FROM chunks"
    ).fetchall():
        reqs = [r for r in _json_list(row["requirement_ids"]) if _is_requirement_id(r)]
        apis = [a for a in _json_list(row["api_names"]) if not _is_requirement_id(a)]
        for r in reqs:
            requirement_counts[r] = requirement_counts.get(r, 0) + 1
        for a in apis:
            api_counts[a] = api_counts.get(a, 0) + 1
        if reqs and apis and len(flow) < flow_limit:
            flow.append({
                "module": row["module"] or "",
                "requirement": reqs[0],
                "api": apis[0],
                "source_pdf": row["source_pdf"],
                "page": row["page_start"],
                "section": f"{row['section_number'] or ''} {row['section_title'] or ''}".strip(),
                "release": row["autosar_release"] or "",
                "chunk_id": row["chunk_id"],
            })

    for name, entry in modules.items():
        req_n = api_n = 0
        for row in conn.execute(
            "SELECT requirement_ids, api_names FROM chunks WHERE COALESCE(module,'') = ?", (name,)
        ).fetchall():
            req_n += len([r for r in _json_list(row["requirement_ids"]) if _is_requirement_id(r)])
            api_n += len([a for a in _json_list(row["api_names"]) if not _is_requirement_id(a)])
        entry["requirements"] = req_n
        entry["apis"] = api_n

    top_requirements = sorted(requirement_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:25]
    top_apis = sorted(api_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:25]

    conn.close()
    return {
        "available": True,
        "corpus": corpus_manifest(canonical_db),
        "modules": sorted(modules.values(), key=lambda m: -m["chunks"]),
        "releases": sorted(releases.values(), key=lambda r: -r["chunks"]),
        "documents": documents,
        "concept_flow": flow,
        "entity_anchors": {
            "requirements": [{"id": rid, "mentions": n} for rid, n in top_requirements],
            "apis": [{"id": aid, "mentions": n} for aid, n in top_apis],
        },
    }


# --------------------------------------------------------------------------- #
# starter prompt library
# --------------------------------------------------------------------------- #


def starter_prompts(canonical_db: str | None = None) -> list[dict]:
    """Curated prompt library.

    The prompts are templated with the real module/release names of the indexed
    corpus so they always point at material the assistant can actually retrieve.
    """
    manifest = corpus_manifest(canonical_db)
    modules = manifest.get("modules") or ["Com"]
    releases = manifest.get("releases") or ["R22-11"]
    primary_module = modules[0]
    primary_release = releases[0]
    other_release = next((r for r in releases if r != primary_release), primary_release)

    return [
        {
            "group": "Understand the project",
            "icon": "flow",
            "prompts": [
                {
                    "title": f"Explain the {primary_module} concept flow",
                    "prompt": f"Explain the {primary_module} concept flow: which requirements, "
                              f"APIs and configuration values form the chain from a signal to the "
                              f"bus, and where does each step come from?",
                },
                {
                    "title": f"What is indexed for {primary_module}?",
                    "prompt": f"What do you know about {primary_module}? Summarise the concepts, "
                              f"the main APIs and the requirement identifiers that appear most often.",
                },
                {
                    "title": f"Map {primary_module} requirements to APIs",
                    "prompt": f"For the {primary_module} module, list the requirements and the "
                              f"API names that appear in the same sections, and cite the document "
                              f"and page for each pair.",
                },
            ],
        },
        {
            "group": "Track down a defect",
            "icon": "bug",
            "prompts": [
                {
                    "title": "Signal is never transmitted",
                    "prompt": "A signal is configured and the sending SWC runs, but the frame is "
                              "never transmitted. Which requirements and configuration values govern "
                              "this path, and what should I check first?",
                },
                {
                    "title": "Timeout on a periodic signal",
                    "prompt": "A periodic signal times out intermittently. What timing requirements "
                              "and timeout parameters apply, and what is the documented behaviour "
                              "when they are violated?",
                },
                {
                    "title": "Port is not connected",
                    "prompt": "A client port is not connected in the composition. Which requirements "
                              "define the connection and what is required to make it valid?",
                },
            ],
        },
        {
            "group": "Specification lookup",
            "icon": "book",
            "prompts": [
                {
                    "title": "Exact API behaviour",
                    "prompt": f"What is the exact behaviour of the {primary_module} main "
                              f"transmission API in {primary_release}? Quote the normative "
                              f"statements and cite the pages.",
                },
                {
                    "title": "Configuration parameter meaning",
                    "prompt": "What does the timeout configuration parameter mean, what unit does it "
                              "use, and what are the documented value ranges?",
                },
            ],
        },
        {
            "group": "Compare and assess impact",
            "icon": "compare",
            "prompts": [
                {
                    "title": f"{primary_release} vs {other_release}",
                    "prompt": f"What changed between {primary_release} and {other_release} for the "
                              f"modules you have indexed? Answer per release with citations.",
                },
                {
                    "title": "Impact of a configuration change",
                    "prompt": "If I change the main function period, which requirements, APIs and "
                              "modules are affected? List the impact chain with citations.",
                },
            ],
        },
    ]
