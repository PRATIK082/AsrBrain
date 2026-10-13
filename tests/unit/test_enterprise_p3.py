"""P3 tests: tenant filters, VLM provenance, SARIF, eval categories B–Q, API endpoints."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_qdrant_mandatory_filter():
    from src.indexing.qdrant_index import build_mandatory_filter
    from src.security.context import SecurityContext
    import pytest
    with pytest.raises(PermissionError):
        build_mandatory_filter({})
    ctx = SecurityContext(user_id="u", tenant_id="t1", project_id="p1", audit_request_id="1")
    assert build_mandatory_filter(ctx) == {"tenant_id": "t1", "project_id": "p1"}


def test_qdrant_override_denied():
    from src.indexing.qdrant_index import search
    from src.security.context import SecurityContext

    class FakeClient:
        def search(self, **kw):
            return kw["query_filter"]

    ctx = SecurityContext(user_id="u", tenant_id="t1", audit_request_id="1")
    import pytest
    with pytest.raises(PermissionError):
        search(FakeClient(), "c", [0.1], ctx, extra_filter={"tenant_id": "evil"})


def test_opensearch_filter_merge():
    from src.indexing.opensearch_security import secure_search_body, check_write_authorized
    import pytest
    body = secure_search_body({"tenant_id": "t1", "project_id": "p"}, {"query": {"match": {"x": "y"}}})
    terms = body["query"]["bool"]["filter"]
    assert {"term": {"tenant_id": "t1"}} in terms
    with pytest.raises(PermissionError):
        check_write_authorized({"tenant_id": "t1"}, "t2")


def test_vlm_provenance():
    from src.ingestion.vlm import analyze_diagram
    ev = analyze_diagram("fig1.png", caption="Brake arch", page=7, document_id="d1")
    assert ev.is_inferred is True and ev.provenance["page"] == 7
    assert "Supplemental" in ev.provenance["note"] or "supplemental" in ev.provenance["note"].lower()


def test_sarif_ingest():
    from src.code_intelligence import ingest_sarif
    sarif = {"runs": [{"tool": {"driver": {"name": "Demo", "version": "1"}},
                       "results": [{"ruleId": "R1", "message": {"text": "issue"},
                                    "locations": [{"physicalLocation": {
                                        "artifactLocation": {"uri": "a.c"},
                                        "region": {"startLine": 3}}}]}]}]}
    f = ingest_sarif(sarif)
    assert f[0].level == "tool_reported" and f[0].location == "a.c:3"


def test_eval_categories_cover_b_to_q():
    from src.evaluation.enterprise_categories import CATEGORIES, EXTRA_SEED, full_seed
    assert set(CATEGORIES) >= set(list("ABCDEFGHIJKLMNOPQ"))
    cats = {q["category"] for q in EXTRA_SEED}
    assert {"B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q"} <= cats
    assert len(full_seed([])) == len(EXTRA_SEED)


def test_api_sarif_and_diagram():
    from apps.api.main import app
    c = TestClient(app)
    r = c.post("/api/code/sarif", json={"sarif": {"runs": []}})
    assert r.status_code == 200 and "disclaimer" in r.json()
    r2 = c.post("/api/diagrams/analyze", json={"image_path": "x.png", "page": 2})
    assert r2.status_code == 200 and r2.json()["is_inferred"] is True
    r3 = c.post("/api/diff", json={"base": [], "target": [{"entity_key": "X", "normalized": "1"}]})
    assert r3.status_code == 200 and r3.json()[0]["change_type"] == "added"
