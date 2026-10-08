"""Enterprise Phase 2 tests: security, ARXML, diff, code advisory, routing."""
from __future__ import annotations


def _arxml_sample(tmp_path, name="sample.arxml"):
    p = tmp_path / name
    p.write_text("""<AUTOSAR SCHEMA-VERSION="4.4.0">
  <AR-PACKAGES><AR-PACKAGE><SHORT-NAME>Pkg</SHORT-NAME><ELEMENTS>
    <APPLICATION-SW-COMPONENT-TYPE><SHORT-NAME>BrakeCtrl</SHORT-NAME>
      <PORTS>
        <R-PORT-PROTOTYPE><SHORT-NAME>VehicleSpeed</SHORT-NAME>
          <REQUIRED-INTERFACE-TREF DEST="SENDER-RECEIVER-INTERFACE">/Pkg/VehSpeed_I</REQUIRED-INTERFACE-TREF>
        </R-PORT-PROTOTYPE>
        <P-PORT-PROTOTYPE><SHORT-NAME>BrakeCmd</SHORT-NAME>
          <PROVIDED-INTERFACE-TREF DEST="SENDER-RECEIVER-INTERFACE">/Pkg/Brake_I</PROVIDED-INTERFACE-TREF>
        </P-PORT-PROTOTYPE>
      </PORTS>
      <INTERNAL-BEHAVIORS><INTERNAL-BEHAVIOR><SHORT-NAME>IB1</SHORT-NAME>
        <RUNNABLES><RUNNABLE-ENTITY><SHORT-NAME>RE_Calc</SHORT-NAME><SYMBOL>RCalc</SYMBOL></RUNNABLE-ENTITY></RUNNABLES>
      </INTERNAL-BEHAVIOR></INTERNAL-BEHAVIORS>
    </APPLICATION-SW-COMPONENT-TYPE>
    <SENDER-RECEIVER-INTERFACE><SHORT-NAME>VehSpeed_I</SHORT-NAME>
      <DATA-ELEMENTS><VARIABLE-DATA-PROTOTYPE><SHORT-NAME>speed</SHORT-NAME></VARIABLE-DATA-PROTOTYPE></DATA-ELEMENTS>
    </SENDER-RECEIVER-INTERFACE>
  </ELEMENTS></AR-PACKAGE></AR-PACKAGES></AUTOSAR>""")
    return str(p)


def test_security_tenant_denial():
    from src.security.context import SecurityContext, check_access
    ctx = SecurityContext(user_id="u", tenant_id="a", audit_request_id="1")
    ok, _ = check_access(ctx, {"tenant_id": "b"})
    assert ok is False
    ok2, _ = check_access(ctx, {"tenant_id": "a"})
    assert ok2 is True


def test_policy_arxml_local_only():
    from src.security.context import SecurityContext
    from src.security.policy import classify_content, routing_decision
    a = classify_content("<APPLICATION-SW-COMPONENT-TYPE>x</APPLICATION-SW-COMPONENT-TYPE>", "ecu.arxml")
    assert a.arxml_detected and a.cloud_eligible is False
    ctx = SecurityContext(user_id="u", tenant_id="t", cloud_policy="cloud_allowed", audit_request_id="1")
    assert routing_decision(ctx, a)["route"] == "local"


def test_redaction_roundtrip():
    from src.security.redaction import redact, restore
    r, m = redact("contact a@b.com ecu 10.1.2.3", project_hint="")
    assert "<EMAIL_001>" in r and m
    assert restore(r, m) == "contact a@b.com ecu 10.1.2.3"


def test_arxml_parse_topology(tmp_path):
    from src.ingestion.arxml import parse_arxml, export_graph
    topo = parse_arxml(_arxml_sample(tmp_path))
    assert topo.components and topo.ports and topo.interfaces and topo.runnables
    assert any(p.direction == "R" for p in topo.ports)
    g = export_graph(topo)
    assert any(e["rel"] == "HAS_PORT" for e in g["edges"])
    assert all(e["is_inferred"] is False for e in g["edges"])


def test_arxml_rejects_doctype(tmp_path):
    from src.ingestion.arxml import parse_arxml
    p = tmp_path / "evil.arxml"
    p.write_text('<!DOCTYPE foo [<!ENTITY x "y">]><AUTOSAR></AUTOSAR>')
    assert parse_arxml(str(p)).artifact.parse_status == "rejected"


def test_diff_records():
    from src.diff import diff_records
    out = diff_records([{"entity_key": "A", "normalized": "1", "evidence_ids": ["b1"]}],
                       [{"entity_key": "A", "normalized": "2", "evidence_ids": ["t1"]},
                        {"entity_key": "B", "normalized": "x", "evidence_ids": ["t2"]}], "api")
    by = {d.entity_key: d.change_type for d in out}
    assert by == {"A": "modified", "B": "added"}


def test_code_advisory_labels():
    from src.code_intelligence import preflight_checks
    f = preflight_checks("void f(){ char *p = malloc(4); goto end; end:; }")
    assert f and all("Advisory finding" in x.message for x in f)
    assert not any("compliant" in x.message.lower() for x in f)


def test_model_router_local_only_tasks():
    from src.security.context import SecurityContext
    from src.security.policy import classify_content
    from src.model_routing import route
    ctx = SecurityContext(user_id="u", tenant_id="t", cloud_policy="cloud_allowed", audit_request_id="1")
    a = classify_content("public text", "spec.pdf", declared="public")
    assert route("code_review", ctx, a)["route"] in ("local", "cloud")
    ctx2 = SecurityContext(user_id="u", tenant_id="t", cloud_policy="local_only", audit_request_id="1")
    assert route("code_review", ctx2, a)["route"] == "local"


def test_plugin_registry_isolation():
    from src.plugins import REGISTRY
    from src.security.context import SecurityContext
    ctx = SecurityContext(user_id="u", tenant_id="t1", project_id="p",
                          allowed_vendor_scopes=["generic_autosar"], audit_request_id="1")
    assert REGISTRY.active_for(ctx) == []
