"""Safe namespace-aware ARXML parser. Defoused XML, no external entities, typed extraction."""
from __future__ import annotations

import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET

from src.ingestion.arxml.models import (
    ArxmlArtifact, SoftwareComponent, Port, PortInterface, RteConnector,
    RunnableEntity, EcucParameter, ArxmlTopology)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag.rsplit(":", 1)[-1]


_SWCS = {"APPLICATION-SW-COMPONENT-TYPE", "ATOMIC-SW-COMPONENT-TYPE",
         "COMPOSITION-SW-COMPONENT-TYPE", "COMPLEX-DEVICE-DRIVER-SW-COMPONENT-TYPE",
         "ECU-ABSTRACTION-SW-COMPONENT-TYPE", "SENSOR-ACTUATOR-SW-COMPONENT-TYPE",
         "SERVICE-SW-COMPONENT-TYPE"}
_IFACE = {"SENDER-RECEIVER-INTERFACE": "sender_receiver", "CLIENT-SERVER-INTERFACE": "client_server",
          "MODE-SWITCH-INTERFACE": "mode_switch", "PARAMETER-INTERFACE": "parameter",
          "NV-DATA-INTERFACE": "nv_data", "TRIGGER-INTERFACE": "trigger"}


def _short_name(el: ET.Element) -> str:
    for c in el:
        if _local(c.tag) == "SHORT-NAME":
            return (c.text or "").strip()
    return ""


def parse_arxml(path: str | Path, tenant_id: str = "default", project_scope: str = "") -> ArxmlTopology:
    p = Path(path)
    raw = p.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    # Safe parse: stdlib ET does not resolve external entities by default; explicitly forbid DOCTYPE.
    head = raw[:4096].decode("utf-8", "ignore")
    if "<!ENTITY" in head or "<!DOCTYPE" in head:
        art = ArxmlArtifact(artifact_id=f"arxml-{sha[:12]}", source_path=str(p), source_sha256=sha,
                            tenant_id=tenant_id, project_scope=project_scope,
                            parse_status="rejected", validation_warnings=["DOCTYPE/ENTITY declarations rejected"])
        return ArxmlTopology(artifact=art)
    root = ET.fromstring(raw)  # noqa: S314 - validated above, no entity expansion in ET
    warnings: list[str] = []
    ns = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
    schema_ver = root.attrib.get("SCHEMA-VERSION") or (ns.rsplit("/", 1)[-1] if ns else None)
    art = ArxmlArtifact(artifact_id=f"arxml-{sha[:12]}", source_path=str(p), source_sha256=sha,
                        autosar_schema_version=schema_ver, tenant_id=tenant_id, project_scope=project_scope)
    topo = ArxmlTopology(artifact=art)
    _walk(root, "/" + _local(root.tag), topo, art.artifact_id, warnings, pkg="")
    art.validation_warnings = warnings
    _resolve_connectors(topo, warnings)
    art.validation_warnings = warnings
    return topo


