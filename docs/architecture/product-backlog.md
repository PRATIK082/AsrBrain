# Product backlog — AsrBrain Engineering Workspace

> Derived from [`target-architecture.md`](./target-architecture.md) and the ADRs.
> Every item is **independently testable** and lands in exactly one phase, so each
> phase is reviewable and revertible on its own.
>
> Legend — **M**: must (blocks the phase) · **S**: should · **C**: could.
> Sizes are engineering estimates in days.

---

## Phase 1 — Design system + workspace shell

*Goal: the product has a navigation shell, a status vocabulary and a workspace
layout, without changing any existing behaviour.*

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 1.1 | Workspace shell: persistent left nav (workspace/project selector + 9 module entries) | M | 2 | The React app renders a collapsible module nav; the current modules are reachable |
| 1.2 | Module routes for Chat, Knowledge, ARXML, Graph, Requirements, Tests, Diffs & Impact, Diagrams & Reports, Evaluation & Admin | M | 2 | Each module has a real route and an actionable empty state (no blank screens) |
| 1.3 | `AnswerabilityStatus` type + badge component (4 states, colour + icon + tooltip) | M | 1 | The badge renders in every state and is used by the chat card |
| 1.4 | Answer card section layout: Answer · Evidence · Reasoning summary · Assumptions · Tool results · Exclusions · Audit | M | 2 | The existing chat response renders in the new card layout, with all existing data still shown |
| 1.5 | Evidence drawer (right panel): PDF page/section preview, ARXML path, code symbol, requirement/test links, conflict/version info | M | 3 | Clicking a citation opens the drawer at the source location |
| 1.6 | Keyboard navigation + focus management + ARIA landmarks | S | 1 | The whole shell is operable by keyboard; landmarks are announced |
| 1.7 | Dark/light theme parity check across all new surfaces | S | 1 | No token is hard-coded; both themes are legible |
| 1.8 | CI: GitHub Actions workflow (pytest, `tsc --noEmit`, `next build`) | M | 1 | A push to the branch runs the three gates and reports status |
| 1.9 | Frontend smoke test: shell renders, nav switches modules, chat still answers | M | 1 | A component test asserts the shell and the preserved chat path |

**Explicitly preserved in Phase 1:** the existing chat behaviour, the Mermaid
rendering path (`MermaidDiagram.tsx`, `securityLevel: "strict"`), the PDF diagram
analysis/recreation endpoints, the ARXML/diff/code workbenches, and all 47 existing
API routes.

---

## Phase 2 — Provenance data model, migrations, artifact registry, job framework

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 2.1 | `src/registry/` store package + `schema_version` table + idempotent migration runner | M | 3 | `python -m src.registry.migrate` applies migrations and is safe to re-run |
| 2.2 | Registry schema: projects, workspaces, artifacts, artifact_versions, source_locations | M | 3 | Migrations 001–003 applied; a round-trip test persists and reads an artifact version |
| 2.3 | Object-store metadata: content hash, source URI, owner, project, branch, release, access policy | M | 2 | Every ingested file gets a registry row with a sha256 and a policy |
| 2.4 | `ArtifactStore` protocol + local filesystem implementation | M | 2 | A second implementation (S3) could be added without touching callers |
| 2.5 | `Job` table + in-process worker + `GET /api/v2/jobs/{id}` | M | 3 | A long job reports real progress and survives a page refresh |
| 2.6 | `AnswerAudit` table + audit writer + request-id propagation | M | 2 | Every answer produces one audit row with scope, claims, citations, tools, model route |
| 2.7 | `SecurityContext` plumbing into the request path (tenant/project scope, default-deny) | M | 3 | Requests without a tenant scope are denied in retrieval |
| 2.8 | `UserRole` table + role check helper | S | 2 | A role can be asserted and enforced by a helper |

---

