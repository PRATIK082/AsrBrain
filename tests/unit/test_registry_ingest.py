"""Unit tests for the artifact-scoped ingestion bridge (Phase 3).

Ingestion is additive: the canonical store is read, never written. Every
indexed chunk of a document gets exactly one `SourceLocation`, and an answer's
evidence is bound to those locations — or reported as unresolved.
"""
import pytest

from src.ingestion.registry_ingest import (bind_citations, ingest_document,
                                           register_artifact_bytes)
from src.objects import LocalObjectStore
from src.registry import RegistryStore


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(str(tmp_path / "registry.db"))
    yield s
    s.close()


@pytest.fixture()
def obj_store(tmp_path):
    return LocalObjectStore(root=str(tmp_path / "objects"))


def _chunk(chunk_id="c1", page=12, section="4.1.2 Signal", release="R22-11",
           module="Com", text="The signal shall be transmitted periodically.",
           sha="", source_pdf="pdf\\AUTOSAR_TPS.pdf"):
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "source_pdf": source_pdf,
        "sha256": sha,
        "page_start": page,
        "page_end": page + 1,
        "autosar_release": release,
        "module": module,
        "section_number": "4.1.2",
        "section_title": "Signal",
        "normalized_text": text,
        "text": text,
    }


def _write_pdf(tmp_path, name="spec.pdf", body=b"%PDF-1.7 body"):
    p = tmp_path / name
    p.write_bytes(body)
    return str(p)


def _sha_of(path: str) -> str:
    import hashlib
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_register_artifact_bytes_creates_an_artifact_and_a_version(store, obj_store):
    store.create_project("Project", project_id="p1")
    artifact, version, ref = register_artifact_bytes(
        store, obj_store,
        data=b"spec bytes",
        project_id="p1",
        name="AUTOSAR TPS",
        kind="spec",
        source_uri="pdf/AUTOSAR_TPS.pdf",
        extractor_name="asrbrain-ingest",
        extractor_version="1",
    )
    assert artifact.content_hash == ref.sha256
    assert artifact.kind == "spec"
    assert version.artifact_id == artifact.id
    assert version.size_bytes == len(b"spec bytes")
    assert version.storage_uri == ref.uri
    assert version.extractor_name == "asrbrain-ingest"
    assert version.extraction_confidence == 1.0


def test_ingest_document_registers_one_source_location_per_chunk(store, obj_store, tmp_path):
    store.create_project("Project", project_id="p1")
    path = _write_pdf(tmp_path)
    sha = _sha_of(path)
    chunks = [_chunk("c1", 12, sha=sha), _chunk("c2", 30, sha=sha)]
    result = ingest_document(
        store, obj_store,
        path=path,
        project_id="p1",
        name="AUTOSAR TPS",
        canonical_db="",
        chunks=chunks,
    )
    assert result["chunks_seen"] == 2
    assert result["source_locations_created"] == 2

    locations = store.list_source_locations(result["artifact_version_id"])
    assert len(locations) == 2
    by_chunk = {loc.chunk_id: loc for loc in locations}
    assert set(by_chunk) == {"c1", "c2"}
    first = by_chunk["c1"]
    assert first.locator_type == "pdf_page"
    assert first.locator == "pdf://doc-1/page/12"
    assert first.page_start == 12
    assert first.page_end == 13
    assert first.release == "R22-11"
    assert first.module == "Com"
    assert "signal" in first.snippet.lower()


def test_ingest_document_is_idempotent_for_the_same_version(store, obj_store, tmp_path):
    store.create_project("Project", project_id="p1")
    path = _write_pdf(tmp_path)
    sha = _sha_of(path)
    chunks = [_chunk("c1", 12, sha=sha)]
    first = ingest_document(store, obj_store, path=path, project_id="p1",
                            canonical_db="", chunks=chunks)
    # A second ingest produces a new version, so the chunk is registered again
    # for that version — but never twice for the same version.
    again = ingest_document(store, obj_store, path=path, project_id="p1",
                            canonical_db="", chunks=chunks)
    assert again["artifact_version_id"] != first["artifact_version_id"]
    assert again["source_locations_created"] == 1
    assert len(store.list_source_locations(first["artifact_version_id"])) == 1


def test_ingest_document_reports_a_missing_file(store, obj_store, tmp_path):
    store.create_project("Project", project_id="p1")
    with pytest.raises(FileNotFoundError):
        ingest_document(store, obj_store, path=str(tmp_path / "nope.pdf"),
                        project_id="p1", canonical_db="", chunks=[])


def test_bind_citations_resolves_evidence_to_registered_locations(store, obj_store, tmp_path):
    store.create_project("Project", project_id="p1")
    path = _write_pdf(tmp_path)
    sha = _sha_of(path)
    result = ingest_document(store, obj_store, path=path, project_id="p1",
                             canonical_db="", chunks=[_chunk("c1", 12, sha=sha)])
    evidence = [{"label": "E1", "source_id": "c1", "source_pdf": "pdf\\AUTOSAR_TPS.pdf",
                 "page": 12, "claim": "the signal is transmitted periodically"}]
    bound = bind_citations(store, "answer-1", evidence,
                           conversation_id="conv-1", message_id="msg-1")
    assert bound["bound"] == 1
    assert bound["unresolved_count"] == 0
    citation = bound["citations"][0]
    assert citation.label == "E1"
    assert citation.answer_id == "answer-1"
    assert citation.artifact_version_id == result["artifact_version_id"]

    stored = store.list_citations("answer-1")
    assert len(stored) == 1
    location = store.get_source_location(citation.source_location_id)
    assert location.chunk_id == "c1"


def test_bind_citations_reports_unresolved_evidence_instead_of_guessing(store):
    evidence = [{"label": "E1", "source_id": "not-registered", "source_pdf": "x.pdf",
                 "page": 3}]
    bound = bind_citations(store, "answer-2", evidence)
    assert bound["bound"] == 0
    assert bound["unresolved_count"] == 1
    assert bound["citations"] == []
    assert bound["unresolved"][0]["label"] == "E1"
    assert bound["unresolved"][0]["reason"]
