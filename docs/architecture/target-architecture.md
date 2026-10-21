# AsrBrain Engineering Workspace — Target Architecture

> Status: **proposed** · Branch: `feature/mermaid-pdf-diagram-rendering` · Baseline: `73a80bb`
> Companion documents: [`current-state.md`](./current-state.md) · [`product-backlog.md`](./product-backlog.md) · [`adr/`](./adr/)

---

## 1. Product definition

**AsrBrain Engineering Workspace** is an evidence-first engineering intelligence platform
for AUTOSAR development. It is *not* a chat product with a document index bolted on.
The unit of value is the **evidence claim**: a statement about the system, bound to a
controlled artifact, at a known location, in a known version.

The product exists to answer four questions an AUTOSAR engineer asks daily:

| Question | Module |
|---|---|
| "What does the specification actually require?" | A — Evidence Chat |
| "What is in my project right now?" | B — Knowledge Ingestion |
| "How is my ARXML actually wired?" | C — ARXML Explorer |
| "How do requirements, code, and tests connect?" | D/E/F — Graph · Requirements · Tests |
| "What breaks if I change this?" | G — Diff & Impact |
| "How do I hand the evidence to a reviewer?" | H — Mermaid & Report Studio |
| "Is the platform behaving, and is it allowed to?" | I — Administration, Policies, Evaluation, Audit |

### 1.1 The non-negotiable principle

> Every material answer is traceable to controlled evidence.

Controlled evidence means one of:

| Source class | Binding |
|---|---|
| AUTOSAR specification | document + release + page + section |
| ARXML | artifact id + version (sha256) + qualified path |
| Project source | repository + commit + file + symbol + line range |
| Requirement | requirement id + revision + source document |
| Test | test case id + run id + result artifact |
| Derived/AI content | always marked `is_inferred`, never authoritative, never used for a normative claim |

We never state a correctness percentage. Instead every answer carries one of four
**answerability statuses**, computed by a deterministic gate (§5.3):

| Status | Meaning | UI |
|---|---|---|
| `VERIFIED` | A deterministic tool result and the authoritative source agree | green |
| `EVIDENCE_SUPPORTED` | Cited sources support the claim; no deterministic validation applies | blue |
| `NEEDS_ENGINEER_REVIEW` | Partial evidence, ambiguity, or a conflict between sources | amber |
| `INSUFFICIENT_EVIDENCE` | The corpus cannot answer; state exactly which artifact/metadata is missing | red |

`INSUFFICIENT_EVIDENCE` is a **first-class answer**, not a failure. It must name the
missing artifact, the searched scope (project / branch / ECU / release / source type),
and the action to close the gap.

---

## 2. System context

```
                        ┌──────────────────────────────────────────┐
   engineers ──────────▶│  AsrBrain Engineering Workspace (React)  │
                        │  left nav · evidence chat · workbenches │
                        └───────────────┬──────────────────────────┘
                                        │  /api/v2 (typed, paged, scoped)
                        ┌───────────────▼──────────────────────────┐
                        │  FastAPI application (apps/api)          │
                        │  intent router · retrieval planner      │
                        │  tool-first executor · answer composer  │
                        │  verifier · answerability gate · audit  │
                        └───┬───────────┬───────────┬────────────┘
                            │           │           │
              ┌─────────────▼──┐  ┌─────▼──────┐  ┌▼───────────────┐
              │  Registry DB   │  │  Vector    │  │  Typed Graph   │
              │  SQLite now    │  │  Hybrid    │  │  SQLite now    │
              │  PG later      │  │  Qdrant    │  │  Neo4j later   │
              │  artifacts,    │  │  later     │  │  typed nodes   │
              │  versions,     │  │            │  │  + edges       │
              │  jobs, audits  │  │            │  │  + provenance  │
              └──────┬─────────┘  └─────┬──────┘  └┬───────────────┘
                     │                  │           │
              ┌──────▼──────────────────▼───────────▼──────────────┐
              │  Object store: pdf/ arxml/ src/ reports/ diagrams/  │
              │  content hash · source URI · owner · project        │
              │  branch · release · access policy                  │
              └────────────────────────────────────────────────────┘
```

Everything above the object store is **local-first by default**. A cloud model is
reachable only through the policy router in §6.4 and only after redaction and an
explicit tenant grant.

