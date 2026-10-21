# Phase 3 — Ingestion pipeline and the evidence/citation model (as built)

- **Branch:** `feature/mermaid-pdf-diagram-rendering`
- **Baseline:** Phase 2 (`89174ea`) — 133 pytest passing
- **Status:** implemented

Phase 3 closes the loop between the two stores the product has: the **canonical
store** (what the retriever reads) and the **registry** (where every passage is
addressed). It adds the object store, artifact-scoped ingestion, and citations
that bind to exact source locations.

---

## 1. What Phase 3 delivers

1. **A byte store that is not a metadata store** (ADR-0012).
   `src/objects/store.py` defines the `ObjectStore` protocol
   (`put / get / exists / stat / delete / presigned_url`) with two
   implementations: `LocalObjectStore` (content-addressed on disk) and
   `S3ObjectStore` (lazy `boto3`, used through the S3 API — never MinIO the
   product). The backend is selected by `OBJECT_STORE_BACKEND`.
2. **Artifact-scoped ingestion** (`src/ingestion/registry_ingest.py`) that
   registers an `Artifact`, one immutable `ArtifactVersion` and **one
   `SourceLocation` per indexed chunk**.
3. **Citations that resolve to a location** — `bind_citations()` maps an
   answer's evidence to the exact `SourceLocation` and writes `Citation` rows.
   Evidence with no registered location is reported as **unresolved**; it is
   never bound to a guessed passage.
4. **A job handler** for `artifact.ingest` in `apps/worker.py`.
5. **Two additive API routes** to trigger ingestion and to bind citations.
6. **Migration 007** adding `chunk_id` to `source_locations` so a retrieval
   chunk can be resolved to its registered passage.

### Not in Phase 3

* The registry is **not** yet populated by the normal `/ingest` flow — that is
  a Phase 3.5/4 change; for now ingestion is triggered explicitly.
* The answerability gate still returns `501`; the gate itself is Phase 5.
* No object-store retention or garbage collection.
* The PostgreSQL adapter is not here (ADR-0010 — the DDL is portable, the
  adapter lands in Phase 3+).

---

## 2. The object store

| Concern | Rule |
|---|---|
| Content addressing | objects are keyed by the SHA-256 of their bytes, so the same bytes always land on the same key. |
| Atomicity | `LocalObjectStore` writes to a temporary file and then `os.replace`s it, so a reader never sees a half-written object. |
| Metadata | the object store holds **bytes only**. Every piece of metadata — content hash, owner, project, branch, release, classification, access policy, lifecycle state — lives in the relational registry. A lost bucket must never mean lost provenance. |
| Portability | the product speaks the S3 API, so MinIO, Ceph RGW, SeaweedFS, Garage and hosted S3 are all deployment choices rather than code dependencies (ADR-0012). |
| Failure mode | `S3ObjectStore` raises a `RuntimeError` that names `boto3` and points at `OBJECT_STORE_BACKEND=local` — a missing library is a configuration error, not a silent fallback. |

Configuration: `OBJECT_STORE_BACKEND` (`local` | `s3`), `OBJECT_STORE_ROOT`,
`OBJECT_STORE_BUCKET`, `OBJECT_STORE_ENDPOINT_URL`, `OBJECT_STORE_REGION`,
`OBJECT_STORE_ACCESS_KEY`, `OBJECT_STORE_SECRET_KEY`, `OBJECT_STORE_PREFIX`.

---

## 3. Artifact-scoped ingestion

```
file bytes ──► ObjectStore.put()  ──► local://<sha>   (bytes only)
                    │
                    ├─► registry.register_artifact()          (Artifact)
                    └─► registry.create_artifact_version()   (ArtifactVersion)
                                │
canonical chunks ───────────────┴─► registry.add_source_location() × N
                                    (one SourceLocation per chunk)
```

* The **canonical store is read, never written.** `canonical.db` stays the
  retrieval source of truth (ADR-0002, dual-read single-write).
* A chunk is matched to its file by the document's **SHA-256** (authoritative),
  with the `source_pdf` file name only as a fallback for stores written before
  the hash was recorded.
* Each `SourceLocation` records `locator_type="pdf_page"`, the locator
  `pdf://<document_id>/page/<page_start>`, the page range, the section, the
  release, the module, a 400-character snippet and the `chunk_id`.
