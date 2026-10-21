"""The six deterministic ARXML tools (ADR-0005).

ARXML is **structured data**, not RAG text. These tools answer structural
questions about a document without a model in the loop, and every answer
carries the file/line where the fact was observed.

The rule they all obey: **never fabricate structure.** When a fact is not in
the file, the tool says so and names the artifact, version and scope it
searched — an empty result is never presented as "the document does not
contain it" unless the search actually covered the whole document.
"""
from __future__ import annotations

from .validation import validate_arxml, validation_summary

__all__ = [
    "ARXML_TOOLS",
    "analyze_change_impact",
    "diff_arxml_versions",
    "query_arxml_path",
    "resolve_arxml_references",
    "tool_catalogue",
    "trace_communication_path",
    "validate_arxml",
]


def _artifact_of(topology) -> dict:
    artifact = getattr(topology, "artifact", None)
    return {
        "artifact_id": getattr(artifact, "artifact_id", "") if artifact else "",
        "source_path": getattr(artifact, "source_path", "") if artifact else "",
        "source_sha256": getattr(artifact, "source_sha256", "") if artifact else "",
        "autosar_release": getattr(artifact, "autosar_release", "") if artifact else "",
        "schema_version": getattr(artifact, "autosar_schema_version", "") if artifact else "",
    }


def _index(topology) -> tuple[dict, set[str]]:
    """Every addressable element of a topology, by several keys.

    Returns the index and the set of short names that are **ambiguous** — they
    belong to more than one qualified name, so they must not silently resolve
    to whichever element happened to be indexed first.
    """
    index: dict[str, dict] = {}
    short_names: dict[str, set[str]] = {}
    groups = (
        ("component", getattr(topology, "components", []) or []),
        ("port", getattr(topology, "ports", []) or []),
        ("interface", getattr(topology, "interfaces", []) or []),
        ("runnable", getattr(topology, "runnables", []) or []),
        ("connector", getattr(topology, "connectors", []) or []),
        ("ecuc_parameter", getattr(topology, "ecuc_parameters", []) or []),
    )
    for kind, items in groups:
        for item in items:
            entry = {
                "kind": kind,
                "qualified_name": getattr(item, "qualified_name", ""),
                "short_name": getattr(item, "short_name", ""),
                "uuid": getattr(item, "uuid", None),
                "line_start": getattr(item, "line_start", 0),
                "line_end": getattr(item, "line_end", 0),
                "source_xpath": getattr(item, "source_xpath", ""),
                "element": item,
            }
            for key in (entry["qualified_name"], entry["short_name"]):
                if key and key not in index:
                    index[key] = entry
            if entry["short_name"]:
                short_names.setdefault(entry["short_name"], set()).add(entry["qualified_name"])
    ambiguous = {name for name, owners in short_names.items() if len(owners) > 1}
    return index, ambiguous


def _lookup(index: dict, ambiguous: set[str], needle: str) -> tuple[dict | None, str]:
    """Find an element. An ambiguous short name is a miss, not a guess."""
    needle = (needle or "").strip()
    if not needle:
        return None, "a path or short name is required"
    entry = index.get(needle)
    if entry is not None:
        return entry, ""
    tail = needle.rsplit("/", 1)[-1]
    if tail in ambiguous:
        return None, (f"{tail!r} is ambiguous - {needle!r} does not identify one element")
    entry = index.get(tail)
    if entry is not None:
        return entry, ""
    return None, f"no element matches {needle!r} in this artifact"


# --------------------------------------------------------------------------- #
# 1. validate
# --------------------------------------------------------------------------- #


def validate(topology) -> dict:
    """Structural validation of a parsed ARXML document."""
    result = validate_arxml(topology)
    result["summary"] = validation_summary(result)
    return result


# --------------------------------------------------------------------------- #
# 2. resolve references
# --------------------------------------------------------------------------- #