---

## 3. Domain model

### 3.1 Canonical entity model

All entities live in one registry database. The table below is the target set; Phase 2
lands the subset marked **[P2]**, later phases the rest.

| Entity | Key fields | Phase |
|---|---|---|
| `Project` | id, name, tenant_id, default_branch, access_policy | [P2] |
| `Workspace` | id, project_id, name, purpose | [P2] |
| `Artifact` | id, project_id, artifact_type (pdf\|arxml\|source\|requirement\|test\|diagram\|report), source_uri, content_hash, owner, uploaded_at, access_policy | [P2] |
| `ArtifactVersion` | id, artifact_id, version_label, content_hash, branch, release, created_at, state (active\|superseded\|draft) | [P2] |
| `SourceLocation` | artifact_version_id, page, section, xpath, line_start, line_end, block | [P2] |
| `Citation` | id, claim_id, artifact_version_id, source_location_id, quote, confidence, is_inferred | [P2] |
| `EvidenceClaim` | id, answer_id, statement, kind (fact\|interpretation\|assumption\|recommendation), status, supported_by | [P2] |
| `ValidationResult` | id, tool, subject, verdict (pass\|fail\|warn\|not_run), details, ran_at | [P2] |
| `Requirement` / `RequirementVersion` | id, revision, title, status, source, parent_id, verification_method | [P6] |
| `ArchitectureElement` | id, kind, name, module, release | [P4] |
| `ARXMLElement` | id, artifact_version_id, uuid, short_name, qualified_path, element_type | [P4] |
| `ECU`, `SWC`, `Port`, `Interface`, `Runnable`, `Event`, `Signal`, `PDU`, `Frame`, `Network` | typed architecture entities | [P4] |
| `CodeSymbol` | id, repo, commit, file, symbol, line_start, line_end, language | [P4] |
| `TestCase`, `TestRun`, `TestResult` | ids, requirement links, run metadata, outcome, artifacts | [P6] |
| `Finding` | id, severity, status, reproducibility, owner, suspected_root_cause, review_state, evidence links | [P6] |
| `ChangeSet` | id, base_version_id, target_version_id, scope, author, created_at | [P7] |
| `Diagram` | id, mermaid_source, rendered artifacts, evidence bindings | [P7] |
| `Conversation`, `Message` | id, workspace_id, slots, content, meta | [P2] (migrated from `chat.db`) |
| `AnswerAudit` | id, request_id, question, scope, status, claims, citations, tools_used, model_route, latency, created_at | [P2] |
| `Job` | id, kind, state, progress, payload, error, created_at, updated_at | [P2] |
| `ModelRoutingPolicy` | id, task, route, conditions, priority, enabled | [P8] |
| `UserRole` | user_id, tenant_id, project_id, role | [P2]/[P8] |

### 3.2 Core trace links

| Link | From → To | How it is established | Phase |
|---|---|---|---|
| Requirement → ArchitectureElement | requirement id → SWC/Port/Runnable/etc. | extracted from spec text near the requirement id, **proposed** until reviewed | [P4]/[P6] |
| ArchitectureElement → ARXMLElement | typed element → ARXML qualified path | deterministic ARXML parse + reference resolution | [P4] |
| ARXMLElement → CodeSymbol | ARXML runnable/port → C function | symbol + call-graph match against the repository at a pinned commit | [P4] |
| Requirement → TestCase | requirement → test case | explicit link in the test artefact, or import from a requirements-traceability file | [P6] |
| TestCase → TestRun → TestResult | test → run → outcome | test-report ingestion (JUnit / pytest / CSV) | [P6] |
| Finding → evidence | finding → citations | created by a triage/diff tool | [P6]/[P7] |
| ChangeSet → impacted entities | change set → requirements/components/tests | deterministic diff + graph traversal | [P7] |

Every link has a **status**: `proposed` · `machine_extracted` · `reviewed` · `approved` ·
`rejected`. Only `approved` links may be presented as established fact; the others are
presented as proposals with their extraction method and confidence.

### 3.3 Provenance rules (non-negotiable)

1. Every graph node, edge, claim, citation, and finding carries
   `artifact_version_id` + `source_location_id` (or an explicit `not_applicable`).
