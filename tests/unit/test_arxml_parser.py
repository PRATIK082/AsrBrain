"""Tests for the reworked ARXML parser (ADR-0005).

The parser must be *deterministic and honest*: every element keeps its line
range and UUID, the release is only recorded when the document states it, and
a document that cannot be parsed says so instead of yielding an empty topology
that looks valid.
"""
from pathlib import Path

import pytest

from src.ingestion.arxml import parse_arxml
from src.ingestion.arxml.xml_reader import XmlError, parse_xml

AUTOSAR_NS = "http://autosar.org/schema/r4.0"

SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="{AUTOSAR_NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         SCHEMA-VERSION="R22-11">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Demo</SHORT-NAME>
      <AR-PACKAGES>
        <AR-PACKAGE>
          <SHORT-NAME>Swc</SHORT-NAME>
          <ELEMENTS>
            <APPLICATION-SW-COMPONENT-TYPE>
              <UUID>11111111-2222-3333-4444-555555555555</UUID>
              <SHORT-NAME>SenderSwc</SHORT-NAME>
              <PORTS>
                <P-PORT-PROTOTYPE>
                  <UUID>aaaaaaaa-0000-0000-0000-000000000001</UUID>
                  <SHORT-NAME>SignalPort</SHORT-NAME>
                  <PROVIDED-INTERFACE-TREF>/Interfaces/SenderIf</PROVIDED-INTERFACE-TREF>
                  <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
                </P-PORT-PROTOTYPE>
                <R-PORT-PROTOTYPE>
                  <UUID>aaaaaaaa-0000-0000-0000-000000000002</UUID>
                  <SHORT-NAME>ReceiverPort</SHORT-NAME>
                  <REQUIRED-INTERFACE-TREF>/Interfaces/ReceiverIf</REQUIRED-INTERFACE-TREF>
                  <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
                </R-PORT-PROTOTYPE>
              </PORTS>
              <INTERNAL-BEHAVIORS>
                <INTERNAL-BEHAVIOR>
                  <SHORT-NAME>MainBehavior</SHORT-NAME>
                </INTERNAL-BEHAVIOR>
              </INTERNAL-BEHAVIORS>
              <IMPLEMENTATION>
                <CODE>
                  <RUNNABLE-ENTITY>
                    <SHORT-NAME>SendRunnable</SHORT-NAME>
                    <SYMBOL>SendRunnable</SYMBOL>
                  </RUNNABLE-ENTITY>
                </CODE>
              </IMPLEMENTATION>
            </APPLICATION-SW-COMPONENT-TYPE>
            <SENDER-RECEIVER-INTERFACE>
              <UUID>bbbbbbbb-0000-0000-0000-000000000001</UUID>
              <SHORT-NAME>SenderIf</SHORT-NAME>
              <DATA-ELEMENTS>
                <VARIABLE-DATA-PROTOTYPE>
                  <SHORT-NAME>Signal</SHORT-NAME>
                </VARIABLE-DATA-PROTOTYPE>
              </DATA-ELEMENTS>
            </SENDER-RECEIVER-INTERFACE>
          </ELEMENTS>
        </AR-PACKAGE>
      </AR-PACKAGES>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


@pytest.fixture()
def sample_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo.arxml"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def test_parser_keeps_the_line_range_of_every_element(sample_file: Path):
    topo = parse_arxml(str(sample_file))
    assert topo.artifact.parse_status == "ok"
    component = topo.components[0]
    assert component.line_start > 0
    assert component.line_end >= component.line_start
    # The component starts on the APPLICATION-SW-COMPONENT-TYPE line.
    lines = SAMPLE.splitlines()
    assert "APPLICATION-SW-COMPONENT-TYPE" in lines[component.line_start - 1]
    port = topo.ports[0]
    assert "P-PORT-PROTOTYPE" in lines[port.line_start - 1]