## Phase 3 — Ingestion pipeline + evidence/citation model

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 3.1 | Artifact-scoped ingestion: every write targets an `artifact_version_id` | M | 4 | A re-ingest produces a new version; the old one stays readable |
| 3.2 | `SourceLocation` emission for PDFs (page, section, block) | M | 2 | Every chunk carries a resolvable source location |
| 3.3 | `Citation` + `EvidenceClaim` models and persistence | M | 2 | A claim can be stored with its citations and re-read |
| 3.4 | `ValidationResult` model + ingestion-quality validation write-back | M | 2 | The quality report is stored as a validation result, not a loose JSON file |
| 3.5 | Fix TD-1: `project_sources.py` ARXML summary call | M | 0.5 | The ARXML summary is no longer swallowed by `except Exception` |
| 3.6 | Fix TD-13: single writer for `canonical.db` | S | 2 | `project_sources.ingest_source()` uses the shared schema definition |
| 3.7 | Fix TD-2: BM25 idf weighting | S | 1 | `bm25_scores` uses the idf it computes; a unit test pins the behaviour |
| 3.8 | Fix TD-10: align `Chunk` dataclass with the `chunks` table | S | 1 | No declared field lacks a column |
| 3.9 | Add indexes and foreign keys to the new registry DB (not to `canonical.db`) | S | 1 | Query plans for the registry use the indexes |

---

## Phase 4 — ARXML parser, typed graph, validation tools, explorer UI

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 4.1 | Line-aware ARXML parsing → `ARXMLElement` with uuid, short name, qualified path, line range | M | 5 | A synthetic ARXML fixture yields elements with exact line numbers |
| 4.2 | Populate the currently dead model fields (`comspec`, `events`, `data_accesses`, `server_call_points`, `value_type`, `reference_target`, connector refs) | M | 3 | Each field has a test with a fixture that exercises it |
| 4.3 | `autosar_release` detection from the schema location | M | 1 | The release is populated and asserted |
| 4.4 | `validate_arxml` tool → `ValidationResult` (well-formedness, schema, unresolved refs) | M | 3 | An invalid fixture yields fail + parser errors, bound to the artifact version |
| 4.5 | `resolve_arxml_references` tool | M | 2 | Unresolved references are reported with the searched artifact and scope |
| 4.6 | `query_arxml_path` tool (qualified-path query) | M | 2 | A path query returns the element with its source location |
| 4.7 | `diff_arxml_versions` tool (components, ports, interfaces, **connectors, runnables, ECUC**) | M | 3 | The diff covers the entities its name claims (closes TD-3) |
| 4.8 | `trace_communication_path` tool | M | 3 | A sender-to-receiver path is returned with hops and locations |
| 4.9 | `analyze_change_impact` tool | M | 3 | Impacted requirements/components/tests are listed with evidence |
| 4.10 | Persist ARXML artifacts and versions in the registry (replaces `_ARXML_STORE`) | M | 2 | An uploaded ARXML survives a restart and is listable |
| 4.11 | ARXML Explorer UI: tree, search, reference navigation, validation results | M | 4 | A user can navigate from a component to its ports and interfaces |
| 4.12 | `GraphStore` interface + SQLite implementation (typed nodes/edges + provenance) | M | 5 | Nodes and edges persist with type, provenance and lifecycle state |

---

## Phase 5 — Hybrid retrieval, graph-aware planner, answerability gates, audit trail

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 5.1 | Scope-first filtering (project/branch/ECU/vendor/release/source type/access) applied before retrieval | M | 4 | A request scoped to a release cannot retrieve a passage from another release |
| 5.2 | Extend the vector payload contract with artifact/version/source-type/location fields | M | 2 | `payload_for()` and the Qdrant mirror carry the same fields (closes TD-7/TD-8) |
| 5.3 | Intent router extended with the 3 missing intents + tool mapping | M | 2 | Each intent resolves to a tool family |
| 5.4 | Tool-first executor in the answer pipeline | M | 5 | A structural question runs its tool before the model and shows the tool result |
| 5.5 | Answerability gate (4 statuses) implemented as a pure function | M | 3 | Unit tests cover all four statuses, including the conflict case |
| 5.6 | `INSUFFICIENT_EVIDENCE` response naming the missing artifact and the searched scope | M | 2 | The response is actionable, never an empty answer |
| 5.7 | Conflict detection between cited sources | M | 3 | Two sources disagreeing produces `NEEDS_ENGINEER_REVIEW` with both cited |
| 5.8 | Full audit trail: ingestion, retrieval, tool execution, export, model request | M | 3 | Every event type has an audit row and a query interface |
| 5.9 | Policy-based model routing enforced on the request path (ADR-0009) | M | 3 | A confidential request cannot reach a cloud provider; redaction is applied and recorded |
| 5.10 | Graph-aware retrieval expansion (intent-driven, depth-capped) | S | 3 | A dependency question expands the graph and cites the expansion |