2. Every edge carries `extraction_method` (`parser` | `regex` | `llm` | `import`),
   `confidence`, `is_inferred`, `lifecycle_state`.
3. **No untyped "AI relationship" may exist.** If the predicate is not in the relation
   vocabulary, the edge is rejected at write time.
4. Inferred edges are visually and structurally distinct everywhere, and can never
   satisfy a `VERIFIED` status on their own.

---

## 4. Layering

```
apps/api            HTTP boundary: routing, authn, validation, pagination
apps/worker         background job runner (Phase 2+)
src/interfaces      ports & protocols — the stable seams
src/application     use cases: ask, ingest, diagnose, diff, trace
src/domain          entities, value objects, policies (pure, no I/O)
src/ingestion       parsers → canonical content (artifact-scoped, versioned)
src/retrieval       planner, hybrid retrieval, graph expansion, rerank
src/tools           deterministic tools (ARXML, diff, code, tests, graph)
src/knowledge       typed graph store, evidence store, registry store
src/generation      composer, verifier, answerability gate
src/audit           audit log writer, redaction, policy evaluation
src/evaluation      golden datasets, metrics, ablation
```

**Dependency rule:** `domain` imports nothing. `application` imports `domain` and
`interfaces`. `apps/*` import `application`. Nothing imports `apps/*`.

Phase 1–2 do **not** move files. The layering above is the target; the migration is
incremental (see §8) and new modules adopt it immediately.

---

## 5. Request pipeline (target)

### 5.1 Intent router

Input → intent + entities + scope. Intents:

`spec_question` · `arxml_topology` · `requirement_traceability` · `code_analysis` ·
`test_failure_analysis` · `cross_release_comparison` · `report_generation` ·
`research` · `change_impact`.

Today `src/retrieval/query_understanding.py::parse()` already produces a `QueryPlan`
with an `intent` literal. The target adds the three missing intents and maps every
intent to a **tool-first policy** (§5.2).

### 5.2 Tool-first policy

For ARXML, diffs, test results, requirement records, code symbols and any calculation,
a deterministic tool runs **before** the model is consulted. The model's job is to
explain the tool output, never to produce it.

| Intent | Tools first | Then LLM |
|---|---|---|
| `arxml_topology` | `query_arxml_path`, `resolve_arxml_references` | explain the tree |
| `requirement_traceability` | `trace_links`, `trace_coverage` | summarise the matrix |
| `test_failure_analysis` | `cluster_failures`, `link_failures_to_changes` | hypothesise root cause (marked inference) |
| `change_impact` | `diff_arxml_versions`, `analyze_change_impact` | rank and explain impact |
| `spec_question` | `search_corpus` (exact requirement/API/ECUC lookup) | compose a cited answer |

### 5.3 Retrieval planner

1. **Scope first.** Apply project / branch / ECU / vendor / release / source-type /
   access-policy filters *before* retrieval, never after.
2. **Hybrid retrieval.** Lexical (BM25) + dense (TF-IDF today, optional embedding model
   later) fused with RRF; exact-match channels for requirement ids, API names and
   ECUC parameters.
3. **Graph expansion only when relevant** (intent-driven), with a hard hop/depth cap.
4. **Dedupe + rerank**, then **evidence selection** to `final_evidence` (12 today).

### 5.4 Answer composer + verifier + answerability gate

The composer produces typed claims, never free text:

```
EvidenceClaim {
  statement, kind: fact|interpretation|assumption|recommendation,
  citations: [Citation], conflicts: [Citation], assumptions: [str]
}
```

The verifier then computes the answerability status:

```
VERIFIED              ⟸ a deterministic tool ran AND its result agrees with the
                        cited authoritative source for this claim
EVIDENCE_SUPPORTED    ⟸ every claim has ≥1 citation whose location contains support,
                        and no deterministic validation applies
NEEDS_ENGINEER_REVIEW ⟸ some claim is partially supported, two sources conflict,
                        a cited artifact version differs from the requested scope,
                        or the claim is an interpretation
INSUFFICIENT_EVIDENCE ⟸ no claim has supporting evidence → answer is replaced by a
                        statement of what is missing, naming artifact/scope
```

