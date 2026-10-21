"""Tests for the deterministic ARXML validator (ADR-0005)."""
from pathlib import Path

from src.ingestion.arxml import parse_arxml
from src.ingestion.arxml.validation import validate_arxml, validation_summary

AUTOSAR_NS = "http://autosar.org/schema/r4.0"

SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="{AUTOSAR_NS}" SCHEMA-VERSION="R22-11">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Pkg</SHORT-NAME>
      <ELEMENTS>
        <APPLICATION-SW-COMPONENT-TYPE>
          <UUID>11111111-2222-3333-4444-555555555555</UUID>
          <SHORT-NAME>Swc</SHORT-NAME>
          <PORTS>
            <P-PORT-PROTOTYPE>
              <UUID>aaaaaaaa-0000-0000-0000-000000000001</UUID>
              <SHORT-NAME>Port</SHORT-NAME>
              <PROVIDED-INTERFACE-TREF>/If/SenderIf</PROVIDED-INTERFACE-TREF>
              <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
            </P-PORT-PROTOTYPE>
          </PORTS>
        </APPLICATION-SW-COMPONENT-TYPE>
        <SENDER-RECEIVER-INTERFACE>
          <UUID>bbbbbbbb-0000-0000-0000-000000000001</UUID>
          <SHORT-NAME>SenderIf</SHORT-NAME>
        </SENDER-RECEIVER-INTERFACE>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


def _topology(tmp_path: Path, text: str = SAMPLE):
    path = tmp_path / "sample.arxml"
    path.write_text(text, encoding="utf-8")
    return parse_arxml(str(path))


def test_validation_reports_every_check_and_passes(tmp_path: Path):
    topo = _topology(tmp_path)
    result = validate_arxml(topo)
    assert result["tool"] == "validate_arxml"
    assert result["status"] in {"passed", "passed_with_warnings"}
    names = {c["check"] for c in result["checks"]}
    assert {"well_formed", "schema_version", "release_declared", "references_resolved",
            "short_names_unique", "required_attributes"} <= names
    assert result["scope"]["components"] == 1
    assert result["scope"]["ports"] == 1
    assert "checks passed" in validation_summary(result)


def test_validation_flags_an_unresolved_reference(tmp_path: Path):
    text = SAMPLE.replace("/If/SenderIf", "/If/DoesNotExist")
    topo = _topology(tmp_path, text)
    result = validate_arxml(topo)
    assert result["status"] == "failed"
    findings = [f for f in result["findings"] if f["check"] == "references_resolved"]
    assert findings
    assert findings[0]["severity"] == "error"
    assert "DoesNotExist" in findings[0]["message"]


def test_validation_warns_when_the_release_is_not_stated(tmp_path: Path):
    text = SAMPLE.replace(' SCHEMA-VERSION="R22-11"', "")
    topo = _topology(tmp_path, text)
    result = validate_arxml(topo)
    releases = [f for f in result["findings"] if f["check"] == "release_declared"]
    assert releases and releases[0]["severity"] == "warning"
    assert "guessed" in releases[0]["message"]


def test_validation_fails_for_a_rejected_document(tmp_path: Path):
    path = tmp_path / "evil.arxml"
    path.write_text('<!DOCTYPE a><AUTOSAR/>', encoding="utf-8")
    result = validate_arxml(parse_arxml(str(path)))
    assert result["status"] == "failed"
    assert any(f["check"] == "well_formed" for f in result["findings"])


def test_validation_warns_about_missing_required_attributes(tmp_path: Path):
    text = SAMPLE.replace("      <UUID>11111111-2222-3333-4444-555555555555</UUID>\n", "")
    topo = _topology(tmp_path, text)
    result = validate_arxml(topo)
    missing = [f for f in result["findings"] if f["check"] == "required_attributes"]
    assert missing
    assert "UUID" in missing[0]["message"]
