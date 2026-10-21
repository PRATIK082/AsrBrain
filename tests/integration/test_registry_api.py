"""Integration tests for the additive v2 registry and job API.

The registry lives in its own database file, so these tests point
`settings.registry_db` at a temporary path and restore it afterwards. The v1
routes are checked at the end to prove nothing regressed.
"""
import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from src.config.settings import settings


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "registry_db", str(tmp_path / "registry.db"))
    yield str(tmp_path / "registry.db")
    from src.registry.store import RegistryStore
    from src.registry.jobs import JobStore
    RegistryStore(settings.registry_db).close()
    JobStore(settings.registry_db).close()


def test_registry_health_reports_the_schema_version(registry):
    c = TestClient(app)
    r = c.get("/api/v2/registry/health")
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    assert d["schema_version"] >= 1


def test_project_workspace_artifact_version_and_location(registry):
    c = TestClient(app)
    r = c.post("/api/v2/registry/projects", json={"id": "p1", "name": "Demo ECU"})
    assert r.status_code == 200
    assert r.json()["id"] == "p1"

    r = c.post("/api/v2/registry/workspaces",
               json={"id": "w1", "project_id": "p1", "name": "SWC", "scope": "CanIf"})
    assert r.status_code == 200

    r = c.post("/api/v2/registry/artifacts", json={
        "id": "a1", "project_id": "p1", "workspace_id": "w1", "kind": "spec",
        "name": "CanIf_TPS.pdf", "content_hash": "abc123", "branch": "main",
        "autosar_release": "R22-11"})
    assert r.status_code == 200
    assert r.json()["content_hash"] == "abc123"

    r = c.post("/api/v2/registry/artifact-versions", json={
        "artifact_id": "a1", "version_label": "R22-11", "size_bytes": 10,
        "extractor_name": "pymupdf", "extraction_confidence": 0.97})
    assert r.status_code == 200
    version_id = r.json()["id"]
    assert r.json()["extraction_confidence"] == 0.97

    r = c.post("/api/v2/registry/source-locations", json={
        "artifact_version_id": version_id, "locator_type": "pdf_page",
        "locator": "pdf://a1/page/42", "page_start": 42, "section": "4.1.2",
        "module": "CanIf", "snippet": "The signal shall be transmitted."})
    assert r.status_code == 200
    assert r.json()["page_start"] == 42
    location_id = r.json()["id"]

    r = c.post("/api/v2/registry/citations", json={
        "source_location_id": location_id, "answer_id": "ans-1",
        "label": "E1", "claim": "Signals are transmitted periodically."})
    assert r.status_code == 200
    assert r.json()["label"] == "E1"

    assert len(c.get("/api/v2/registry/projects").json()["projects"]) == 1
    assert len(c.get("/api/v2/registry/artifacts?project_id=p1").json()["artifacts"]) == 1
    assert len(c.get("/api/v2/registry/citations?answer_id=ans-1").json()["citations"]) == 1


def test_a_workspace_for_an_unknown_project_is_rejected(registry):
    c = TestClient(app)
    r = c.post("/api/v2/registry/workspaces",
               json={"project_id": "nope", "name": "orphan"})
    assert r.status_code == 400
    assert "detail" in r.json()


def test_jobs_can_be_enqueued_and_listed(registry):
    c = TestClient(app)
    r = c.post("/api/v2/jobs", json={"kind": "ingest",
                                      "payload": {"path": "a.pdf"}})
    assert r.status_code == 200
    job_id = r.json()["id"]
    assert r.json()["status"] == "queued"

    listed = c.get("/api/v2/jobs").json()
    assert listed["counts"]["queued"] == 1
    assert any(j["id"] == job_id for j in listed["jobs"])

    assert c.get(f"/api/v2/jobs/{job_id}").status_code == 200
    assert c.get("/api/v2/jobs/does-not-exist").status_code == 404


def test_v1_routes_are_unaffected(registry):
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/assistant/capabilities").status_code == 200
    assert c.get("/api/assistant/prompts").status_code == 200
    assert c.get("/api/v2/modules").status_code == 200
