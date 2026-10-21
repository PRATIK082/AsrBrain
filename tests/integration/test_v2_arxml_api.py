"""Integration tests for the v2 ARXML API.

The v1 routes must keep working exactly as before (ADR-0008).
"""
from fastapi.testclient import TestClient

from apps.api.main import app

AUTOSAR_NS = "http://autosar.org/schema/r4.0"

SAMPLE = f"""<?xml version="1.0" encoding="UTF-8"?>
<AUTOSAR xmlns="{AUTOSAR_NS}" SCHEMA-VERSION="R22-11">
  <AR-PACKAGES>
    <AR-PACKAGE>
      <SHORT-NAME>Pkg</SHORT-NAME>
      <ELEMENTS>
        <APPLICATION-SW-COMPONENT-TYPE>
          <UUID>11111111-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>Swc</SHORT-NAME>
          <PORTS>
            <P-PORT-PROTOTYPE>
              <UUID>22222222-0000-0000-0000-00000000000a</UUID>
              <SHORT-NAME>OutPort</SHORT-NAME>
              <PROVIDED-INTERFACE-TREF>/If/OutIf</PROVIDED-INTERFACE-TREF>
              <INTERFACE-TYPE>SENDER-RECEIVER</INTERFACE-TYPE>
            </P-PORT-PROTOTYPE>
          </PORTS>
        </APPLICATION-SW-COMPONENT-TYPE>
        <SENDER-RECEIVER-INTERFACE>
          <UUID>44444444-0000-0000-0000-00000000000a</UUID>
          <SHORT-NAME>OutIf</SHORT-NAME>
        </SENDER-RECEIVER-INTERFACE>
      </ELEMENTS>
    </AR-PACKAGE>
  </AR-PACKAGES>
</AUTOSAR>
"""


def _upload(client: TestClient, tmp_path) -> str:
    path = tmp_path / "sample.arxml"
    path.write_text(SAMPLE, encoding="utf-8")
    with path.open("rb") as handle:
        r = client.post("/api/v2/arxml/upload",
                        files={"file": ("sample.arxml", handle, "application/xml")},
                        data={"tenant": "default", "project": "test"})
    assert r.status_code == 200, r.text
    return r.json()["artifact_id"]


def test_tool_catalogue_is_discoverable():
    c = TestClient(app)
    r = c.get("/api/v2/arxml/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    assert "validate_arxml" in names
    assert "trace_communication_path" in names


def test_upload_parse_and_validate(tmp_path):
    c = TestClient(app)
    artifact_id = _upload(c, tmp_path)

    listing = c.get("/api/v2/arxml/artifacts")
    assert listing.status_code == 200
    assert any(a["artifact_id"] == artifact_id for a in listing.json()["artifacts"])

    result = c.get(f"/api/v2/arxml/{artifact_id}/validate")
    assert result.status_code == 200
    body = result.json()
    assert body["tool"] == "validate_arxml"
    assert body["status"] in {"passed", "passed_with_warnings"}

    refs = c.get(f"/api/v2/arxml/{artifact_id}/references")
    assert refs.status_code == 200
    assert refs.json()["tool"] == "resolve_arxml_references"


def test_query_path_and_tree(tmp_path):
    c = TestClient(app)
    artifact_id = _upload(c, tmp_path)

    found = c.get(f"/api/v2/arxml/{artifact_id}/path", params={"path": "/Pkg/Swc/OutPort"})
    assert found.status_code == 200
    assert found.json()["status"] == "ok"
    assert found.json()["element"]["line_start"] > 0

    missing = c.get(f"/api/v2/arxml/{artifact_id}/path", params={"path": "/Pkg/Nope"})
    assert missing.status_code == 200
    assert missing.json()["status"] == "not_found"

    tree = c.get(f"/api/v2/arxml/{artifact_id}/tree")
    assert tree.status_code == 200
    assert tree.json()["components"]


def test_unknown_artifact_is_a_404():
    c = TestClient(app)
    assert c.get("/api/v2/arxml/does-not-exist/validate").status_code == 404


def test_v1_routes_are_unaffected():
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/assistant/capabilities").status_code == 200
    assert c.get("/api/v2/modules").status_code == 200
