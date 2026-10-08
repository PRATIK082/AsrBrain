"""Code intelligence: advisory-only preflight + AST-light checks + traceability (Phase 2 §10).

Never outputs 'MISRA compliant / ISO 26262 certified'. All findings advisory unless
supplied by a configured external analyzer (ingested verbatim with provenance).
"""
from __future__ import annotations

import re
from pydantic import BaseModel, Field

DISCLAIMER = ("Advisory finding — requires configured static-analysis verification. "
              "Not a compliance determination.")

_PATTERNS = [
    ("dynamic-allocation", re.compile(r"\bmalloc\s*\(|\bcalloc\s*\(|\brealloc\s*\(|\bnew\s+"), "avoid dynamic allocation in safety code"),
    ("goto", re.compile(r"^\s*goto\s+\w+|[^a-zA-Z_]goto\s+\w+", re.M), "unstructured control flow"),
    ("unsafe-api", re.compile(r"\b(gets|strcpy|strcat|sprintf|system)\s*\("), "unsafe C library API"),
    ("suspicious-cast", re.compile(r"\(\s*(?:uint8_t|uint16_t|int)\s*\*\s*\)"), "suspicious pointer cast — review aliasing"),
    ("missing-memmap", re.compile(r"#include\s*[\"<](?!.*(?:MemMap|Compiler)\b)"), "include without MemMap/Compiler abstraction visible"),
]

_RTE_RE = re.compile(r"\bRte_(Read|Write|Call|Mode|Invalidate|Receive|Send)_\w+")
_FUNC_RE = re.compile(r"^[A-Za-z_]\w*\s+([A-Za-z_]\w*)\s*\(", re.M)


class CodeFinding(BaseModel):
    rule: str
    level: str = "advisory"  # informational|advisory|potential_violation|tool_reported|requires_review
    location: str = ""
    message: str = ""
    provenance: str = "asrbrain-preflight"
    is_compliance_claim: bool = False


class TraceabilityLink(BaseModel):
    link_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    link_type: str = "suspected_match"
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list)
    is_inferred: bool = True


def preflight_checks(source: str, path: str = "<input>") -> list[CodeFinding]:
    out: list[CodeFinding] = []
    for rule, rx, msg in _PATTERNS:
        for m in rx.finditer(source):
            line = source[:m.start()].count("\n") + 1
            out.append(CodeFinding(rule=rule, location=f"{path}:{line}",
                                   message=f"{msg} [{DISCLAIMER}]"))
    return out


def rte_call_sites(source: str) -> list[str]:
    return sorted(set(_RTE_RE.findall(source)) and [m.group(0) for m in _RTE_RE.finditer(source)])


def map_rte_to_arxml(calls: list[str], port_names: list[str]) -> list[TraceabilityLink]:
    links: list[TraceabilityLink] = []
    for c in calls:
        for p in port_names:
            if p and p.lower().replace(" ", "") in c.lower().replace("_", ""):
                links.append(TraceabilityLink(link_id=f"{c}->{p}", source_type="code", source_id=c,
                                              target_type="arxml", target_id=p, link_type="suspected_match",
                                              confidence=0.6, evidence=[f"name overlap: {c} ~ {p}"]))
    return links