def resolve_arxml_references(topology) -> dict:
    """Resolve every reference the document makes and report what is left.

    Returns `{tool, resolved[], unresolved[], counts, scope}`.
    """
    resolved: list[dict] = []
    unresolved: list[dict] = []

    ports = getattr(topology, "ports", []) or []
    interfaces = getattr(topology, "interfaces", []) or []
    interface_names = {i.qualified_name for i in interfaces} | {i.short_name for i in interfaces}
    port_names = {p.qualified_name for p in ports} | {p.short_name for p in ports}
    component_names = {c.qualified_name for c in (getattr(topology, "components", []) or [])}
    component_names |= {c.short_name for c in (getattr(topology, "components", []) or [])}

    for port in ports:
        ref = port.interface_ref
        if not ref:
            continue
        if ref in interface_names or ref.rsplit("/", 1)[-1] in interface_names:
            resolved.append({"kind": "port_to_interface", "from": port.qualified_name,
                             "to": ref, "line_start": port.line_start})
        else:
            unresolved.append({"kind": "port_to_interface", "from": port.qualified_name,
                               "to": ref, "line_start": port.line_start,
                               "reason": "no interface with this name in the document"})

    for connector in (getattr(topology, "connectors", []) or []):
        for role, ref in (("provider", connector.provider_port_ref),
                          ("requester", connector.requester_port_ref)):
            if not ref:
                continue
            if ref in port_names or ref.rsplit("/", 1)[-1] in port_names:
                resolved.append({"kind": f"connector_{role}_port", "from": connector.connector_type,
                                 "to": ref, "line_start": connector.line_start})
            else:
                unresolved.append({"kind": f"connector_{role}_port", "from": connector.connector_type,
                                   "to": ref, "line_start": connector.line_start,
                                   "reason": "no port with this name in the document"})
        for role, ref in (("provider_component", connector.provider_component_ref),
                          ("requester_component", connector.requester_component_ref)):
            if not ref:
                continue
            if ref in component_names or ref.rsplit("/", 1)[-1] in component_names:
                resolved.append({"kind": f"connector_{role}", "from": connector.connector_type,
                                 "to": ref, "line_start": connector.line_start})
            else:
                unresolved.append({"kind": f"connector_{role}", "from": connector.connector_type,
                                   "to": ref, "line_start": connector.line_start,
                                   "reason": "no component with this name in the document"})

    for ref in (getattr(topology, "unresolved_refs", []) or []):
        unresolved.append({"kind": "unresolved_reference", "from": "",
                           "to": ref.get("ref", ""), "line_start": ref.get("line_start", 0),
                           "reason": "the parser could not resolve this reference"})

    return {
        "tool": "resolve_arxml_references",
        "status": "ok" if not unresolved else "incomplete",
        "artifact": _artifact_of(topology),
        "resolved": resolved,
        "unresolved": unresolved,
        "counts": {"resolved": len(resolved), "unresolved": len(unresolved)},
        "summary": (f"{len(resolved)} reference(s) resolved, {len(unresolved)} left unresolved"),
    }


# --------------------------------------------------------------------------- #
# 3. query a path
# --------------------------------------------------------------------------- #


def query_arxml_path(topology, path: str, kind: str = "") -> dict:
    """Look an element up by its qualified path or short name.

    Returns the element, its position in the file and the elements that
    reference it — so the answer is a *place*, not just a name.
    """
    needle = (path or "").strip()
    if not needle:
        return {"tool": "query_arxml_path", "status": "invalid",
                "error": "a path or short name is required",
                "artifact": _artifact_of(topology)}

    index, ambiguous = _index(topology)
    entry, reason = _lookup(index, ambiguous, needle)
    if entry is None:
        return {
            "tool": "query_arxml_path", "status": "not_found",
            "searched": {"path": needle, "kind": kind or "any",
                         "scope": _artifact_of(topology)},
            "error": reason,
            "artifact": _artifact_of(topology),
        }
    if kind and entry["kind"] != kind:
        return {
            "tool": "query_arxml_path", "status": "not_found",
            "searched": {"path": needle, "kind": kind, "scope": _artifact_of(topology)},
            "error": f"{needle!r} exists but is a {entry['kind']}, not a {kind}",
            "artifact": _artifact_of(topology),
        }

    referenced_by = []
    for connector in (getattr(topology, "connectors", []) or []):
        for role, ref in (("provider_port", connector.provider_port_ref),
                          ("requester_port", connector.requester_port_ref),
                          ("provider_component", connector.provider_component_ref),
                          ("requester_component", connector.requester_component_ref)):
            if ref and (ref == entry["qualified_name"] or ref.rsplit("/", 1)[-1] == entry["short_name"]):
                referenced_by.append({"role": role, "ref": ref,
                                       "connector_type": connector.connector_type,
                                       "line_start": connector.line_start})

    return {
        "tool": "query_arxml_path",
        "status": "ok",
        "artifact": _artifact_of(topology),
        "element": {
            "kind": entry["kind"],
            "qualified_name": entry["qualified_name"],
            "short_name": entry["short_name"],
            "uuid": entry["uuid"],
            "line_start": entry["line_start"],
            "line_end": entry["line_end"],
            "source_xpath": entry["source_xpath"],
        },
        "referenced_by": referenced_by,
        "summary": f"{entry['kind']} {entry['qualified_name']} at line {entry['line_start']}",
    }


