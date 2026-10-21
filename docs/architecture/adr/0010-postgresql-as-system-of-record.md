# ADR-0010 — PostgreSQL is the system of record; SQLite stays the dev adapter

- **Status:** accepted
- **Date:** 2026-10-21
- **Supersedes/partially refines:** ADR-0003
- **Product owner decision:** confirmed 2026-10-21 ("PostgreSQL or stay on SQLite — any better DB for a hybrid workflow?").

## Context

The product needs to hold, in one relational model, the provenance spine
(Artifact → ArtifactVersion → SourceLocation → Citation → EvidenceClaim), the
chat and audit trail, the job queue and (later) the requirement/test/finding
entities. The retrieval stack is hybrid: lexical + dense retrieval, a typed
property graph, and object storage for the raw bytes.

SQLite is a good fit for a single-writer, local, read-mostly corpus — which is
exactly what AsrBrain is today. It stops being a good fit the moment the
product gains a second writer and real isolation requirements.

## Decision

**PostgreSQL 16 is the target system of record.** Phase 2 ships **SQLite** as
the local/dev adapter, but the DDL is written in **portable SQL** and applied
through a migration framework, so the same migrations run on both engines. The
PostgreSQL adapter is added in Phase 3+, once the migrations exist — the schema
is never written twice.

Phase 2 therefore lands:

* `src/registry/migrations/*.sql` — ordered, idempotent, portable DDL.
* `src/registry/migrator.py` — an ordered idempotent runner with a
  `schema_version` table and **checksum enforcement** (editing an applied
  migration is an error, not a silent divergence).
* `src/registry/db.py` — the connection seam where the engine is chosen.

## Why PostgreSQL for a hybrid workflow

| Need | PostgreSQL | SQLite |
|---|---|---|
| Concurrent writers (API + ingestion worker + agents) | MVCC, real concurrency | one writer at a time; `SQLITE_BUSY` under load |
| Structured provenance | `jsonb` with indexing | JSON text, no indexing |
| Transactions across artifacts/versions/citations | real multi-table transactions | single-writer only |
| Job queue | `LISTEN/NOTIFY` + `FOR UPDATE SKIP LOCKED` | polling a table (works, but coarse) |
| Project isolation | row-level security | application-level filtering only |
| Fuzzy entity search | `pg_trgm` | no equivalent |
| Lexical search | native `tsvector` | BM25 in the app |
| Vectors | `pgvector` | none (needs a separate store) |

The important consequence: **one database can hold the relational model, the
vector index and the job queue.** That removes the need to run SQLite *and*
Qdrant *and* Redis *and* a graph database. Qdrant remains an optional
mirror, not a requirement.

## Consequences

* **Positive:** one deployment topology, real transactions over the evidence
  spine, one backup story, one place to enforce project isolation.
* **Negative:** contributors need a PostgreSQL instance to exercise the
  production path. Mitigated by keeping the SQLite adapter and by making the
  engine selection a single setting.
* **Rule:** DDL in `src/registry/migrations/` must stay portable — no SQLite-only
  or PostgreSQL-only construct without an explicit, documented branch.
* **Rule:** the existing `canonical.db` chunk store is **not** migrated in this
  phase. It stays the retrieval source of truth (ADR-0002, dual-read
  single-write).

## Alternatives considered

* **Stay on SQLite forever** — rejected: it caps the product at single-writer,
  single-host, single-tenant, and forces a second store for vectors and a third
  for the job queue.
* **MongoDB / document store** — rejected: the evidence spine is relational and
  heavily join-shaped (citations point at source locations which point at
  artifact versions); a document store would push every integrity check into
  application code.
* **Write the DDL twice (SQLite now, PostgreSQL later)** — rejected: two
  schemas drift, and the drift is exactly where evidence provenance gets lost.
