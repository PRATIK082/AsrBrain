# Phase 2 — Provenance Data Model, Registry, Job Framework (as built)

> Branch: `feature/mermaid-pdf-diagram-rendering` · Status: implemented
> Predecessor: [Phase 1 plan](phase-1-implementation-plan.md) · ADRs: 0010–0014

---

## 1. What Phase 2 delivers

Phase 2 builds the **provenance spine** the evidence-first contract needs. Today a
citation points at a `chunk_id` in a flat SQLite table; after Phase 2 a citation can
point at a *versioned artifact*, at a *source location inside that artifact*, and the
answer that used it can be audited with the claims it made and the status it earned.

| # | Deliverable | Where |
|---|---|---|
| 2.1 | Artifact/version registry with ordered, idempotent migrations | `src/registry/` |
| 2.2 | Provenance-first records (project → artifact → version → location → citation) | `src/registry/models.py`, `src/registry/store.py` |
| 2.3 | Background-job framework (enqueue / claim / complete / fail) + worker process | `src/registry/jobs.py`, `apps/worker.py` |
| 2.4 | Additive `/api/v2/registry/*` and `/api/v2/jobs/*` API | `apps/api/main.py` |
| 2.5 | Stack decisions recorded | `docs/architecture/adr/0010..0014` |
| 2.6 | Tests (22) | `tests/unit/test_registry_migrations.py`, `tests/unit/test_registry_store.py`, `tests/integration/test_registry_api.py` |

**Not in Phase 2** (deliberately): the registry is not yet populated by the ingestion
pipeline, the answerability gate is not computed from it, no object store adapter
exists yet, and no PostgreSQL server is required to run the product.

## 2. Data model

Eleven tables, created by six ordered migrations plus the migrator's own
`schema_version` table.

```
projects ──< workspaces ──< artifacts ──< artifact_versions ──< source_locations ──< citations
                                                                        └──< validation_results
evidence_claims            (per answer: claim, type, status, citations, missing, conflicts)
answer_audits              (per answer: question, status, scope, citations, tool calls, route)
jobs                       (long-running work: kind, payload, status, attempts, result)
schema_version             (applied migrations + checksum)
```

### The spine

`Project → Workspace → Artifact → ArtifactVersion → SourceLocation → Citation`

* **Artifact** is the thing ("the SOME/IP PRS PDF", "the ECU extract ARXML"), with a
  `content_hash`, `owner`, `branch`, `autosar_release`, `data_classification`,
  `access_policy` and `lifecycle_state`.
* **ArtifactVersion** is one immutable revision of it, with `version_label`,
  `size_bytes`, `storage_uri`, `extractor_name`, `extractor_version` and
  `extraction_confidence`. A citation binds to a *version*, never to "the file".
* **SourceLocation** is the address of a passage inside a version:
  `locator_type` ∈ `pdf_page | arxml_xpath | source_symbol | test_case | row_range |
  json_pointer`, plus `page_start/page_end`, `section`, `line_start/line_end`,
  `release`, `module` and the `snippet`.
* **Citation** binds a claim to a location and to the answer that made it
  (`answer_id`, `conversation_id`, `message_id`, `label`, `claim`).

### The answer contract

`evidence_claims` is where ADR-0001 becomes data. One row per claim:

* `claim_type` ∈ `fact | interpretation | assumption | recommendation`
* `status` ∈ `VERIFIED | EVIDENCE_SUPPORTED | NEEDS_ENGINEER_REVIEW | INSUFFICIENT_EVIDENCE`
* `citation_ids`, `missing[]`, `conflicts[]`, `checked[]`, `confidence` (internal only)

`answer_audits` records the whole turn: request id, scope, the status earned, the
citations, the tool calls, the model route and its reason, and the latency.

### Migrations

`src/registry/migrations/*.sql`, applied in numeric order by `apply_migrations()`:

* Each file is applied inside a transaction; a failure rolls that migration back.
* A `schema_version(version, name, checksum, applied_at)` row records what ran.
* **Re-running is a no-op** — already-applied versions are skipped.
* **Editing an applied migration raises `MigrationError`** (the checksum changed).
  Add a new migration instead; the applied history is immutable.
* The DDL is written to be portable (ADR-0010): the same files must run on PostgreSQL.

## 3. Background jobs

`Job` rows are the unit of long-running work (ingestion, re-indexing, ARXML parsing,
report rendering) so the API never blocks and the UI can show real progress.

* `enqueue(kind, payload, ...)` → `queued`.
* `claim_next(kinds=None)` — atomic (`BEGIN IMMEDIATE` + conditional `UPDATE`); a
  claimed job is never handed out twice, even with two workers.
* `complete(job_id, result)` → `succeeded` with the result recorded.
* `fail(job_id, error)` — requeues while `attempts < max_attempts`, then marks
  `failed` with the error text. **A failing job never kills the worker.**
* An unregistered job kind is failed loudly with the reason, instead of being dropped.

`apps/worker.py` is the entry point (`python -m apps.worker`). It currently ships one
placeholder handler (`echo`); the real handlers arrive with the Phase 3 ingestion
pipeline.

