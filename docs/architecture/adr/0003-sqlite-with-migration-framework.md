# ADR-0003 — Stay on SQLite, but introduce a migration framework now

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §6.1, §8

## Context

`docker-compose.yml` already ships a `postgres:16` service (profiles `standard` and
`full`) with credentials `autosar/autosar/autosar`, plus `neo4j:5`, `opensearch` and
`redis` — but **no application code uses any of them**. There is no SQLAlchemy, no
alembic, no migration directory, and no ORM. The two live stores are hand-written
SQLite files:

- `data/canonical/canonical.db` — documents, chunks, tables, figures (no indexes, no
  foreign keys);
- `data/canonical/chat.db` — conversations, messages, feedback (no indexes, no
  foreign keys).

The project is an open-source, local-first tool that must run from a clone with
`pip install -r requirements.txt` and start. A hard PostgreSQL dependency would break
that promise and would prevent the many contributors who only want to run the chat
UI.

At the same time, the target model needs ordered, auditable schema evolution
(registries, jobs, audits, requirement links), and hand-written `CREATE TABLE IF NOT
EXISTS` blocks in two modules — with two independent writers already racing on
`canonical.db` — is not going to survive six more phases.

## Decision

1. **Keep SQLite as the default and only required store** for Phases 1–6. No new
   runtime dependency, no database server to install, no change to the one-command
   start.
2. **Introduce a migration framework immediately**: ordered, idempotent SQL migration
   files in `src/registry/migrations/`, applied by a tiny runner, tracked in a
   `schema_version` table. Each migration is a plain `.sql` file with an explicit
   version and is applied inside a transaction.
3. **One SQLite file per concern**: `canonical.db` (corpus), `chat.db` (conversations),
   `registry.db` (new: projects, artifacts, versions, jobs, audits, links).
4. **PostgreSQL is a later adapter, not a rewrite.** The SQL is written to be
   portable (no SQLite-only constructs in the new migrations), so a Postgres backend
   can be added behind the same store interfaces when a hosted/multi-tenant
   deployment is actually required (Phase 8).
5. The `postgres`/`neo4j`/`opensearch`/`redis` Compose services stay available but
   are documented as **reserved profiles**, not as running dependencies — until code
   uses them they must not be presented as a supported deployment option.

## Consequences

**Positive**

- The one-command experience survives; contributors keep working with zero setup.
- Schema changes become reviewable, ordered and reversible.
- The registry database is a clean boundary that can be ported later without touching
  the corpus.

**Negative**

- SQLite has no concurrent-writer story: long ingestion jobs must not write while a
  request reads the same file. Mitigated by keeping the corpus read-only at request
  time and writing the registry only.
- Two databases means two backups.
- A Postgres port is not free: `PRAGMA` usage, JSON text columns and
  `INSERT OR REPLACE` semantics all need revisiting.

**Rejected alternatives**

- *Adopt PostgreSQL + SQLAlchemy + alembic now* — breaks local-first start-up, adds
  three dependencies, and rewrites every store call for a deployment target that does
  not exist yet.
- *Keep ad-hoc `CREATE TABLE IF NOT EXISTS`* — the current state; two writers already
  race on the same file.
- *Drop the unused Compose services now* — reasonable, but out of scope for this
  decision; documented instead as reserved.
