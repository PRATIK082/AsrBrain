"""ARXML parser — ARXML as structured data, not RAG text (ADR-0005).

The parser is deterministic and never invents structure:

* every element keeps its **line range** and its **UUID**;
* every object keeps a **qualified path** built from the AR-PACKAGE chain;
* the release is only recorded when the document actually states it;
* a reference that cannot be resolved is reported, not guessed.

`parse_arxml()` keeps its original signature so existing callers and the
`/api/arxml/*` routes keep working.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

import xml.etree.ElementTree as ET

from .models import (
    ArxmlArtifact,
    ArxmlTopology,
    EcucParameter,
    Port,
    PortInterface,
    RteConnector,
    RunnableEntity,
    SoftwareComponent,
)
from .xml_reader import XmlError, line_end_of, line_of, parse_xml

__all__ = ["parse_arxml", "XmlError"]

# AUTOSAR software-component types this parser understands.
_SWCS = {
    "APPLICATION-SW-COMPONENT-TYPE",
    "ATOMIC-SW-COMPONENT-TYPE",
    "COMPOSITION-SW-COMPONENT-TYPE",
    "COMPLEX-DEVICE-DRIVER-SW-COMPONENT-TYPE",
    "ECU-ABSTRACTION-SW-COMPONENT-TYPE",
    "SENSOR-ACTUATOR-SW-COMPONENT-TYPE",
    "SERVICE-SW-COMPONENT-TYPE",
}

# AUTOSAR interface types this parser understands.
_IFACE = {
    "SENDER-RECEIVER-INTERFACE": "sender_receiver",
    "CLIENT-SERVER-INTERFACE": "client_server",
    "MODE-SWITCH-INTERFACE": "mode_switch",
    "PARAMETER-INTERFACE": "parameter",
    "NV-DATA-INTERFACE": "nv_data",
    "TRIGGER-INTERFACE": "trigger",
}

# A release looks like R22-11 / R24-11.
_RELEASE_RE = re.compile(r"^R\d{2}-\d{2}$")

# Elements that may carry the release of the document.
_RELEASE_ELEMENTS = {"AUTOSAR-RELEASE", "RELEASE-VERSION", "AUTOSAR-VERSION"}

# Elements that may carry the UUID of an object.
_UUID_ELEMENTS = {"UUID", "LONG-NAME"}


def _local(tag: str) -> str:
    """The local name of a tag, with or without a namespace."""
    if not isinstance(tag, str):
        return ""
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag.rsplit(":", 1)[-1]


def _short_name(el: ET.Element) -> str:
    for child in el:
        if _local(child.tag) == "SHORT-NAME":
            return (child.text or "").strip()
    return ""


def _child_text(el: ET.Element, *names: str) -> str:
    """The text of the first direct child with one of the given local names."""
    wanted = {n.upper() for n in names}
    for child in el:
        if _local(child.tag).upper() in wanted:
            return (child.text or "").strip()
    return ""


def _uuid_of(el: ET.Element) -> str | None:
    for child in el:
        if _local(child.tag).upper() == "UUID":
            value = (child.text or "").strip()
            if value:
                return value
    return None


def _iref_text(el: ET.Element) -> str | None:
    """The target of the first *-IREF child."""
    for child in el:
        if _local(child.tag).endswith("-IREF"):
            for grand in child:
                target = _child_text(grand, "TARGET", "TARGET-REF", "CONTEXT-ELEMENT-REF")
                if target:
                    return target
            text = (child.text or "").strip()
            if text:
                return text
    return None


def _iter_refs(el: ET.Element, suffix: str) -> Iterable[str]:
    """Every direct child whose local name ends with the given suffix."""
    for child in el:
        if _local(child.tag).endswith(suffix):
            text = (child.text or "").strip()
            if text:
                yield text


def _detect_release(root: ET.Element, explicit: str = "") -> str:
    """The release the document states — never inferred from a file name."""
    if explicit and _RELEASE_RE.match(explicit.strip()):
        return explicit.strip()
    for key, value in root.attrib.items():
        if key.upper() == "SCHEMA-VERSION" and _RELEASE_RE.match(value.strip()):
            return value.strip()
    for element in root.iter():
        if _local(element.tag).upper() in _RELEASE_ELEMENTS:
            text = (element.text or "").strip()
            if _RELEASE_RE.match(text):
                return text
    return ""


def _count_elements(root: ET.Element) -> int:
    return sum(1 for _ in root.iter())


def _parse_arxml(path: str | Path, tenant_id: str = "default", project_scope: str = "",
                 autosar_release: str = "") -> ArxmlTopology:
    """Parse one ARXML file into a typed topology."""
    file_path = Path(path)
    raw = file_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    artifact_id = f"arxml-{sha[:12]}"
    warnings: list[str] = []

    # No DTD / entity expansion: a hostile document must not be able to read
    # the filesystem or the network through the parser.
    head = raw[:4096]
    if b"<!ENTITY" in head or b"<!DOCTYPE" in head:
        artifact = ArxmlArtifact(
            artifact_id=artifact_id,
            source_path=str(file_path),
            source_sha256=sha,
            project_scope=project_scope,
            tenant_id=tenant_id,
            parse_status="rejected",
            validation_warnings=["DOCTYPE/ENTITY declarations rejected"],
        )
        return ArxmlTopology(artifact=artifact)

    try:
        document = parse_xml(raw)
    except XmlError as exc:
        artifact = ArxmlArtifact(
            artifact_id=artifact_id,
            source_path=str(file_path),
            source_sha256=sha,
            project_scope=project_scope,
            tenant_id=tenant_id,
            parse_status="failed",
            validation_warnings=[str(exc)],
        )
        return ArxmlTopology(artifact=artifact)

    root = document.root
    schema_version = document.schema_version or _namespace_tail(document.namespace)
    release = _detect_release(root, autosar_release)
    if not release:
        warnings.append("the document does not state an AUTOSAR release")

    artifact = ArxmlArtifact(
        artifact_id=artifact_id,
        source_path=str(file_path),
        source_sha256=sha,
        autosar_schema_version=schema_version or None,
        autosar_release=release or None,
        project_scope=project_scope,
        tenant_id=tenant_id,
        parse_status="ok",
        validation_warnings=warnings,
        line_start=document.line_start,
        line_end=document.line_end,
        element_count=_count_elements(root),
    )
    topo = ArxmlTopology(
        artifact=artifact,
        line_start=document.line_start,
        line_end=document.line_end,
        element_count=artifact.element_count,
    )
    _walk(root, "/" + _local(root.tag), topo, artifact_id, warnings, "")
    _resolve_connectors(topo, warnings)
    artifact.validation_warnings = warnings
    return topo


def _namespace_tail(namespace: str) -> str:
    if not namespace:
        return ""
    return namespace.rstrip("/").rsplit("/", 1)[-1]



#: Containers that only group other elements. The parser descends through them
#: so a port under ``<PORTS>`` and a runnable under
#: ``<INTERNAL-BEHAVIORS>/<INTERNAL-BEHAVIOR>/<RUNNABLES>`` are both found.
_CONTAINER_TAGS = {
    "PORTS",
    "INTERNAL-BEHAVIORS",
    "INTERNAL-BEHAVIOR",
    "RUNNABLES",
    "IMPLEMENTATION",
    "CODE",
    "VARIABLES",
    "DATA-ELEMENTS",
}


def _descend(el: ET.Element, xpath: str) -> list[tuple[ET.Element, str]]:
    """The children of a container, and of the containers inside it."""
    out: list[tuple[ET.Element, str]] = []
    for child in el:
        out.append((child, xpath))
        tag = _local(child.tag)
        if tag in _CONTAINER_TAGS:
            out.extend(_descend(child, f"{xpath}/{tag}"))
    return out


def _component_children(el: ET.Element, xpath: str) -> list[tuple[ET.Element, str]]:
    """The children of a component, including the standard containers.

    AUTOSAR nests ports under ``<PORTS>``, internal behaviors under
    ``<INTERNAL-BEHAVIORS>`` and runnables either under
    ``<IMPLEMENTATION>/<CODE>`` or under
    ``<INTERNAL-BEHAVIORS>/<INTERNAL-BEHAVIOR>/<RUNNABLES>``. Both the direct
    children and the children of those containers are returned, each with the
    xpath of its parent, so a citation can point at the container it really
    lives in.
    """
    out: list[tuple[ET.Element, str]] = []
    for child in el:
        out.append((child, xpath))
        if _local(child.tag) in _CONTAINER_TAGS:
            out.extend(_descend(child, f"{xpath}/{_local(child.tag)}"))
    return out

def _walk(el: ET.Element, xpath: str, topo: ArxmlTopology, aid: str,
          warnings: list[str], pkg: str) -> None:
    """Walk the document, collecting typed objects."""
    tag = _local(el.tag)
    sn = _short_name(el)

    if tag == "AR-PACKAGE" and sn:
        pkg = f"{pkg}/{sn}" if pkg else f"/{sn}"

    if tag in _SWCS:
        component = SoftwareComponent(
            uuid=_uuid_of(el),
            short_name=sn,
            qualified_name=f"{pkg}/{sn}" if pkg else f"/{sn}",
            component_type=tag,
            package_path=pkg,
            source_artifact_id=aid,
            source_xpath=xpath,
            element_type=tag,
            line_start=line_of(el),
            line_end=line_end_of(el),
        )
        topo.components.append(component)
        for child, parent_xpath in _component_children(el, xpath):
            child_tag = _local(child.tag)
            child_sn = _short_name(child)
            if child_tag in {"P-PORT-PROTOTYPE", "R-PORT-PROTOTYPE", "PR-PORT-PROTOTYPE"}:
                direction = {"P-PORT-PROTOTYPE": "P", "R-PORT-PROTOTYPE": "R",
                             "PR-PORT-PROTOTYPE": "PR"}[child_tag]
                port = Port(
                    uuid=_uuid_of(child),
                    short_name=child_sn,
                    qualified_name=f"{pkg}/{sn}/{child_sn}",
                    direction=direction,
                    interface_ref=_child_text(child, "PROVIDED-INTERFACE-TREF",
                                             "REQUIRED-INTERFACE-TREF",
                                             "PROVIDED-REQUIRED-INTERFACE-TREF") or None,
                    interface_type=_child_text(child, "INTERFACE-TYPE") or None,
                    comspec=_comspec(child),
                    component_ref=component.qualified_name,
                    source_artifact_id=aid,
                    source_xpath=f"{parent_xpath}//{child_tag}[SHORT-NAME='{child_sn}']",
                    element_type=child_tag,
                    line_start=line_of(child),
                    line_end=line_end_of(child),
                )
                topo.ports.append(port)
                component.ports.append(port.qualified_name)
            elif child_tag == "RUNNABLE-ENTITY":
                runnable = RunnableEntity(
                    uuid=_uuid_of(child),
                    short_name=child_sn,
                    qualified_name=f"{pkg}/{sn}/{child_sn}",
                    symbol=_child_text(child, "SYMBOL") or None,
                    events=list(_iter_refs(child, "-IREF")),
                    data_accesses=_data_accesses(child),
                    server_call_points=_server_call_points(child),
                    source_artifact_id=aid,
                    source_xpath=f"{parent_xpath}//RUNNABLE-ENTITY[SHORT-NAME='{child_sn}']",
                    element_type=child_tag,
                    line_start=line_of(child),
                    line_end=line_end_of(child),
                )
                topo.runnables.append(runnable)
                component.runnables.append(runnable.qualified_name)
            elif child_tag == "INTERNAL-BEHAVIOR":
                component.internal_behaviors.append(child_sn or _short_name(child))

    elif tag in _IFACE:
        interface = PortInterface(
            uuid=_uuid_of(el),
            short_name=sn,
            qualified_name=f"{pkg}/{sn}" if pkg else f"/{sn}",
            interface_type=_IFACE[tag],
            data_elements=_data_elements(el),
            operations=_operations(el),
            source_artifact_id=aid,
            source_xpath=xpath,
            element_type=tag,
            line_start=line_of(el),
            line_end=line_end_of(el),
        )
        topo.interfaces.append(interface)

    elif tag in {"ASSEMBLY-SW-CONNECTOR", "DELEGATION-SW-CONNECTOR"}:
        connector_type = "assembly" if tag == "ASSEMBLY-SW-CONNECTOR" else "delegation"
        provider_component, provider_port = _connector_side(el, "PROVIDER-IREF")
        requester_component, requester_port = _connector_side(el, "REQUESTER-IREF")
        if connector_type == "delegation":
            provider_component, provider_port = _connector_side(el, "INNER-PORT-IREF")
            requester_component, requester_port = _connector_side(el, "OUTER-PORT-IREF")
        connector = RteConnector(
            connector_type=connector_type,
            provider_component_ref=provider_component,
            provider_port_ref=provider_port,
            requester_component_ref=requester_component,
            requester_port_ref=requester_port,
            composition_ref=_child_text(el, "CONTEXT-COMPOSITION-REF",
                                        "COMPOSITION-REF") or None,
            uuid=_uuid_of(el),
            source_artifact_id=aid,
            source_xpath=xpath,
            element_type=tag,
            line_start=line_of(el),
            line_end=line_end_of(el),
        )
        topo.connectors.append(connector)

    elif tag == "ECUC-NUMERICAL-PARAM-VALUE":
        parameter = EcucParameter(
            short_name=sn,
            qualified_path=f"{pkg}/{sn}" if pkg else f"/{sn}",
            definition_ref=_child_text(el, "DEFINITION-REF") or None,
            value_type=_child_text(el, "VALUE-TYPE") or "numerical",
            value=_parse_value(_child_text(el, "VALUE")),
            reference_target=_child_text(el, "REFERENCE-VALUE",
                                         "VALUE-REFERENCE") or None,
            container_path=pkg,
            source_artifact_id=aid,
            source_xpath=xpath,
            element_type=tag,
            line_start=line_of(el),
            line_end=line_end_of(el),
        )
        topo.ecuc_parameters.append(parameter)

    for i, child in enumerate(el):
        _walk(child, f"{xpath}/{_local(child.tag)}[{i}]", topo, aid, warnings, pkg)


def _parse_value(text: str):
    if text == "":
        return None
    try:
        if text.lstrip("-").isdigit():
            return int(text)
        return float(text) if "." in text else text
    except ValueError:
        return text


def _comspec(el: ET.Element) -> dict:
    """The communication specification of a port, when present."""
    comspec: dict = {}
    for child in el:
        if _local(child.tag) == "COM-SPECIFICATION":
            comspec["element_type"] = "COM-SPECIFICATION"
            comspec["line_start"] = line_of(child)
            for grand in child:
                tag = _local(grand.tag)
                if tag in {"SIGNAL", "SIGNAL-REF", "DATA-ELEMENT-REF"}:
                    comspec.setdefault("signals", []).append((grand.text or "").strip())
                elif tag in {"MESSAGE", "MESSAGE-REF"}:
                    comspec.setdefault("messages", []).append((grand.text or "").strip())
            break
    return comspec


def _data_elements(el: ET.Element) -> list[dict]:
    out: list[dict] = []
    for child in el:
        if _local(child.tag) == "DATA-ELEMENTS":
            for grand in child:
                if _local(grand.tag) != "VARIABLE-DATA-PROTOTYPE":
                    continue
                out.append({
                    "name": _short_name(grand),
                    "type": _child_text(grand, "TYPE-TREF") or "",
                    "line_start": line_of(grand),
                })
    return out


def _operations(el: ET.Element) -> list[dict]:
    out: list[dict] = []
    for child in el:
        if _local(child.tag) == "OPERATIONS":
            for grand in child:
                if _local(grand.tag) != "CLIENT-SERVER-OPERATION":
                    continue
                out.append({
                    "name": _short_name(grand),
                    "line_start": line_of(grand),
                })
    return out


def _data_accesses(el: ET.Element) -> list[dict]:
    out: list[dict] = []
    for child in el:
        tag = _local(child.tag)
        if tag in {"DATA-SEND-POINTS", "DATA-RECEIVE-POINTS-BY-VALUE",
                   "DATA-RECEIVE-POINTS-BY-REFERENCE", "SERVER-CALL-POINTS"}:
            for grand in child:
                if not _local(grand.tag).endswith("-ACCESS"):
                    continue
                out.append({
                    "kind": tag,
                    "name": _short_name(grand),
                    "target": _iref_text(grand) or "",
                    "line_start": line_of(grand),
                })
    return out


def _server_call_points(el: ET.Element) -> list[dict]:
    return [d for d in _data_accesses(el) if d["kind"] == "SERVER-CALL-POINTS"]


def _connector_side(el: ET.Element, suffix: str) -> tuple[str | None, str | None]:
    """(component_ref, port_ref) of one side of a connector."""
    for child in el:
        if _local(child.tag).endswith(suffix):
            component = _child_text(child, "CONTEXT-COMPONENT-REF") or None
            port = _child_text(child, "TARGET-P-PORT-REF", "TARGET-R-PORT-REF",
                               "TARGET-PR-PORT-REF", "TARGET-PORT-REF") or None
            return component, port
    return None, None


def _resolve_connectors(topo: ArxmlTopology, warnings: list[str]) -> None:
    """Report references that do not resolve.

    A reference is only reported when it cannot be matched; the parser never
    rewrites or invents a target.
    """
    known_ports = {p.short_name for p in topo.ports}
    known_components = {c.qualified_name for c in topo.components}
    for connector in topo.connectors:
        for role, ref in (("provider", connector.provider_port_ref),
                          ("requester", connector.requester_port_ref)):
            if not ref:
                continue
            if "/" in ref:
                continue
            if ref not in known_ports:
                topo.unresolved_refs.append({
                    "ref": ref,
                    "connector": connector.connector_type,
                    "role": role,
                    "line_start": connector.line_start,
                })
                warnings.append(f"unresolved port reference: {ref}")


def parse_arxml(path: str | Path, tenant_id: str = "default", project_scope: str = "",
                autosar_release: str = "") -> ArxmlTopology:
    """Parse an ARXML file into a typed, provenance-carrying topology."""
    return _parse_arxml(path, tenant_id=tenant_id, project_scope=project_scope,
                        autosar_release=autosar_release)
