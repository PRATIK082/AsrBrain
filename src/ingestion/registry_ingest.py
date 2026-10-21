"""Artifact-scoped ingestion bridge (Phase 3).

Bridges the two worlds the product has today:

* the **canonical store** (`data/canonical/canonical.db`) — the retrieval source
  of truth, holding the chunk rows the retriever actually uses;
* the **registry** (`data/canonical/registry.db`) — the provenance spine that
  says *where* a passage came from, in which version of which artifact.

Ingestion is **additive**: the canonical store is never modified. The registry
gains an `Artifact`, an `ArtifactVersion` and one `SourceLocation` per indexed
chunk. The bytes themselves go to the object store, which holds bytes only
(ADR-0012).

Citations are bound the same way — an answer's evidence chunk is resolved to
the exact `SourceLocation` that was registered for it. Evidence that cannot be
resolved is **reported as unresolved**, never cited to a guessed location.
"""
from __future__ import annotations

import os
from pathlib import Path

from ..objects import ObjectStore, default_object_store
from ..registry import RegistryStore

__all__ = [
    "bind_citations",
    "ingest_document",
    "register_artifact_bytes",
    "source_location_for_chunk",
]

# The chunk text kept as a preview. The full text stays in the canonical store.
SNIPPET_CHARS = 400


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _section(chunk: dict) -> str:
    number = str(chunk.get("section_number") or "").strip()
    title = str(chunk.get("section_title") or "").strip()
    return f"{number} {title}".strip()


def _chunks_for_document(chunks: list[dict], source_path: str, sha: str) -> list[dict]:
    """The canonical chunks that came from one file.

    The canonical store records the document's SHA-256 on every chunk, so the
    hash is the authoritative match. The file name is only a fallback for
    stores written before the hash was recorded.
    """
    by_hash = [c for c in chunks if sha and str(c.get("sha256") or "") == sha]
    if by_hash:
        return by_hash
    name = os.path.basename(source_path).lower()
    return [c for c in chunks if os.path.basename(str(c.get("source_pdf") or "")).lower() == name]


def register_artifact_bytes(registry: RegistryStore, obj_store: ObjectStore, *,
                             data: bytes, project_id: str, name: str,
                             kind: str = "spec", source_uri: str = "",
                             workspace_id: str = "", owner: str = "",
                             branch: str = "", autosar_release: str = "",
                             data_classification: str = "internal",
                             access_policy: dict | None = None,
                             version_label: str = "",
                             extractor_name: str = "asrbrain-ingest",
                             extractor_version: str = "1",
                             extraction_confidence: float = 1.0,
                             metadata: dict | None = None) -> tuple:
    """Store the bytes, register the artifact and record one immutable version.

    Returns `(artifact, artifact_version, object_ref)`.
    """
    ref = obj_store.put(data)
    artifact = registry.register_artifact(
        project_id=project_id,
        name=name,
        kind=kind,
        workspace_id=workspace_id,
        source_uri=source_uri or name,
        content_hash=ref.sha256,
        owner=owner,
        branch=branch,
        autosar_release=autosar_release,
        data_classification=data_classification,
        access_policy=access_policy,
    )
    version = registry.create_artifact_version(
        artifact_id=artifact.id,
        version_label=version_label or ref.sha256[:12],
        content_hash=ref.sha256,
        size_bytes=ref.size,
        storage_uri=ref.uri,
        source_uri=source_uri or name,
        extracted_at=_now(),
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        extraction_confidence=extraction_confidence,
        metadata=metadata,
    )
    return artifact, version, ref