---

## Phase 6 — Requirements, tests, traceability matrix, failure investigation

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 6.1 | Requirement ingestion (CSV/XLSX/JSON/API) + normalization (id, title, revision, status, source, parent, verification method) | M | 4 | A synthetic requirement file is ingested and normalized |
| 6.2 | `TestCase` / `TestRun` / `TestResult` models + JUnit, pytest and CSV adapters | M | 4 | A synthetic JUnit XML yields test cases, a run and results |
| 6.3 | Trace links with lifecycle status (proposed → machine_extracted → reviewed → approved → rejected) | M | 3 | Only `approved` links are presented as established fact |
| 6.4 | Traceability Matrix UI (bidirectional requirement ↔ code ↔ test) | M | 4 | A user can navigate both directions from a requirement |
| 6.5 | Coverage view + orphan detection (requirements without code, tests without requirements) | M | 3 | Orphans are listed with their evidence |
| 6.6 | `Finding` model + findings UI (severity, status, reproducibility, owner, root cause, review state) | M | 3 | A finding is created, reviewed and shown |
| 6.7 | Failure clustering + timeline + linked changes | M | 4 | Clustered failures link to the change set that introduced them |
| 6.8 | CAN/log-derived test summaries | C | 4 | A synthetic log yields a test summary with an inferred flag |

---

## Phase 7 — Diff/impact engine, Mermaid evidence binding, PDF evidence package

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 7.1 | `ChangeSet` model (base version → target version, scope, author) | M | 2 | A change set persists both versions and its scope |
| 7.2 | Impact engine: change set → impacted entities (requirements, components, tests) with evidence | M | 5 | An impact report lists entities with citations and a confidence |
| 7.3 | Mermaid source versioning + binding to evidence claims and graph nodes | M | 3 | A diagram records which claims and nodes it visualises |
| 7.4 | Sandboxed Mermaid rendering (separate process, size/time limits) | M | 3 | A pathological diagram cannot hang or crash the API |
| 7.5 | PDF **Evidence Package** export: title, project scope, artifact versions, question, answer status, citations, diagrams, validation outputs, assumptions, timestamp, software version, audit id | M | 4 | The exported PDF contains every listed section |
| 7.6 | Deterministic Mermaid rendering tests + graceful errors for invalid Mermaid | M | 2 | An invalid diagram yields a structured error, not a stack trace |
| 7.7 | Diff & Impact workspace UI | M | 3 | A user picks base/target and sees the structural diff plus the impact list |

---

## Phase 8 — Policy-based routing, evaluation harness, production hardening

| ID | Item | Pri | Size | Done when |
|---|---|---|---|---|
| 8.1 | `ModelRoutingPolicy` table (routing as data) + admin UI | M | 4 | A policy change alters routing without a code change |
| 8.2 | Golden evaluation dataset format (query, expected status, allowed source ids, expected entities, expected citations, forbidden claims, notes) | M | 3 | A synthetic dataset loads and the runner reports per-case results |
| 8.3 | Metrics: recall@k, precision@k, citation validity, grounded-answer rate, abstention quality, tool error rate, latency/cost by route | M | 4 | The metrics are computed from a run and reported |
| 8.4 | CI expansion: formatting, lint, types, unit, security scan, migration verification, API contract tests, Mermaid rendering tests | M | 4 | Every gate is green on the branch |
| 8.5 | Upload hardening: file-type allowlist, size limit, content sniffing, quarantine | M | 3 | A disallowed upload is rejected with a clear message |
| 8.6 | Retention/deletion + export of audit and registry data | S | 3 | A deletion request removes the artifact and its derived rows |
| 8.7 | License inventory (source dependencies + corpus licensing status) | S | 2 | The inventory is generated and checked in |
| 8.8 | Postgres adapter behind the store interfaces (optional) | C | 5 | The contract test suite passes against both backends |

---

## Explicitly out of scope

* Automatic ISO 26262 / SOP compliance claims — the platform reports "evidence
  available for review"; a qualified human approves.
* Autonomous code modification — code findings are advisory.
* Automatic requirement approval — extracted links stay proposals until reviewed.
* Web research in the default path — no external retrieval without a labelled policy.
* Hosted multi-tenant SaaS before Phase 8.