def test_parser_captures_uuids(sample_file: Path):
    topo = parse_arxml(str(sample_file))
    assert topo.components[0].uuid == "11111111-2222-3333-4444-555555555555"
    assert topo.ports[0].uuid == "aaaaaaaa-0000-0000-0000-000000000001"
    assert topo.interfaces[0].uuid == "bbbbbbbb-0000-0000-0000-000000000001"


def test_qualified_names_follow_the_package_chain(sample_file: Path):
    topo = parse_arxml(str(sample_file))
    assert topo.components[0].qualified_name == "/Demo/Swc/SenderSwc"
    assert topo.ports[0].qualified_name == "/Demo/Swc/SenderSwc/SignalPort"
    assert topo.interfaces[0].qualified_name == "/Demo/Swc/SenderIf"
    assert topo.runnables[0].qualified_name == "/Demo/Swc/SenderSwc/SendRunnable"


def test_release_is_taken_from_the_document_and_never_invented(sample_file: Path):
    topo = parse_arxml(str(sample_file))
    assert topo.artifact.autosar_release == "R22-11"

    # A document that states no release must leave the field empty.
    other = sample_file.read_text(encoding="utf-8").replace(' SCHEMA-VERSION="R22-11"', "")
    path = sample_file.parent / "no-release.arxml"
    path.write_text(other, encoding="utf-8")
    topo2 = parse_arxml(str(path))
    assert not topo2.artifact.autosar_release
    assert any("release" in w for w in topo2.artifact.validation_warnings)


def test_explicit_release_argument_wins(sample_file: Path):
    topo = parse_arxml(str(sample_file), autosar_release="R24-11")
    assert topo.artifact.autosar_release == "R24-11"


def test_previously_dead_fields_are_now_populated(sample_file: Path):
    topo = parse_arxml(str(sample_file))
    port = next(p for p in topo.ports if p.short_name == "SignalPort")
    assert port.direction == "P"
    assert port.interface_ref == "/Interfaces/SenderIf"
    assert port.interface_type == "SENDER-RECEIVER"

    component = topo.components[0]
    assert component.internal_behaviors == ["MainBehavior"]
    assert component.ports == [p.qualified_name for p in topo.ports]
    assert component.runnables == [r.qualified_name for r in topo.runnables]

    runnable = topo.runnables[0]
    assert runnable.symbol == "SendRunnable"
    assert runnable.line_start > 0


def test_doctype_declarations_are_rejected(tmp_path: Path):
    path = tmp_path / "evil.arxml"
    path.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>\n'
        '<AUTOSAR><AR-PACKAGES/></AUTOSAR>\n',
        encoding="utf-8",
    )
    topo = parse_arxml(str(path))
    assert topo.artifact.parse_status == "rejected"
    assert topo.components == []


def test_malformed_xml_fails_loudly(tmp_path: Path):
    path = tmp_path / "broken.arxml"
    path.write_text("<AUTOSAR><AR-PACKAGES></AUTOSAR>", encoding="utf-8")
    topo = parse_arxml(str(path))
    assert topo.artifact.parse_status == "failed"
    assert topo.artifact.validation_warnings


def test_xml_reader_reports_the_namespace_and_schema_version(sample_file: Path):
    document = parse_xml(sample_file.read_bytes())
    assert document.namespace == AUTOSAR_NS
    assert document.schema_version == "R22-11"


def test_xml_reader_raises_on_malformed_input():
    with pytest.raises(XmlError):
        parse_xml(b"<a><b></a>")
    with pytest.raises(XmlError):
        parse_xml(b"")


def test_artifact_id_is_content_addressed(sample_file: Path, tmp_path: Path):
    topo = parse_arxml(str(sample_file))
    assert topo.artifact.artifact_id.startswith("arxml-")
    copy = tmp_path / "copy.arxml"
    copy.write_text(SAMPLE, encoding="utf-8")
    assert parse_arxml(str(copy)).artifact.artifact_id == topo.artifact.artifact_id
