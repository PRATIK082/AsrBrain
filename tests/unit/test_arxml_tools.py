"""Tests for the six deterministic ARXML tools (ADR-0005)."""
from pathlib import Path

from src.ingestion.arxml import parse_arxml
from src.ingestion.arxml.tools import (
    analyze_change_impact,
    diff_arxml_versions,
    query_arxml_path,
    resolve_arxml_references,
    tool_catalogue,
    trace_communication_path,
    validate,
)

AUTOSAR_NS = "http://autosar.org/schema/r4.0"

TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="{ns}" SCHEMA-VERSION="R22-11">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Pkg</SHORT-NAME>
      <ELEMENTS>
        <APPLICATION-SW-COMPONENT-TYPE>
          <UUID>11111111-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>{swc}</SHORT-NAME>
          <PORTS>
            <P-PORT-PROTOTYPE>
              <UUID>22222222-0000-0000-0000-00000000000a</UUID>
              <SHORT-NAME>OutPort</SHORT-NAME>
              <PROVIDED-INTERFACE-TREF>/If/OutIf</PROVIDED-INTERFACE-TREF>
              <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
            </P-PORT-PROTOTYPE>
            <R-PORT-PROTOTYPE>
              <UUID>33333333-0000-0000-0000-00000000000a</UUID>
              <SHORT-NAME>InPort</SHORT-NAME>
              <REQUIRED-INTERFACE-TREF>/If/InIf</REQUIRED-INTERFACE-TREF>
              <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
            </R-PORT-PROTOTYPE>
          </PORTS>
        </APPLICATION-SW-COMPONENT-TYPE>
        <SENDER-RECEIVER-INTERFACE>
          <UUID>44444444-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>OutIf</SHORT-NAME>
        </SENDER-RECEIVER-INTERFACE>
        <SENDER-RECEIVER-INTERFACE>
          <UUID>55555555-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>InIf</SHORT-NAME>
        </SENDER-RECEIVER-INTERFACE>
        <APPLICATION-SW-COMPONENT-TYPE>
          <UUID>77777777-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>Receiver</SHORT-NAME>
          <PORTS>
            <R-PORT-PROTOTYPE>
              <UUID>88888888-0000-0000-0000-00000000000a</UUID>
              <SHORT-NAME>InPort</SHORT-NAME>
              <REQUIRED-INTERFACE-TREF>/If/InIf</REQUIRED-INTERFACE-TREF>
              <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
            </R-PORT-PROTOTYPE>
          </PORTS>
        </APPLICATION-SW-COMPONENT-TYPE>
        <ASSEMBLY-SW-CONNECTOR>
          <UUID>66666666-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>Conn</SHORT-NAME>
          <PROVIDER-IREF>
            <CONTEXT-COMPONENT-REF>/Pkg/{swc}</CONTEXT-COMPONENT-REF>
            <TARGET-P-PORT-REF>/Pkg/{swc}/OutPort</TARGET-P-PORT-REF>
          </PROVIDER-IREF>
          <REQUESTER-IREF>
            <CONTEXT-COMPONENT-REF>/Pkg/Receiver</CONTEXT-COMPONENT-REF>
            <TARGET-R-PORT-REF>/Pkg/Receiver/InPort</TARGET-R-PORT-REF>
          </REQUESTER-IREF>
        </ASSEMBLY-SW-CONNECTOR>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""

BASE = TEMPLATE.format(ns=AUTOSAR_NS, swc="Sender")
TARGET = TEMPLATE.format(ns=AUTOSAR_NS, swc="SenderV2")


def _parse(tmp_path: Path, text: str, name: str = "sample.arxml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return parse_arxml(str(path))


def test_tool_catalogue_lists_the_six_deterministic_tools():
    catalogue = tool_catalogue()
    names = {t["name"] for t in catalogue["tools"]}
    assert names == {"validate_arxml", "resolve_arxml_references", "query_arxml_path",
                     "diff_arxml_versions", "trace_communication_path", "analyze_change_impact"}
    assert catalogue["count"] == 6
    assert all(t["mutating"] is False for t in catalogue["tools"])


def test_validate_tool_returns_a_validation_result(tmp_path: Path):
    result = validate(_parse(tmp_path, BASE))
    assert result["tool"] == "validate_arxml"
    assert result["checks"]
    assert "summary" in result


def test_resolve_references_reports_what_is_resolved_and_what_is_not(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = resolve_arxml_references(topo)
    assert result["tool"] == "resolve_arxml_references"
    kinds = {r["kind"] for r in result["resolved"]}
    assert "port_to_interface" in kinds
    assert "connector_provider_port" in kinds
    assert result["counts"]["resolved"] > 0
    for entry in result["unresolved"]:
        assert entry["reason"]


def test_query_path_finds_an_element_and_its_position(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = query_arxml_path(topo, "/Pkg/Sender/OutPort")
    assert result["status"] == "ok"
    assert result["element"]["kind"] == "port"
    assert result["element"]["line_start"] > 0
    assert result["element"]["uuid"]


def test_query_path_reports_a_miss_without_inventing_structure(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = query_arxml_path(topo, "/Pkg/Nope/Missing")
    assert result["status"] == "not_found"
    assert result["searched"]["path"] == "/Pkg/Nope/Missing"
    assert "no element matches" in result["error"]


def test_query_path_rejects_a_kind_mismatch(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = query_arxml_path(topo, "/Pkg/Sender/OutPort", kind="component")
    assert result["status"] == "not_found"
    assert "is a port" in result["error"]


def test_diff_reports_added_removed_and_modified(tmp_path: Path):
    base = _parse(tmp_path, BASE, "base.arxml")
    target = _parse(tmp_path, TARGET, "target.arxml")
    result = diff_arxml_versions(base, target)
    assert result["tool"] == "diff_arxml_versions"
    assert any(key.endswith("Sender") for key in result["removed"])
    assert any(key.endswith("SenderV2") for key in result["added"])
    assert result["counts"]["removed"] >= 1
    assert result["counts"]["added"] >= 1


def test_trace_communication_path_follows_the_documented_connector(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = trace_communication_path(topo, "/Pkg/Sender/OutPort", "/Pkg/Receiver/InPort")
    assert result["status"] == "ok"
    assert result["paths"]
    assert result["paths"][0]["nodes"][0] == "/Pkg/Sender/OutPort"


def test_trace_communication_path_reports_a_miss(tmp_path: Path):
    topo = _parse(tmp_path, BASE)
    result = trace_communication_path(topo, "/Pkg/Sender/OutPort", "/Pkg/Nowhere/InPort")
    assert result["status"] == "not_found"
    assert result["searched"]["target"] == "/Pkg/Nowhere/InPort"


def test_analyze_change_impact_lists_the_dependents(tmp_path: Path):
    base = _parse(tmp_path, BASE, "base.arxml")
    target = _parse(tmp_path, TARGET, "target.arxml")
    result = analyze_change_impact(base, target)
    assert result["tool"] == "analyze_change_impact"
    assert result["impacted"]
    assert result["counts"]["changed"] > 0
    kinds = {i["change"] for i in result["impacted"]}
    assert "added" in kinds or "removed" in kinds


def test_analyze_change_impact_can_narrow_to_one_element(tmp_path: Path):
    base = _parse(tmp_path, BASE, "base.arxml")
    target = _parse(tmp_path, TARGET, "target.arxml")
    result = analyze_change_impact(base, target, element="/Pkg/Sender/OutPort")
    assert result["element"] == "/Pkg/Sender/OutPort"
    assert all("Sender/OutPort" in i["name"] or i["dependents"] for i in result["impacted"])