def _walk(el: ET.Element, xpath: str, topo: ArxmlTopology, aid: str,
          warnings: list[str], pkg: str) -> None:
    name = _local(el.tag)
    if name == "AR-PACKAGE":
        sn = _short_name(el)
        pkg = f"{pkg}/{sn}" if pkg else f"/{sn}"
    if name in _SWCS:
        sn = _short_name(el)
        ports, runs, ibs = [], [], []
        for d in el.iter():
            ln = _local(d.tag)
            if ln in ("P-PORT-PROTOTYPE", "R-PORT-PROTOTYPE", "PR-PORT-PROTOTYPE"):
                psn = _short_name(d)
                direction = {"P-PORT-PROTOTYPE": "P", "R-PORT-PROTOTYPE": "R"}.get(ln, "PR")
                iref, itype = None, None
                for sub in d.iter():
                    if _local(sub.tag) in ("PROVIDED-INTERFACE-TREF", "REQUIRED-INTERFACE-TREF",
                                            "PROVIDED-REQUIRED-INTERFACE-TREF"):
                        iref = (sub.text or "").strip()
                    if _local(sub.tag) == "INTERFACE-TYPE":
                        itype = (sub.text or "").strip()
                ports.append(f"{pkg}/{sn}/{psn}")
                topo.ports.append(Port(short_name=psn, qualified_name=f"{pkg}/{sn}/{psn}",
                                       direction=direction, interface_ref=iref or None,
                                       interface_type=itype, component_ref=f"{pkg}/{sn}",
                                       source_artifact_id=aid, source_xpath=f"{xpath}//{ln}[SHORT-NAME='{psn}']"))
            elif ln == "RUNNABLE-ENTITY":
                rsn = _short_name(d)
                runs.append(f"{pkg}/{sn}/{rsn}")
                sym = None
                for sub in d:
                    if _local(sub.tag) == "SYMBOL":
                        sym = (sub.text or "").strip()
                topo.runnables.append(RunnableEntity(short_name=rsn, qualified_name=f"{pkg}/{sn}/{rsn}",
                                                     symbol=sym, source_artifact_id=aid, source_xpath=xpath))
            elif ln == "INTERNAL-BEHAVIOR":
                ibs.append(_short_name(d))
        topo.components.append(SoftwareComponent(short_name=sn, qualified_name=f"{pkg}/{sn}",
                                                 component_type=name, package_path=pkg, ports=ports,
                                                 runnables=runs, internal_behaviors=ibs,
                                                 source_artifact_id=aid, source_xpath=xpath))
    elif name in _IFACE:
        sn = _short_name(el)
        data_els, ops = [], []
        for sub in el.iter():
            ln = _local(sub.tag)
            if ln in ("VARIABLE-DATA-PROTOTYPE", "DATA-ELEMENT"):
                data_els.append({"name": _short_name(sub)})
            elif ln == "CLIENT-SERVER-OPERATION":
                ops.append({"name": _short_name(sub)})
        topo.interfaces.append(PortInterface(short_name=sn, qualified_name=f"{pkg}/{sn}",
                                             interface_type=_IFACE[name], data_elements=data_els,
                                             operations=ops, source_artifact_id=aid, source_xpath=xpath))
    elif name == "ASSEMBLY-SW-CONNECTOR":
        prov = req = None
        for sub in el.iter():
            ln = _local(sub.tag)
            if ln == "PROVIDER-IREF":
                prov = _iref_text(sub)
            elif ln == "REQUESTER-IREF":
                req = _iref_text(sub)
        topo.connectors.append(RteConnector(connector_type="assembly", provider_port_ref=prov,
                                            requester_port_ref=req, source_artifact_id=aid, source_xpath=xpath))
    elif name == "DELEGATION-SW-CONNECTOR":
        inner = outer = None
        for sub in el.iter():
            if _local(sub.tag) == "INNER-PORT-IREF":
                inner = _iref_text(sub)
            elif _local(sub.tag) == "OUTER-PORT-IREF":
                outer = _iref_text(sub)
        topo.connectors.append(RteConnector(connector_type="delegation", provider_port_ref=outer,
                                            requester_port_ref=inner, source_artifact_id=aid, source_xpath=xpath))
    elif name == "ECUC-NUMERICAL-PARAM-VALUE":
        defi, val = None, None
        for sub in el:
            if _local(sub.tag) == "DEFINITION-REF":
                defi = (sub.text or "").strip()
            elif _local(sub.tag) == "VALUE":
                val = (sub.text or "").strip()
        topo.ecuc_parameters.append(EcucParameter(short_name=defi.rsplit("/", 1)[-1] if defi else "",
                                                 qualified_path=defi or "", definition_ref=defi,
                                                 value=val, container_path=pkg,
                                                 source_artifact_id=aid, source_xpath=xpath))
    for i, child in enumerate(list(el)):
        _walk(child, f"{xpath}/{_local(child.tag)}[{i}]", topo, aid, warnings, pkg)


def _iref_text(el: ET.Element) -> str | None:
    for sub in el.iter():
        if _local(sub.tag) in ("TARGET-P-PORT-REF", "TARGET-R-PORT-REF", "TARGET-PR-PORT-REF",
                                "CONTEXT-COMPONENT-REF", "TARGET-PORT-REF"):
            t = (sub.text or "").strip()
            if t:
                return t
    return None


def _resolve_connectors(topo: ArxmlTopology, warnings: list[str]) -> None:
    known_ports = {p.qualified_name.split("/")[-1]: p.qualified_name for p in topo.ports}
    for c in topo.connectors:
        for ref in (c.provider_port_ref, c.requester_port_ref):
            if ref and "/" not in ref and ref not in known_ports:
                topo.unresolved_refs.append({"ref": ref, "connector": c.connector_type})
                warnings.append(f"unresolved port reference: {ref}")
