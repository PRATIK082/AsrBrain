# ADR-0002 — Provenance-first data model with an artifact/version spine

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §3

## Context

The corpus today is a flat set of tables in `data/canonical/canonical.db`:

```
documents(document_id, source_pdf, sha256, title, autosar_release, platform,
          module, document_type, page_count, quality)
chunks(chunk_id, document_id, source_pdf, sha256, page_start, page_end,
       pdf_page_index, autosar_release, platform, module, document_type,
       section_number, section_title, requirement_ids, api_names,
       ecu_parameters, parent_chunk_id, chunk_kind, text, normalized_text)
tables(evidence_id, document_id, source_pdf, page, caption, rows_json, …)
figures(evidence_id, document_id, source_pdf, page, kind, number, caption, …)
```

There is no notion of a *project*, a *branch*, a *version* of a file, or an *owner*.
A chunk points at a file name and a page, but not at a content hash of a specific
revision of a specific project. ARXML artifacts live in an in-memory dict
(`_ARXML_STORE` in `apps/api/main.py`) and are lost on restart. Two independent
writers (`src/ingestion/pipeline.py` and `src/ingestion/project_sources.py`) target
the same file.

Without a provenance spine, "traceable to controlled evidence" cannot be enforced: a
citation cannot name the artifact *version* it came from, an access policy cannot be
evaluated per artifact, and a diff cannot be expressed as base-version →
target-version.

## Decision

Adopt a **provenance-first** model in a **new** database (`data/canonical/registry.db`),
additive to the existing corpus:

```
Project → Workspace → Artifact → ArtifactVersion → SourceLocation
                                                   ├→ Citation → EvidenceClaim
                                                   └→ ValidationResult
```

Key rules:

1. `Artifact` = the logical thing ("the CanIf ARXML of project X").
   `ArtifactVersion` = an immutable snapshot identified by `content_hash` +
   `version_label` + `branch` + `release`. Citations always bind to a **version**.
2. `SourceLocation` is the addressable location inside a version:
   `page`/`section` for PDF, `xpath` + `line_start`/`line_end` for ARXML and source,
   `cell_range` for spreadsheets, `block` for code.
3. Everything that asserts something — graph edges, claims, findings, trace links,
   diagrams — carries `artifact_version_id` + `source_location_id` (or an explicit
   `not_applicable`), plus `extraction_method`, `confidence`, `is_inferred` and
   `lifecycle_state`.
4. The existing `chunks` table remains the retrieval source of truth during the
   migration (dual-read, single-write). The registry is populated alongside it.
5. Migrations are ordered, idempotent SQL scripts in `src/registry/migrations/`,
   tracked by a `schema_version` table.

## Consequences

**Positive**

- A citation can always be resolved to an exact, immutable version of a file.
- Access policy, retention and deletion become per-artifact decisions.
- Diffs become "base version → target version" instead of "two arbitrary JSON blobs".
- Multi-project and multi-branch work becomes possible without a rewrite.

**Negative**

- Two databases must stay consistent; the registry must be rebuildable from the
  corpus.
- Every write path (ingestion, ARXML upload, project-source import) needs a registry
  write, which is more code today.
- Storage grows (a content hash and metadata per version).

**Rejected alternatives**

- *Add columns to `chunks`* — cannot express project/branch/version/owner/ACL, and
  breaks the "additive, no destructive ALTER" migration rule.
- *Make the existing corpus the only store* — no place for citations, claims, jobs or
  audits without polluting the hot retrieval table.
- *PostgreSQL now* — rejected in [ADR-0003].