# --------------------------------------------------------------------------- #
# 4. diff two versions
# --------------------------------------------------------------------------- #


def _fingerprint(topology) -> dict:
    """A comparable shape of a topology: qualified name -> signature."""
    out: dict[str, str] = {}
    for kind, items in (("component", getattr(topology, "components", []) or []),
                        ("port", getattr(topology, "ports", []) or []),
                        ("interface", getattr(topology, "interfaces", []) or []),
                        ("runnable", getattr(topology, "runnables", []) or []),
                        ("connector", getattr(topology, "connectors", []) or []),
                        ("ecuc_parameter", getattr(topology, "ecuc_parameters", []) or [])):
        for item in items:
            name = getattr(item, "qualified_name", "") or getattr(item, "short_name", "")
            if not name:
                continue
            fields = {k: v for k, v in item.model_dump().items()
                      if k not in ("source_artifact_id", "source_xpath", "line_start", "line_end")}
            out[f"{kind}:{name}"] = repr(sorted(fields.items(), key=lambda kv: kv[0]))
    return out


def diff_arxml_versions(base, target) -> dict:
    """Structural difference between two parsed ARXML documents.

    Only facts that are *present* in one version and absent (or different) in
    the other are reported — a wording change never becomes a structural change.
    """
    base_fp = _fingerprint(base)
    target_fp = _fingerprint(target)
    added = sorted(set(target_fp) - set(base_fp))
    removed = sorted(set(base_fp) - set(target_fp))
    modified = sorted(key for key in set(base_fp) & set(target_fp)
                      if base_fp[key] != target_fp[key])

    return {
        "tool": "diff_arxml_versions",
        "status": "ok",
        "base": _artifact_of(base),
        "target": _artifact_of(target),
        "added": added,
        "removed": removed,
        "modified": modified,
        "counts": {"added": len(added), "removed": len(removed), "modified": len(modified)},
        "summary": (f"{len(added)} added, {len(removed)} removed, {len(modified)} modified"),
    }


# --------------------------------------------------------------------------- #
# 5. trace a communication path
# --------------------------------------------------------------------------- #


def trace_communication_path(topology, source: str, target: str) -> dict:
    """Trace how a signal travels from one element to another.

    The trace follows the *documented* connectors only. When no path exists the
    result says which artifact and scope were searched.
    """
    index, ambiguous = _index(topology)
    src, src_reason = _lookup(index, ambiguous, source)
    dst, dst_reason = _lookup(index, ambiguous, target)
    if src is None or dst is None:
        missing = source if src is None else target
        reason = src_reason if src is None else dst_reason
        return {
            "tool": "trace_communication_path", "status": "not_found",
            "searched": {"source": source, "target": target,
                         "scope": _artifact_of(topology)},
            "error": reason or f"no element matches {missing!r} in this artifact",
            "artifact": _artifact_of(topology),
        }

    # Build an undirected adjacency over the connectors.
    adjacency: dict[str, list[tuple[str, str]]] = {}

    def link(a: str, b: str, kind: str) -> None:
        adjacency.setdefault(a, []).append((b, kind))
        adjacency.setdefault(b, []).append((a, kind))

    for connector in (getattr(topology, "connectors", []) or []):
        provider = connector.provider_port_ref or connector.provider_component_ref
        requester = connector.requester_port_ref or connector.requester_component_ref
        if provider and requester:
            link(provider, requester, connector.connector_type)

    def key_of(name: str) -> str:
        entry = index.get(name) or index.get(name.rsplit("/", 1)[-1])
        return entry["qualified_name"] if entry else name

    start = key_of(src["qualified_name"])
    goal = key_of(dst["qualified_name"])

    queue: list[tuple[str, list[str], list[str]]] = [(start, [start], [])]
    paths: list[dict] = []
    while queue and len(paths) < 10:
        current, node_path, kind_path = queue.pop(0)
        if len(node_path) > 8:
            continue
        for neighbour, kind in sorted(adjacency.get(current, [])):
            if neighbour in node_path:
                continue
            new_nodes = node_path + [neighbour]
            new_kinds = kind_path + [kind]
            if neighbour == goal:
                paths.append({"nodes": new_nodes, "connector_types": new_kinds})
            else:
                queue.append((neighbour, new_nodes, new_kinds))

    return {
        "tool": "trace_communication_path",
        "status": "ok" if paths else "no_path",
        "artifact": _artifact_of(topology),
        "source": src["qualified_name"],
        "target": dst["qualified_name"],
        "paths": paths,
        "summary": (f"{len(paths)} path(s) from {src['qualified_name']} to {dst['qualified_name']}"
                    if paths else
                    f"no connector path from {src['qualified_name']} to {dst['qualified_name']} "
                    f"in this artifact"),
    }