A **conflict** is never silently resolved: both citations are shown with their versions
and the answer is downgraded to `NEEDS_ENGINEER_REVIEW`.

---

## 6. Platform services

### 6.1 Artifact registry (§3.1)

A new SQLite file `data/canonical/registry.db` with ordered, idempotent SQL migrations in
`src/registry/migrations/` and a `schema_version` table. No ORM, no new dependency.
`Project`/`Workspace`/`Artifact`/`ArtifactVersion`/`SourceLocation`/`Citation`/
`EvidenceClaim`/`ValidationResult`/`Job`/`AnswerAudit` land in Phase 2.

### 6.2 Object store

The filesystem is the object store: `pdf/`, `pdf/uploads/`, `data/sources/`,
`data/graphs/`, `data/reports/`. Every file gets a content hash, a source URI, an
upload timestamp, an owner, a project, a branch, a release and an access policy. The
registry stores the metadata; the bytes stay where they are. A later S3/Azure adapter
implements the same `ObjectStore` protocol.

### 6.3 Vector retrieval

`VectorStore` protocol with `HybridIndex` (local, default) and `QdrantIndex`
(already written, currently unwired) implementations. Both carry the same payload
contract, which `src/indexing/collections.py::payload_for()` already defines and which
**must be extended** with `artifact_id`, `artifact_version_id`, `source_type`,
`language` and `source_location_id`. The existing default-deny tenant filter in
`qdrant_index.build_mandatory_filter()` becomes the shared policy.

### 6.4 Model routing

`src/model_routing/router.py` already implements task → route with a `LOCAL_ONLY_TASKS`
set. Target: add `ModelRoutingPolicy` rows so routing is data, not code, and record
every routing decision in the audit trail (§6.5). Controlled project data is redacted
(`src/security/redaction.py`) or blocked before any external request unless the tenant
policy explicitly allows it. The token map never leaves the local boundary.

### 6.5 Audit trail

`AnswerAudit` records: request id, user, tenant/project scope, question, resolved
scope, answerability status, claims, citations, tools invoked (and their verdicts),
model route, latency, and the retrieval plan. Separate audit events for ingestion,
retrieval, tool execution, export and model requests. `src/observability/logging.py`
becomes the emitter, with a `request_id` propagated through the pipeline.

### 6.6 Background jobs

Long-running work (ingestion, re-indexing, ARXML parsing, report rendering) moves to
`Job` rows processed by a worker, so the API never blocks and the UI can show real
progress. Phase 2 delivers the table and a simple in-process worker; the `jobs` API is
additive (`GET /api/v2/jobs/{id}`).

---

## 7. Frontend architecture

### 7.1 Shell

A persistent left navigation (collapsible) with the module switcher:

```
Workspace ▸ [project ▾]
─────────────
▸ Chat                (A)
▸ Knowledge           (B)
▸ ARXML Explorer      (C)
▸ Graph               (D)
▸ Requirements        (E)
▸ Tests               (F)
▸ Diffs & Impact      (G)
▸ Diagrams & Reports  (H)
▸ Evaluation & Admin  (I)
─────────────
[scope chips]  [theme]  [user]
```

### 7.2 Evidence chat (A)

Compact engineering chat. The composer carries **attachments** and **scope filters**
(project, branch, ECU, release, source types, artifact versions). Each assistant
response is a card with:

* the answerability status badge (VERIFIED / EVIDENCE_SUPPORTED / NEEDS_REVIEW /
  INSUFFICIENT_EVIDENCE);
* expandable sections: **Answer · Evidence · Reasoning summary · Assumptions ·
  Tool results · Exclusions · Audit**;
* interactive citations — clicking one opens the **evidence drawer** at the exact
  source location (PDF page preview, ARXML tree + qualified path, code symbol
  reference, requirement/test links, graph path, conflict/version info).

There is **no hidden chain of thought**. The "reasoning summary" is a short,
structured rationale: which scope was searched, which tools ran, which conflicts exist.

### 7.3 Workbenches

| Workbench | Minimum viable content |
|---|---|
| ARXML Explorer | tree + search + reference navigation + validation results |
| Graph Explorer | typed nodes/edges, provenance filter, path view |
| Traceability Matrix | bidirectional requirement ↔ code ↔ test, coverage, orphans |
| Test Intelligence | failure clustering, timeline, linked changes, evidence |
| Diff & Impact | base/target selection, structural diff, impacted-entity list |
| Mermaid Studio | source editor, live preview, export, evidence bindings |

