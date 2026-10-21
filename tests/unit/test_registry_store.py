"""Unit tests for the provenance-first registry store (ADR-0002).

The registry is the record of *what was used, from which version, and how it
was extracted*. These tests pin that contract: every row carries its
provenance, and nothing is stored without an id, a version or a location.
"""
import pytest

from src.registry.jobs import JobStore, run_worker
from src.registry.store import RegistryStore


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(str(tmp_path / "registry.db"))
    yield s
    s.close()


def test_project_and_workspace_round_trip(store):
    project = store.create_project("Demo ECU", project_id="p1", owner="qa")
    assert project.id == "p1"
    assert store.get_project("p1").name == "Demo ECU"
    assert [p.id for p in store.list_projects()] == ["p1"]

    ws = store.create_workspace(project_id="p1", name="SWC workspace",
                                workspace_id="w1", scope="CanIf")
    assert ws.project_id == "p1"
    assert store.get_workspace("w1").scope == "CanIf"
    assert [w.id for w in store.list_workspaces(project_id="p1")] == ["w1"]


def test_artifact_keeps_its_provenance(store):
    store.create_project("Demo", project_id="p1")
    art = store.register_artifact(
        project_id="p1", name="CanIf_TPS.pdf", kind="spec",
        artifact_id="a1", content_hash="deadbeef", owner="qa",
        branch="main", autosar_release="R22-11",
        data_classification="internal")
    assert art.content_hash == "deadbeef"
    assert art.branch == "main"
    assert art.autosar_release == "R22-11"
    assert art.lifecycle_state == "active"

    version = store.create_artifact_version(
        artifact_id="a1", version_label="R22-11", content_hash="deadbeef",
        size_bytes=1234, storage_uri="file://objects/deadbeef",
        extractor_name="pymupdf", extractor_version="1.24",
        extraction_confidence=0.98)
    assert version.artifact_id == "a1"
    assert version.extraction_confidence == 0.98
    assert store.get_artifact_version(version.id).extractor_name == "pymupdf"
    assert [v.id for v in store.list_artifact_versions(artifact_id="a1")] == [version.id]


def test_source_location_is_the_address_of_a_passage(store):
    store.create_project("Demo", project_id="p1")
    store.register_artifact(project_id="p1", name="a.pdf", artifact_id="a1")
    version = store.create_artifact_version(artifact_id="a1", version_label="v1")
    loc = store.add_source_location(
        artifact_version_id=version.id, locator_type="pdf_page",
        locator="pdf://a1/page/42", page_start=42, page_end=43,
        section="4.1.2", release="R22-11", module="CanIf",
        snippet="The signal shall be transmitted …")
    assert loc.page_start == 42
    assert loc.section == "4.1.2"
    assert loc.snippet.startswith("The signal")
    assert [x.id for x in store.list_source_locations(
        artifact_version_id=version.id)] == [loc.id]


def test_citation_binds_a_claim_to_a_location(store):
    store.create_project("Demo", project_id="p1")
    store.register_artifact(project_id="p1", name="a.pdf", artifact_id="a1")
    version = store.create_artifact_version(artifact_id="a1", version_label="v1")
    loc = store.add_source_location(artifact_version_id=version.id,
                                    locator_type="pdf_page", locator="p42")
    cit = store.add_citation(source_location_id=loc.id, answer_id="ans-1",
                             label="E1", claim="Signals are transmitted periodically.")
    assert cit.answer_id == "ans-1"
    assert cit.label == "E1"
    assert [c.id for c in store.list_citations(answer_id="ans-1")] == [cit.id]


def test_evidence_claim_carries_its_status_and_missing_artifacts(store):
    claim = store.add_evidence_claim(
        claim="The timeout parameter is not specified in the corpus.",
        answer_id="ans-1", claim_type="fact",
        status="INSUFFICIENT_EVIDENCE",
        reason="no passage mentions the parameter",
        missing=["ComRxTimeout value"], checked=["citation validity"])
    assert claim.status == "INSUFFICIENT_EVIDENCE"
    assert claim.missing == ["ComRxTimeout value"]
    assert claim.checked == ["citation validity"]
    assert [c.id for c in store.list_evidence_claims(answer_id="ans-1")] == [claim.id]


def test_validation_result_records_the_tool_and_its_verdict(store):
    store.create_project("Demo", project_id="p1")
    store.register_artifact(project_id="p1", name="a.arxml", kind="arxml", artifact_id="a1")
    version = store.create_artifact_version(artifact_id="a1", version_label="v1")
    res = store.add_validation_result(
        artifact_version_id=version.id, tool_name="validate_arxml",
        status="failed", severity="warning",
        message="2 unresolved port references", details={"unresolved": 2})
    assert res.tool_name == "validate_arxml"
    assert res.status == "failed"
    assert res.details["unresolved"] == 2


def test_answer_audit_records_what_was_answered(store):
    audit = store.record_answer_audit(
        question="How is a periodic signal transmitted?",
        answer="…", answerability_status="EVIDENCE_SUPPORTED",
        request_id="req-1", conversation_id="c1", model_provider="ollama",
        model_name="qwen3:14b", latency_ms=1234)
    assert audit.answerability_status == "EVIDENCE_SUPPORTED"
    assert audit.request_id == "req-1"
    assert [a.id for a in store.list_answer_audits(conversation_id="c1")] == [audit.id]


def test_jobs_move_through_the_whole_lifecycle(tmp_path):
    jobs = JobStore(str(tmp_path / "registry.db"))
    job = jobs.enqueue("ingest", payload={"path": "a.pdf"})
    assert job.status == "queued"
    assert jobs.get(job.id).payload["path"] == "a.pdf"

    claimed = jobs.claim_next()
    assert claimed is not None and claimed.id == job.id
    assert jobs.claim_next() is None, "a claimed job must not be handed out twice"

    done = jobs.complete(job.id, result={"ok": True})
    assert done.status == "succeeded"
    assert done.result["ok"] is True
    assert jobs.counts() == {"succeeded": 1}


def test_a_failing_job_is_retried_then_marked_failed(tmp_path):
    jobs = JobStore(str(tmp_path / "registry.db"))
    job = jobs.enqueue("boom", max_attempts=2)
    jobs.claim_next()
    again = jobs.fail(job.id, "handler exploded")
    assert again.status == "queued", "the job must be retried while attempts remain"
    jobs.claim_next()
    final = jobs.fail(job.id, "handler exploded again")
    assert final.status == "failed"
    assert "exploded" in final.error


def test_worker_dispatches_by_kind_and_never_dies_on_a_bad_job(tmp_path):
    jobs = JobStore(str(tmp_path / "registry.db"))
    jobs.enqueue("echo", payload={"n": 1})
    jobs.enqueue("unknown-kind")

    processed = run_worker(
        {"echo": lambda job: {"ok": True}},
        db_path=str(tmp_path / "registry.db"),
        max_iterations=10,
        poll_interval_s=0,
        sleep=lambda _s: None,
    )
    assert processed >= 2, "both jobs must be picked up"
    counts = jobs.counts()
    assert counts.get("succeeded") == 1
    assert counts.get("failed") == 1
    # The unknown kind was retried before it was given up on.
    assert processed > 2
