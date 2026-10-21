"""Integration tests for the v2 requirements, tests and traceability API.

The traceability tables live in the registry database, so every test points
`settings.registry_db` at a temporary file. The real
`data/canonical/registry.db` is never opened.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from src.config.settings import settings

REQUIREMENTS_CSV = (
    "req_id,summary,status,owner\n"
    "REQ-1,First requirement,in progress,ana\n"
    "REQ-2,Second requirement,done,bo\n"
)

JUNIT_XML = (
    '<testsuite name="unit" tests="2" time="0.3">'
    '<testcase classname="tests.test_a" name="test_ok" time="0.1"/>'
    '<testcase classname="tests.test_a" name="test_bad" time="0.2">'
    '<failure message="expected 1 got 2">traceback</failure>'
    "</testcase>"
    "</testsuite>"
)


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    db = str(tmp_path / "registry.db")
    # The store applies the migrations on init, so migration 008 lands in the
    # temporary file. monkeypatch restores the previous value afterwards.
    monkeypatch.setattr(settings, "registry_db", db)
    yield db


def _ingest_requirements(c):
    return c.post("/api/v2/requirements/ingest",
                  json={"format": "csv", "content": REQUIREMENTS_CSV})


def test_the_ingestion_adapters_are_listed(registry):
    c = TestClient(app)
    r = c.get("/api/v2/traceability/adapters")
    assert r.status_code == 200
    body = r.json()
    names = [a["name"] for a in body["adapters"]]
    assert "junit_xml" in names
    assert "test_csv" in names
    assert body["count"] == len(body["adapters"])


def test_requirements_are_ingested_from_csv_and_listed(registry):
    c = TestClient(app)
    r = _ingest_requirements(c)
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] == 2
    assert [item["id"] for item in body["requirements"]] == ["REQ-1", "REQ-2"]
    assert body["requirements"][0]["title"] == "First requirement"
    # The status spelling is normalised on the way in.
    assert body["requirements"][0]["status"] == "in-progress"
    assert body["requirements"][1]["status"] == "implemented"

    listed = c.get("/api/v2/requirements")
    assert listed.status_code == 200
    assert listed.json()["count"] == 2
    assert [item["id"] for item in listed.json()["requirements"]] == ["REQ-1", "REQ-2"]


def test_a_single_requirement_is_returned_and_an_unknown_one_is_404(registry):
    c = TestClient(app)
    _ingest_requirements(c)
    r = c.get("/api/v2/requirements/REQ-1")
    assert r.status_code == 200
    assert r.json()["id"] == "REQ-1"
    assert r.json()["title"] == "First requirement"

    missing = c.get("/api/v2/requirements/REQ-does-not-exist")
    assert missing.status_code == 404


def test_a_trace_link_is_proposed_and_then_reviewed(registry):
    c = TestClient(app)
    _ingest_requirements(c)
    created = c.post("/api/v2/traceability/links", json={
        "source_type": "requirement", "source_id": "REQ-1",
        "target_type": "test_case", "target_id": "TC-1",
        "review_state": "proposed",
    })
    assert created.status_code == 200
    link = created.json()
    assert link["review_state"] == "proposed"
    link_id = link["id"]

    reviewed = c.post(f"/api/v2/traceability/links/{link_id}/review",
                      json={"review_state": "approved", "reviewed_by": "qa",
                            "review_note": "checked by hand"})
    assert reviewed.status_code == 200
    assert reviewed.json()["review_state"] == "approved"
    assert reviewed.json()["reviewed_by"] == "qa"
    assert reviewed.json()["review_note"] == "checked by hand"


def test_an_unknown_review_state_is_rejected_when_a_link_is_created(registry):
    c = TestClient(app)
    r = c.post("/api/v2/traceability/links", json={
        "source_type": "requirement", "source_id": "REQ-1",
        "target_type": "test_case", "target_id": "TC-1",
        "review_state": "compliant",
    })
    assert r.status_code == 400


def test_an_unknown_review_state_is_rejected_when_a_link_is_reviewed(registry):
    c = TestClient(app)
    created = c.post("/api/v2/traceability/links", json={
        "source_type": "requirement", "source_id": "REQ-1",
        "target_type": "test_case", "target_id": "TC-1",
    })
    assert created.status_code == 200
    link_id = created.json()["id"]
    r = c.post(f"/api/v2/traceability/links/{link_id}/review",
               json={"review_state": "nonsense"})
    assert r.status_code == 400


def test_junit_results_are_stored_and_clustered(registry):
    c = TestClient(app)
    r = c.post("/api/v2/tests/ingest", json={
        "format": "junit", "content": JUNIT_XML, "run_id": "run-1"})
    assert r.status_code == 200
    body = r.json()
    assert body["test_cases"] == 2
    assert body["results"] == 2
    assert body["run"]["id"] == "run-1"

    runs = c.get("/api/v2/tests/runs")
    assert runs.status_code == 200
    assert runs.json()["count"] == 1

    results = c.get("/api/v2/tests/results")
    assert results.status_code == 200
    assert results.json()["count"] == 2
    assert sorted(item["status"] for item in results.json()["results"]) == ["failed", "passed"]

    clusters = c.get("/api/v2/tests/clusters")
    assert clusters.status_code == 200
    assert clusters.json()["failures"] == 1
    assert clusters.json()["count"] == 1
    assert clusters.json()["clusters"][0]["count"] == 1


def test_a_test_run_id_is_generated_when_none_is_given(registry):
    c = TestClient(app)
    r = c.post("/api/v2/tests/ingest", json={"format": "junit", "content": JUNIT_XML})
    assert r.status_code == 200
    assert r.json()["run"]["id"].startswith("run-")


def test_the_matrix_coverage_and_orphan_reports_answer(registry):
    c = TestClient(app)
    _ingest_requirements(c)
    c.post("/api/v2/traceability/links", json={
        "source_type": "requirement", "source_id": "REQ-1",
        "target_type": "test_case", "target_id": "TC-1",
        "review_state": "approved",
    })

    matrix = c.get("/api/v2/traceability/matrix")
    assert matrix.status_code == 200
    assert matrix.json()["counts"]["requirements"] == 2
    assert matrix.json()["counts"]["links"] == 1

    coverage = c.get("/api/v2/traceability/coverage")
    assert coverage.status_code == 200
    body = coverage.json()
    assert body["requirements"] == 2
    assert body["with_accepted_link"] == 1
    assert body["without_any_link"] == 1
    assert "evidence available for review" in body["statement"]
    assert "compliant" not in body["statement"].lower()

    orphans = c.get("/api/v2/traceability/orphans")
    assert orphans.status_code == 200
    assert "REQ-2" in orphans.json()["orphan_requirements"]


def test_a_finding_can_be_listed(registry):
    c = TestClient(app)
    listed = c.get("/api/v2/findings")
    assert listed.status_code == 200
    body = listed.json()
    assert body["count"] == 0
    assert body["findings"] == []


def test_a_finding_can_be_created_and_listed(registry):
    c = TestClient(app)
    created = c.post("/api/v2/findings", json={
        "project_id": "p1", "title": "Odd behaviour", "severity": "medium",
        "summary": "seen in CI", "review_state": "proposed",
    })
    assert created.status_code == 200
    finding = created.json()
    assert finding["title"] == "Odd behaviour"
    assert finding["severity"] == "medium"
    assert finding["review_state"] == "proposed"

    listed = c.get("/api/v2/findings")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["findings"][0]["id"] == finding["id"]


def test_the_v1_routes_still_work(registry):
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/assistant/capabilities").status_code == 200