### 7.4 Two UIs, one backend

The repository ships a **legacy Streamlit client** and the **React workspace**. The
Streamlit app has no access to the new modules and was the reason the user saw "no UI
change". Target: **React is the product; Streamlit enters maintenance mode** — it keeps
working against `/api/*` unchanged, and a banner in the Streamlit app points to the
workspace. The React app is served by the `frontend` Compose profile and documented as
the primary surface.

---

## 8. Migration approach (incremental, reversible)

1. **Additive only.** No destructive `ALTER`/`DROP` of `chunks`/`documents`; rebuilding
   the corpus is always the user's choice.
2. **Dual-read, single-write.** The existing `chunks` table stays the source of truth
   for retrieval. New provenance tables are populated alongside and are read only once
   they are complete for the artifact in question.
3. **Feature flags.** Reuse `arxml_enabled` / `diff_enabled` / `code_intel_enabled` /
   `cloud_routing_enabled` / `strict_local_only` / `vendor_plugins_enabled`. A flag is
   **off** by default for anything that changes an answer, **on** for anything that only
   adds information.
4. **API stability.** All 47 existing routes keep their path, request shape and
   response keys. New capability ships under `/api/v2/...` or as additive response
   fields. `/api/chat` responses gain an additive `answerability` object; older clients
   ignore it.
5. **One commit per phase**, each independently revertible with `git revert <sha>`; the
   down-migration always leaves the old tables readable.
6. **No silent failure.** A tool that cannot run returns a structured error naming the
   searched scope — never an empty result presented as "nothing found".

---

## 9. Non-functional targets

| Concern | Target |
|---|---|
| Determinism | same corpus + same scope → same answerability status and same cited artifacts |
| Auditability | 100 % of answers have an `AnswerAudit` row; 100 % of material claims have ≥1 citation or are downgraded |
| Latency | interactive answer ≤ 8 s on a 5 k-chunk corpus, local model; retrieval-only ≤ 1.5 s |
| Safety | 0 external model requests without an explicit policy grant; 0 unredacted confidential content leaving the boundary |
| Quality gates | pytest green, `tsc --noEmit` clean, `next build` green, Mermaid rendering tests green, API contract tests green |
| Test data | synthetic fixtures only — no proprietary AUTOSAR files, no customer data |

---

## 10. Scope boundaries (explicitly out of the first four phases)

* No automatic ISO 26262 / SOP compliance assertion — the platform reports
  **"evidence available for review"** and requires a qualified human approval.
* No automatic requirement approval — extracted links stay `proposed`/`machine_extracted`
  until a human marks them `reviewed`/`approved`.
* No autonomous code modification — code findings are advisory; a human applies them.
* No external web research in the default path — `research` intent is out of scope
  until an explicit, labelled external-source policy exists.
* No multi-tenant cloud deployment in Phases 1–4 — the tenancy model is designed and
  enforced locally from Phase 2, but the hosted offering is Phase 8.

---

## 11. Phasing summary

| Phase | Theme | Deliverable |
|---|---|---|
| 0 | Discovery | `docs/architecture/*` — this set of documents |
| 1 | Design system + workspace shell | React left nav, module routes, evidence-card status badge, preserved chat + Mermaid/PDF |
| 2 | Provenance data model | `registry.db` + migrations, artifact registry, job framework, audit skeleton |
| 3 | Ingestion + evidence model | artifact-scoped ingestion, citations, `EvidenceClaim`, `ValidationResult` |
| 4 | ARXML as structured data | typed ARXML graph, line locations, the 6 deterministic tools, ARXML Explorer |
| 5 | Retrieval + answerability gates | scoped hybrid retrieval, graph-aware planner, the 4 status gates, audit trail |
| 6 | Requirements & tests | requirement/test ingestion, traceability matrix, failure clustering, findings |
| 7 | Diff/impact + reports | change-impact engine, Mermaid evidence binding, PDF Evidence Package |
| 8 | Routing, evaluation, hardening | policy-based model routing, golden dataset + metrics, CI, production hardening |
