"""Deterministic ARXML validation (ADR-0005).

The rule this module enforces: **"validated" is a claim, and a claim needs
evidence.** The validator therefore never says "the ARXML is fine" — it returns
a `ValidationResult` payload listing every check that ran, every finding with a
severity, and the file/line where the finding was observed.

If the document could not be parsed, the result says so and no structural
check is claimed.
"""
from __future__ import annotations

__all__ = ["validate_arxml", "validation_summary"]

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _finding(check: str, severity: str, message: str, **locator) -> dict:
    return {"check": check, "severity": severity, "message": message, **locator}


def validate_arxml(topology) -> dict:
    """Validate a parsed ARXML topology.

    Returns a `ValidationResult`-shaped dict:
    `{tool, status, severity, message, checks[], findings[], artifact, scope}`.
    """
    artifact = getattr(topology, "artifact", None)
    checks: list[dict] = []
    findings: list[dict] = []

    parse_status = getattr(artifact, "parse_status", "ok") if artifact else "failed"
    source_path = getattr(artifact, "source_path", "") if artifact else ""
    artifact_id = getattr(artifact, "artifact_id", "") if artifact else ""

    # --- 1. well-formedness / parse status ---------------------------------
    if parse_status == "rejected":
        findings.append(_finding(
            "well_formed", "error",
            "the document was rejected before parsing (DOCTYPE/ENTITY declarations are not allowed)",
            artifact_id=artifact_id, source_path=source_path,
        ))
    elif parse_status != "ok":
        for warning in (getattr(artifact, "validation_warnings", []) or []):
            findings.append(_finding(
                "well_formed", "error", str(warning),
                artifact_id=artifact_id, source_path=source_path,
            ))
    checks.append({"check": "well_formed", "passed": parse_status == "ok",
                   "detail": f"parse status: {parse_status}"})

    # --- 2. schema version -------------------------------------------------
    schema_version = getattr(artifact, "autosar_schema_version", "") if artifact else ""
    if not schema_version:
        findings.append(_finding(
            "schema_version", "warning",
            "the document does not declare a schema version",
            artifact_id=artifact_id, source_path=source_path,
        ))
    checks.append({"check": "schema_version", "passed": bool(schema_version),
                   "detail": schema_version or "not declared"})

    # --- 3. release --------------------------------------------------------
    release = getattr(artifact, "autosar_release", "") if artifact else ""
    if not release:
        findings.append(_finding(
            "release_declared", "warning",
            "the document does not state an AUTOSAR release; the release is left empty "
            "rather than guessed",
            artifact_id=artifact_id, source_path=source_path,
        ))
    checks.append({"check": "release_declared", "passed": bool(release),
                   "detail": release or "not declared"})

    # --- 4. unresolved references -----------------------------------------
    unresolved = list(getattr(topology, "unresolved_refs", []) or [])
    # A port that points at an interface the document does not contain is an
    # unresolved reference too, even though the parser could not flag it.
    interface_names = set()
    for interface in (getattr(topology, "interfaces", []) or []):
        interface_names.add(interface.qualified_name)
        interface_names.add(interface.short_name)
    for port in (getattr(topology, "ports", []) or []):
        ref = getattr(port, "interface_ref", None)
        if not ref:
            continue
        if ref in interface_names or ref.rsplit("/", 1)[-1] in interface_names:
            continue
        unresolved.append({"ref": ref, "connector": "port",
                           "role": "port_to_interface",
                           "line_start": getattr(port, "line_start", 0)})
    for ref in unresolved:
        findings.append(_finding(
            "references_resolved", "error",
            f"unresolved reference: {ref.get('ref', '')}",
            artifact_id=artifact_id, source_path=source_path,
            line_start=ref.get("line_start"), ref=ref.get("ref", ""),
            role=ref.get("role", ""),
        ))
    checks.append({"check": "references_resolved", "passed": not unresolved,
                   "detail": f"{len(unresolved)} unresolved reference(s)"})

    # --- 5. duplicate short names -----------------------------------------
    duplicates = _duplicate_short_names(topology)
    for qualified, count in duplicates:
        findings.append(_finding(
            "short_names_unique", "warning",
            f"{count} elements share the qualified name {qualified}",
            artifact_id=artifact_id, source_path=source_path, qualified_name=qualified,
        ))
    checks.append({"check": "short_names_unique", "passed": not duplicates,
                   "detail": f"{len(duplicates)} duplicate name(s)"})

    # --- 6. required attributes -------------------------------------------
    missing = _missing_required(topology)
    for item in missing:
        findings.append(_finding(
            "required_attributes", "warning",
            f"{item['element']} {item['qualified_name']} has no {item['attribute']}",
            artifact_id=artifact_id, source_path=source_path,
            line_start=item.get("line_start"),
            qualified_name=item["qualified_name"], element=item["element"],
        ))
    checks.append({"check": "required_attributes", "passed": not missing,
                   "detail": f"{len(missing)} missing attribute(s)"})

    # --- 7. no fabricated release -----------------------------------------
    if release and not str(release).strip():
        findings.append(_finding("no_fabricated_data", "error",
                                 "an empty release was written as a value",
                                 artifact_id=artifact_id))

    severity = "info"
    if any(f["severity"] == "error" for f in findings):
        severity = "error"
    elif any(f["severity"] == "warning" for f in findings):
        severity = "warning"
    status = "failed" if severity == "error" else ("passed" if not findings else "passed_with_warnings")

    return {
        "tool": "validate_arxml",
        "status": status,
        "severity": severity,
        "message": _message(status, len(findings)),
        "artifact_id": artifact_id,
        "source_path": source_path,
        "source_sha256": getattr(artifact, "source_sha256", "") if artifact else "",
        "checks": checks,
        "findings": sorted(findings, key=lambda f: _SEVERITY_ORDER.get(f["severity"], 9)),
        "scope": {
            "components": len(getattr(topology, "components", []) or []),
            "ports": len(getattr(topology, "ports", []) or []),
            "interfaces": len(getattr(topology, "interfaces", []) or []),
            "connectors": len(getattr(topology, "connectors", []) or []),
            "runnables": len(getattr(topology, "runnables", []) or []),
            "ecuc_parameters": len(getattr(topology, "ecuc_parameters", []) or []),
        },
    }