# --------------------------------------------------------------------------- #
# 6. change impact
# --------------------------------------------------------------------------- #


def analyze_change_impact(base, target, element: str = "") -> dict:
    """Which elements are affected by the difference between two versions.

    When ``element`` is given, only the changes touching that element and the
    elements that reference it are reported.
    """
    diff = diff_arxml_versions(base, target)
    changed = diff["added"] + diff["removed"] + diff["modified"]
    index, _ = _index(target)
    base_index, _ = _index(base)

    impacted: list[dict] = []
    for key in changed:
        kind, _, name = key.partition(":")
        entry = index.get(name) or base_index.get(name)
        dependents = []
        if entry:
            for connector in (getattr(target, "connectors", []) or []):
                for role, ref in (("provider_port", connector.provider_port_ref),
                                  ("requester_port", connector.requester_port_ref)):
                    if ref and (ref == entry["qualified_name"]
                                or ref.rsplit("/", 1)[-1] == entry["short_name"]):
                        dependents.append({"role": role, "ref": ref,
                                           "line_start": connector.line_start})
        impacted.append({
            "key": key,
            "kind": kind,
            "name": name,
            "change": ("added" if key in diff["added"]
                       else "removed" if key in diff["removed"] else "modified"),
            "line_start": entry["line_start"] if entry else 0,
            "dependents": dependents,
        })

    if element:
        needle = element.rsplit("/", 1)[-1]
        impacted = [i for i in impacted
                    if i["name"] == element or i["name"].endswith("/" + needle)
                    or any(d["ref"].endswith(needle) for d in i["dependents"])]

    return {
        "tool": "analyze_change_impact",
        "status": "ok",
        "base": diff["base"],
        "target": diff["target"],
        "element": element,
        "impacted": impacted,
        "counts": {"changed": len(changed), "impacted": len(impacted),
                   "added": diff["counts"]["added"], "removed": diff["counts"]["removed"],
                   "modified": diff["counts"]["modified"]},
        "summary": (f"{len(impacted)} of {len(changed)} change(s) affect"
                    + (f" {element}" if element else " the document")),
    }


# --------------------------------------------------------------------------- #
# catalogue
# --------------------------------------------------------------------------- #

ARXML_TOOLS = (
    {
        "name": "validate_arxml",
        "description": "Validate a parsed ARXML document and report every finding with a file/line.",
        "mutating": False,
        "inputs": ["topology"],
    },
    {
        "name": "resolve_arxml_references",
        "description": "Resolve every reference the document makes and report the unresolved ones.",
        "mutating": False,
        "inputs": ["topology"],
    },
    {
        "name": "query_arxml_path",
        "description": "Look an element up by qualified path or short name and return its position.",
        "mutating": False,
        "inputs": ["topology", "path", "kind"],
    },
    {
        "name": "diff_arxml_versions",
        "description": "Structural difference between two parsed ARXML documents.",
        "mutating": False,
        "inputs": ["base", "target"],
    },
    {
        "name": "trace_communication_path",
        "description": "Trace how a signal travels between two elements through the documented connectors.",
        "mutating": False,
        "inputs": ["topology", "source", "target"],
    },
    {
        "name": "analyze_change_impact",
        "description": "Which elements and dependents are affected by the difference between two versions.",
        "mutating": False,
        "inputs": ["base", "target", "element"],
    },
)


def tool_catalogue() -> dict:
    """The deterministic ARXML tools, for discovery by the agent and the UI."""
    return {"tools": [dict(t) for t in ARXML_TOOLS], "count": len(ARXML_TOOLS)}