## 4. API changes (additive only)

All 47 v1 routes keep their path, request shape and response keys (ADR-0008). The new
surface lives under `/api/v2/`:

| Route | Purpose |
|---|---|
| `GET /api/v2/registry/health` | `{enabled, registry_db, schema_version}`; 503 when `ASRBRAIN_REGISTRY_ENABLED=false` |
| `POST` / `GET /api/v2/registry/projects` | project registry |
| `POST` / `GET /api/v2/registry/workspaces` | workspaces (filter by `project_id`) |
| `POST` / `GET /api/v2/registry/artifacts` | artifacts (filter by `project_id`, `kind`) |
| `POST` / `GET /api/v2/registry/artifact-versions` | versions (filter by `artifact_id`) |
| `POST` / `GET /api/v2/registry/source-locations` | source locations (filter by `artifact_version_id`) |
| `POST` / `GET /api/v2/registry/citations` | citations (filter by `answer_id`) |
| `GET` / `POST /api/v2/jobs`, `GET /api/v2/jobs/{id}` | job queue; `GET` returns `{jobs, counts}` |

Referential integrity is enforced in the store (not by foreign keys, so the DDL stays
portable): creating a workspace for an unknown project, an artifact version for an
unknown artifact, a source location for an unknown version or a citation for an unknown
location raises `ValueError`, which the API maps to **HTTP 400** with a `detail`
message. A missing job returns **404**.

## 5. Migration and rollback

* **No existing table was altered.** The registry is a *new* SQLite file
  (`data/canonical/registry.db`, override with `REGISTRY_DB`). The `canonical.db`
  chunk store and `chat.db` are untouched.
* **No existing behaviour changed.** The v1 API is byte-for-byte unchanged; the
  registry is only reachable through the new v2 routes.
* **Feature flags.** `ASRBRAIN_REGISTRY_ENABLED` (default `true`) gates the registry
  API; `ASRBRAIN_WORKER_ENABLED` (default `false`) gates the worker; the worker is a
  separate process, so the API never starts it implicitly.
* **Rollback.** `git revert <phase-2-sha>` removes the code. The registry file is
  left on disk and is inert — nothing in v1 reads it. To remove it: delete
  `data/canonical/registry.db` (it holds no user data that is not reproducible from
  the sources).
* **Forward-only migrations.** Once a migration is applied it is never edited; the
  checksum guard makes that an error, not a silent divergence.

## 6. Stack decisions (ADRs 0010–0014)

| Concern | Decision | Dev | Production |
|---|---|---|---|
| Relational store | PostgreSQL is the system of record, portable DDL | SQLite adapter | PostgreSQL 16 |
| Graph | Typed property graph behind `GraphStore` | SQLite implementation | FalkorDB (LGPL-3.0) |
| Object storage | Depend on the S3 API | content-addressed filesystem | MinIO / Ceph / S3 |
| Orchestration | Our own deterministic staged pipeline | same | same |
| Dense embeddings | BGE-M3 (MIT) via local Ollama | `tfidf` until measured better | BGE-M3 + BM25, vectors in pgvector |
| Jobs | `Job` rows + worker | SQLite | PostgreSQL `LISTEN/NOTIFY` + `SKIP LOCKED` |

LlamaIndex and LangChain were **declined** as the orchestration core (ADR-0013): the
existing `run_staged` pipeline, the clarify gate, the citation verifier and the UI event
contract are the evidence-first backbone. If a framework is added later it must stop at
our model boundary — a connector may produce `Artifact`/`ArtifactVersion`/
`SourceLocation` records, never answers.

## 7. Risks that remain

* The registry is **not yet populated** by the ingestion pipeline — Phase 3 wires
  ingestion to it. Until then the registry is an empty, correct skeleton.
* The answerability gate still returns **HTTP 501**; the UI shows
  `NEEDS_ENGINEER_REVIEW` and says so. Phase 5 computes the real status from the
  registry rows.
* The module catalogue is duplicated in the API and in the frontend fallback. The
  registry is the intended single source in Phase 2+; the duplicate is a deliberate
  safety net so the shell still renders if the API is down.
* `docs/architecture/adr/0007` still says "Neo4j/RDF" in its title; ADR-0011
  supersedes that wording. The `GraphStore` protocol it defines is unchanged.
* No PostgreSQL adapter exists yet, so the portability of the DDL is asserted by
  review, not by a running PostgreSQL in CI.

## 8. Unresolved decisions (carried forward)

1. **PostgreSQL provisioning** — who runs it, and in which environment? Phase 3 needs
   a decision before the PG adapter lands.
2. **Job queue semantics on PostgreSQL** — `LISTEN/NOTIFY` vs `SKIP LOCKED` polling
   vs keeping the SQLite queue; affects the worker contract.
3. **Object store retention** — the lifecycle policy for `ArtifactVersion` rows and the
   bytes they point at.
4. **Multi-tenant isolation** — row-level security arrives with the PG adapter; until
   then the registry is single-tenant by construction.