* Re-ingesting the same file creates a **new version** and registers the chunk
  again *for that version* — never twice for the same version.
* The snippet is a preview. The full text stays in the canonical store; the
  registry holds the address, not a second copy of the corpus.

---

## 4. Binding citations

`bind_citations(registry, answer_id, evidence, …)` walks the evidence of one
answer and, for each item:

1. resolves `evidence.source_id` (the chunk id) through
   `find_source_location_by_chunk()`;
2. writes a `Citation` carrying `answer_id`, `conversation_id`, `message_id`,
   `label`, `claim`, the `source_location_id` and the `artifact_version_id`;
3. if no location is registered, records the item in `unresolved` with the
   reason and **does not create a citation**.

The returned summary is `{answer_id, citations, unresolved, bound,
unresolved_count}`. `unresolved_count > 0` is a signal that the answer cites
something the registry cannot locate — the UI and the audit trail must show
that rather than hide it.

---

## 5. API changes (additive only)

| Route | Behaviour |
|---|---|
| `POST /api/v2/registry/ingest` | Body: `path`, `project_id`, optional `name`, `kind`, `workspace_id`, `owner`, `branch`, `autosar_release`, `data_classification`, `version_label`, `canonical_db`. Enqueues an `artifact.ingest` job and returns `{queued: true, job}`. `503` when the registry is disabled, `400` when `path`/`project_id` are missing. |
| `POST /api/v2/registry/citations/bind` | Body: `answer_id`, `evidence[]`, optional `conversation_id`, `message_id`, `artifact_version_id`. Returns `{answer_id, citations, unresolved, bound, unresolved_count}`. |

The 47 v1 routes and the Phase-2 v2 registry/jobs routes are unchanged.

---

## 6. Migration and rollback

* **Data model:** one new migration, `007_source_location_chunk.sql`
  (`ALTER TABLE source_locations ADD COLUMN chunk_id TEXT;` + an index). It is
  additive and portable across SQLite and PostgreSQL.
* Applying it is automatic: `RegistryStore.__init__` runs the migration
  runner, and the runner records the version and a checksum in
  `schema_version`. Re-running is a no-op; **editing an already-applied
  migration raises `MigrationError`**.
* **Rollback:** `git revert <phase-3-sha>` and delete the registry file
  (`data/canonical/registry.db`, or `REGISTRY_DB`). The canonical store and the
  hybrid index are untouched, so the product keeps working without the
  registry.
* Migrations are forward-only. To undo migration 007 in a live database, add
  migration 008 — never edit 007.

---

## 7. Changed files

**New**
* `src/objects/store.py`, `src/objects/__init__.py`
* `src/ingestion/registry_ingest.py`
* `src/registry/migrations/007_source_location_chunk.sql`
* `tests/unit/test_object_store.py`, `tests/unit/test_registry_ingest.py`

**Modified**
* `src/registry/models.py` (`SourceLocation.chunk_id`)
* `src/registry/store.py` (`add_source_location(chunk_id=…)`,
  `find_source_location_by_chunk()`)
* `apps/worker.py` (`artifact.ingest` handler)
* `apps/api/main.py` (the two v2 routes)
* `README.md` (Phase 3 section)

---

## 8. Risks that remain

* The registry is only populated when ingestion is triggered explicitly; the
  standard `/ingest` path still writes only the canonical store.
* Bindings are resolved by chunk id. A re-index that changes chunk ids would
  orphan existing citations — the artifact **version** is the stable identity,
  so a re-index must create a new version rather than mutate locations.
* `bind_citations` is a separate step from answering. Until Phase 5 wires the
  verifier into the request path, citations are created on demand, not as part
  of every answer.
* The snippet stored in a `SourceLocation` is a 400-character preview; the
  evidence drawer must read the full passage from the canonical store, not from
  the registry.

---

## 9. Unresolved decisions

* Should `/ingest` always register an artifact, or only when a project is
  given? (A default "local" project is the current behaviour.)
* How long are object bytes kept after an `ArtifactVersion` is superseded —
  and does a deletion request delete the bytes, the rows, or both?
* Should a citation be immutable? Today a re-bind creates a second row for the
  same answer.