def ingest_document(registry: RegistryStore, obj_store: ObjectStore, *,
                    path: str, project_id: str, name: str = "",
                    kind: str = "spec", canonical_db: str = "",
                    workspace_id: str = "", owner: str = "",
                    branch: str = "", autosar_release: str = "",
                    data_classification: str = "internal",
                    access_policy: dict | None = None,
                    version_label: str = "",
                    extractor_name: str = "asrbrain-ingest",
                    extractor_version: str = "1",
                    extraction_confidence: float = 1.0,
                    chunks: list[dict] | None = None) -> dict:
    """Register one source file and every indexed passage it produced.

    The canonical store is read, never written. One `SourceLocation` is created
    per chunk so a citation can be bound to an exact passage.
    """
    from ..indexing.hybrid import load_chunks

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"source file not found: {path}")
    data = file_path.read_bytes()

    artifact, version, ref = register_artifact_bytes(
        registry, obj_store,
        data=data,
        project_id=project_id,
        name=name or file_path.name,
        kind=kind,
        source_uri=str(file_path),
        workspace_id=workspace_id,
        owner=owner,
        branch=branch,
        autosar_release=autosar_release,
        data_classification=data_classification,
        access_policy=access_policy,
        version_label=version_label,
        extractor_name=extractor_name,
        extractor_version=extractor_version,
        extraction_confidence=extraction_confidence,
    )

    if chunks is None:
        chunks = load_chunks(canonical_db) if canonical_db else []
    doc_chunks = _chunks_for_document(chunks, str(file_path), ref.sha256)

    # Do not create a second location for a chunk we already registered.
    known = {loc.chunk_id for loc in registry.list_source_locations(version.id)
             if loc.chunk_id}

    created = 0
    for chunk in doc_chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        if not chunk_id or chunk_id in known:
            continue
        document_id = str(chunk.get("document_id") or "")
        page_start = chunk.get("page_start")
        registry.add_source_location(
            artifact_version_id=version.id,
            locator_type="pdf_page",
            locator=f"pdf://{document_id}/page/{page_start}",
            page_start=page_start,
            page_end=chunk.get("page_end"),
            section=_section(chunk),
            release=str(chunk.get("autosar_release") or ""),
            module=str(chunk.get("module") or ""),
            snippet=(str(chunk.get("normalized_text") or chunk.get("text") or "")
                     [:SNIPPET_CHARS]),
            chunk_id=chunk_id,
        )
        created += 1

    return {
        "artifact_id": artifact.id,
        "artifact_version_id": version.id,
        "content_hash": ref.sha256,
        "size_bytes": ref.size,
        "storage_uri": ref.uri,
        "chunks_seen": len(doc_chunks),
        "source_locations_created": created,
    }


def source_location_for_chunk(registry: RegistryStore, chunk_id: str,
                               artifact_version_id: str = ""):
    """The registered location of a retrieval chunk, or None."""
    return registry.find_source_location_by_chunk(chunk_id, artifact_version_id)


def bind_citations(registry: RegistryStore, answer_id: str, evidence: list[dict], *,
                   conversation_id: str = "", message_id: str = "",
                   artifact_version_id: str = "") -> dict:
    """Bind an answer's evidence to registered source locations.

    Every evidence item is resolved through its chunk id. Evidence that has no
    registered location is reported as unresolved — it is never bound to a
    guessed passage, and the caller must not cite it.
    """
    citations = []
    unresolved = []
    for item in evidence or []:
        label = str(item.get("label") or "")
        chunk_id = str(item.get("source_id") or item.get("chunk_id") or "")
        location = (source_location_for_chunk(registry, chunk_id, artifact_version_id)
                    if chunk_id else None)
        if location is None:
            unresolved.append({
                "label": label,
                "source_id": chunk_id,
                "source_pdf": str(item.get("source_pdf") or ""),
                "page": item.get("page"),
                "reason": "no registered source location for this chunk",
            })
            continue
        citation = registry.add_citation(
            source_location_id=location.id,
            answer_id=answer_id,
            conversation_id=conversation_id,
            message_id=message_id,
            artifact_version_id=location.artifact_version_id,
            label=label,
            claim=str(item.get("claim") or ""),
        )
        citations.append(citation)
    return {
        "answer_id": answer_id,
        "citations": citations,
        "unresolved": unresolved,
        "bound": len(citations),
        "unresolved_count": len(unresolved),
    }