def _message(status: str, count: int) -> str:
    if status == "failed":
        return f"validation failed with {count} finding(s)"
    if status == "passed_with_warnings":
        return f"validation passed with {count} warning(s) - review them before relying on the file"
    return "validation passed with no findings"


def _duplicate_short_names(topology) -> list[tuple[str, int]]:
    seen: dict[str, int] = {}
    for group in ("components", "ports", "interfaces", "runnables"):
        for item in (getattr(topology, group, []) or []):
            name = getattr(item, "qualified_name", "") or ""
            if name:
                seen[name] = seen.get(name, 0) + 1
    return sorted(((name, count) for name, count in seen.items() if count > 1),
                  key=lambda pair: pair[0])


def _missing_required(topology) -> list[dict]:
    missing: list[dict] = []
    for component in (getattr(topology, "components", []) or []):
        if not getattr(component, "uuid", None):
            missing.append({"element": "component",
                            "qualified_name": component.qualified_name,
                            "attribute": "UUID",
                            "line_start": getattr(component, "line_start", 0)})
    for interface in (getattr(topology, "interfaces", []) or []):
        if interface.interface_type == "unknown":
            missing.append({"element": "interface",
                            "qualified_name": interface.qualified_name,
                            "attribute": "interface type",
                            "line_start": getattr(interface, "line_start", 0)})
    for port in (getattr(topology, "ports", []) or []):
        if not getattr(port, "interface_ref", None):
            missing.append({"element": "port",
                            "qualified_name": port.qualified_name,
                            "attribute": "interface reference",
                            "line_start": getattr(port, "line_start", 0)})
    return missing


def validation_summary(result: dict) -> str:
    """A one-line, human-readable summary of a validation result."""
    checks = result.get("checks", [])
    passed = sum(1 for c in checks if c.get("passed"))
    return (f"{result.get('status', 'unknown')}: {passed}/{len(checks)} checks passed, "
            f"{len(result.get('findings', []))} finding(s)")
