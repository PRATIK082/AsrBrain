# AsrBrain — Current State (Phase 0 discovery)

> Repo: `PRATIK082/AsrBrain` · Branch: `feature/mermaid-pdf-diagram-rendering`
> HEAD at time of writing: `73a80bb` · Baseline: `144919f`
> Scope: a factual inventory of the repository as it stands. Nothing here is aspirational.
> Every "absent" claim was verified by reading the code, not inferred from documentation.

---

## 1. Repository map

```
RAG_LLM/
├── apps/
│   ├── api/main.py                 FastAPI app — 47 routes (single module, no routers)
│   └── streamlit/app.py            Legacy Streamlit chat UI — 726 lines, 7 tabs
├── src/
│   ├── assistant/                  knowledge.py, triage.py            (read-only assistant layer)
│   ├── chat/store.py               ChatStore — conversations, messages, slots, feedback (SQLite)
│   ├── code_intelligence/          advisory.py, sarif.py
│   ├── config/settings.py          Settings dataclass + env overrides
│   ├── diff/engine.py              DiffItem, diff_records, diff_arxml_topologies
│   ├── evaluation/                 ablation, datasets, enterprise_categories, metrics, run
│   ├── generation/                 answer, citations, enterprise_prompts, prompts, providers,
│   │                               routing, verification
│   ├── indexing/                   build, collections, hybrid, opensearch_security, qdrant_index
│   ├── ingestion/                  chunking, diagram_mermaid, metadata, parsers, parser_adapter,
│   │                               pdf_extract, pipeline, processors, project_sources, vlm
│   │   └── arxml/                  models, parser, graph_export
│   ├── model_routing/router.py     Task → route policy
│   ├── observability/logging.py    JSON stage logging
│   ├── plugins/base.py             VendorPlugin protocol + registry
│   ├── retrieval/                  clarify, context, context_rules, fusion, graph, metadata_filter,
│   │                               modalities, modality_fusion, normalize, pipeline, planner,
│   │                               query_rewriting, query_understanding, reranking
│   ├── schema/                     canonical, documents, graph, multimodal, multimodal_graph, queries
│   ├── security/                   context, policy, redaction
│   └── workflows/                  router, stages, suggest
├── frontend/                       Next.js 14.2 app — institutional assistant UI
├── tests/                          unit/ (18 files), integration/ (4), retrieval/, fixtures/
├── docs/                           25+ audit/plan documents (see §8)
├── config/generation.yaml          User-editable token caps
├── data/                           canonical.db, chat.db, indexes/, sources/  (gitignored)
├── docker/                         Dockerfile.api, Dockerfile.frontend, Dockerfile.streamlit
├── docker-compose.yml              api, streamlit, frontend, qdrant, ollama, postgres, opensearch,
│                                   neo4j, redis
├── Makefile                        install, ingest, index, api, ui, test, eval, docker-*
├── requirements.txt                FastAPI, uvicorn, pydantic v2, numpy, scikit-learn, rank-bm25,
│                                   pypdf, httpx, streamlit, qdrant-client (optional)
└── reports/evaluation/             validated.json, comparison.md
```

### 1.1 What is *not* here

* **No `.github/` directory → no CI.** Nothing runs on push or pull request today.
* **No migrations directory, no Alembic, no ORM.** Schema is created by `CREATE TABLE IF NOT EXISTS`
  strings embedded in the modules that own them.
* **No `pyproject.toml`**, no linter/formatter/type-checker configuration.
* **No `src/graphrag`, `src/tools`, `src/agents`.** Those exist on the sibling branch
  `feature/agentic-graphrag-mindmap-tooling` (`b42220f`) and are **not** on this branch.
* No component-test or e2e framework in `frontend/`.
* No license inventory file, despite `LICENSE` being present.

---

## 2. Request and data flow

### 2.1 Answer path (`POST /api/chat`, `POST /api/chat/stream`)

```
client
  → ChatRequest (pydantic)  apps/api/main.py
  → ChatStore.merge_slots(conversation_id, releases/platforms/modules)      [SQLite chat.db]
  → run_staged(get_pipe(), message, spec, cancel, slots, history)           src/workflows/stages.py
      → parse()                    src/retrieval/query_understanding.py  → QueryPlan
      → missing_slots()            src/retrieval/clarify.py             → ["release","platform"]
      → (clarify gate)             → 403-style clarify event, no answer
      → plan()                     src/retrieval/planner.py             → modality plan
      → RetrievalPipeline.retrieve()                                     src/retrieval/pipeline.py
            → HybridIndex (BM25 + TF-IDF dense)  src/indexing/hybrid.py
            → fusion (RRF, k=60) → rerank → parent-expand → compress
            → per-release routing, exact-first modality lookups
      → generate()  src/generation/answer.py   (Ollama | OpenAI-compat | extractive fallback)
      → verify()    src/generation/verification.py  → verdicts, claim_support_rate, citation_coverage
      → confidence_score() → confidence / level / should_abstain
      → extract_edges()  src/retrieval/graph.py  → per-request co-mention edges
      → events: status | clarify | evidence | token | complete
  → ChatStore.add_message(cid, "assistant", answer, {trace, llm, plan, graph, evidence, followups})
  → SSE `data: {...}\n\n`
```

**Current answer status model:** there is none. The API returns `confidence` (float) and
`level` ("Low"/"Medium"/"High") plus `citation_coverage` / `claim_support_rate`. There is no
`VERIFIED` / `EVIDENCE_SUPPORTED` / `NEEDS_ENGINEER_REVIEW` / `INSUFFICIENT_EVIDENCE`
discriminator anywhere in the codebase.

### 2.2 Ingestion path

```
pdf/*.pdf  → src/ingestion/pipeline.py::run(pdf_dir, out)
              → parsers.py (Docling-opt → PyMuPDF → pypdf, quality routing)
              → chunking.py → Chunk (src/schema/documents.py)
              → metadata.py (release/platform/doctype detect, req/API/ECUC signals)
              → processors.py (tables, figures)
              → writes <out>/canonical.db   [tables: documents, chunks, tables, figures]
              → writes <out>/<document_id>.quality.json, <out>/ingestion_report.json
  → src/indexing/build.py --canonical data/canonical/canonical.db --out data/indexes/hybrid
              → HybridIndex.save()  → <path>.npz + <path>.meta.json
```

A **second, independent writer** exists: `src/ingestion/project_sources.py::ingest_source()`
creates its own `documents`/`chunks` tables (same column names) and inserts into the same
`data/canonical/canonical.db`. The two schemas are column-compatible but not schema-governed.

### 2.3 ARXML path

```
POST /api/arxml/upload (multipart)
  → src/ingestion/arxml/parser.py::parse_arxml(path)   [stdlib ElementTree, XXE-rejecting]
      → ArxmlTopology (pydantic)  — components, ports, interfaces, connectors, runnables, ECUC
      → unresolved_refs
  → in-memory dict _ARXML_STORE  (apps/api/main.py)   ← NOT persisted, lost on restart
  → src/ingestion/arxml/graph_export.py::export_graph(topo) → {nodes, edges, unresolved}
  → GET /api/arxml/topology, GET /api/arxml/nodes/{id}/neighbors (in-memory BFS, depth ≤ 3)
```

### 2.4 Diagram path (Mermaid / PDF)

```
POST /api/diagrams/recreate
  → src/ingestion/diagram_mermaid.py::recreate_diagrams_for_pdf
      → page gate (caption regex | vector drawings)  → PyMuPDF page → PNG bytes
      → src/ingestion/vlm.py::recreate_mermaid_from_image
          → httpx POST to Ollama /api/chat (images=[b64]) or OpenAI /chat/completions
          → validate_mermaid()  [structural regex only — NO mermaid compiler runs server-side]
          → {"mermaid": …} | {"fallback": …, "error": …}
  → client renders:
      Streamlit: mermaid@10 CDN (_render_mermaid_blocks)
      React:     frontend/components/chat/MermaidDiagram.tsx (dynamic import("mermaid"),
                 securityLevel "strict", dangerouslySetInnerHTML of sanitised SVG)
```

---

## 3. Existing capabilities (working today)

| Area | Capability | Where |
|---|---|---|
| Ingestion | PDF → text/tables/figures with quality report, release/platform/module detection | `src/ingestion/` |
| Retrieval | Hybrid BM25 + TF-IDF, RRF fusion, rerank, parent expansion, compression, per-release routing, exact-first modality lookup | `src/indexing/hybrid.py`, `src/retrieval/` |
| Query understanding | Typed `QueryPlan`, slot-fill clarification gate, intent classification | `src/retrieval/query_understanding.py`, `clarify.py` |
| Generation | Ollama local + OpenAI-compatible cloud + extractive fallback; token caps in YAML | `src/generation/` |
| Verification | Claim extraction, per-claim citation verdicts, version/platform consistency, confidence & abstain | `src/generation/verification.py` |
| Chat contract | Conversations, messages, slots, feedback, SSE streaming, cancel, export/import bundle | `src/chat/store.py`, `apps/api/main.py` |
| ARXML | XML parse with XXE rejection, qualified paths, unresolved-ref detection, graph export, neighbour BFS | `src/ingestion/arxml/` |
| Diff | Generic canonical-key diff with severity/risk/action | `src/diff/engine.py` |
| Code review | Advisory static checks + SARIF output (human approval required) | `src/code_intelligence/` |
| Diagrams | Page-image extraction, VLM → Mermaid, structural validation, client-side render | `src/ingestion/diagram_mermaid.py`, `vlm.py` |
| Assistant (new) | Corpus manifest, capabilities, project overview with concept flow, starter prompts, deterministic symptom triage over 9 families | `src/assistant/` |
| Security primitives | `SecurityContext`, default-deny content classification, reversible redaction, policy routing, vendor plugin registry | `src/security/`, `src/plugins/`, `src/model_routing/` |
| Evaluation | Benchmark runner, metrics, ablation, enterprise categories | `src/evaluation/` |
| UI | React institutional assistant UI (ChatGPT-class shell) **and** a separate legacy Streamlit chat UI | `frontend/`, `apps/streamlit/app.py` |

## 4. Missing capabilities (required by the target product)

| Required capability | Current state | Gap |
|---|---|---|
| **Answerability gate** (`VERIFIED` / `EVIDENCE_SUPPORTED` / `NEEDS_ENGINEER_REVIEW` / `INSUFFICIENT_EVIDENCE`) | absent | confidence float only |
| **Provenance-first data model** — Artifact, ArtifactVersion, SourceLocation, Citation, EvidenceClaim, ValidationResult | absent (only `Chunk` / `DocumentRecord` / `CanonicalContent` / `MultimodalEvidence`) | no artifact registry, no versioning, no job/audit tables |
| **Requirements intelligence** — CSV/XLSX/JSON/API ingestion, normalisation, trace-link lifecycle | absent | no `requirements` / `requirement_versions` / `trace_links` tables |
| **Test intelligence** — JUnit/pytest/CSV ingestion, TestCase/TestRun/TestResult, failure clustering | absent | no test tables, no findings model |
| **Findings model** (severity, status, reproducibility, root cause, review state) | absent | only `DiffItem` and SARIF output |
| **Object storage with content hash + access policy** | partial — `sha256` on `documents`/`chunks` only | no owner, project, branch, release, access policy, upload time |
| **Relational schema with migrations** | absent — `CREATE TABLE IF NOT EXISTS` inline, 2 writers | no versioned migrations, no indexes, no foreign keys |
| **Vector retrieval behind an abstraction** | partial — `HybridIndex` concrete, `qdrant_index.py` is an unwired mirror with default-deny filters | no interface, no adapter selection |
| **Graph abstraction** — local dev impl + production adapter, typed nodes/edges with schema/provenance/confidence/method/version/lifecycle | absent — edges derived per request by co-mention; no `GraphNode` model; no persistence | no traversal API over stored graph |
| **ARXML as structured data** | partial — parse + qualified paths + unresolved refs | no line numbers, no UUID capture, no `autosar_release`, no source locations, no validation report, no persisted artifact, several model fields never populated |
| **Deterministic ARXML tools** — `validate_arxml`, `resolve_arxml_references`, `query_arxml_path`, `diff_arxml_versions`, `trace_communication_path`, `analyze_change_impact` | absent | only `export_graph` + `neighbors` exist |
| **Change impact engine** | partial — `diff_records` over caller-supplied lists; `diff_arxml_topologies` covers components/ports/interfaces only (docstring overstates) | no impact graph, no impacted-entity resolution, no ChangeSet model |
| **Mermaid evidence binding** | absent — Mermaid is a free-text artifact | no link from diagram → graph node → evidence claim |
| **PDF Evidence Package export** | absent | no export format |
| **Job framework for long ingestion** | absent | ingestion is synchronous in the request |
| **Audit trail** | absent — `log_stage` only | no answer_audits table, no request-id plumbing, no per-answer audit record |
| **RBAC / project isolation in the request path** | primitives exist but are **not wired** into any endpoint | `SecurityContext` is never constructed in `apps/api/main.py` |
| **Evaluation harness for answerability** | partial — generic benchmark metrics | no golden dataset with expected answerability status / allowed source IDs / forbidden claims |
| **CI** | absent | no pipeline at all |
| **Frontend module switcher** (Knowledge, ARXML Explorer, Graph, Requirements, Tests, Diffs & Impact, Diagrams & Reports, Evaluation & Administration) | absent — the React shell switches assistant/arxml/diff/code only | left-nav workbench missing |
| **Evidence drawer** (PDF page preview, ARXML tree + qualified path, code symbol ref, graph path) | absent | sources are a flat list |

---

## 5. Technical debt

| # | Debt | Impact | Location |
|---|---|---|---|
| TD-1 | `src/ingestion/project_sources.py:176` calls `parse_arxml(text, artifact_id="summary").get("topology", {})` — wrong signature and wrong return type; the `except Exception: return ""` swallows the `TypeError` | ARXML summaries are **always empty** | `src/ingestion/project_sources.py` |
| TD-2 | `HybridIndex.bm25_scores` computes `idf` inside the loop and never uses it; the scoring loop reads `term` from the enclosing scope | the BM25 contribution is not idf-weighted as written | `src/indexing/hybrid.py` |
| TD-3 | `diff_arxml_topologies` docstring claims connectors/runnables/ECUC are diffed; only components/ports/interfaces are | false sense of coverage | `src/diff/engine.py` |
| TD-4 | `_norm_api` defined but never called | dead code | `src/diff/engine.py` |
| TD-5 | `ClaimVerdict` referenced nowhere outside `queries.py` | verdicts are recomputed ad hoc | `src/schema/queries.py` |
| TD-6 | `TypedEdge` / `Provenance` / `NODES` / `RELATIONS` are not wired to `GraphEdge` or to any store | typed graph vocabulary is unused | `src/schema/multimodal_graph.py` |
| TD-7 | `src/indexing/collections.py` payload contract is used **only** by a unit test | the production index ignores tenant/project/classification fields | `src/indexing/collections.py` |
| TD-8 | `src/indexing/qdrant_index.py` is not imported by any `src/` or `apps/` module | Qdrant is an unwired mirror | `src/indexing/qdrant_index.py` |
| TD-9 | `src/security/*`, `src/model_routing/`, `src/plugins/` are not wired into the request path | security primitives are decorative today | `apps/api/main.py` |
| TD-10 | `src/schema/documents.py::Chunk` declares `printed_page_number`, `chapter_number`, `chapter_title`, `entity_tags`, `table_data`; the `chunks` table has none of them | silent schema drift between the dataclass and the store | `src/schema/documents.py` vs `src/ingestion/pipeline.py` |
| TD-11 | `src/ingestion/arxml/models.py` declares `uuid`, `Port.comspec`, `RunnableEntity.events/data_accesses/server_call_points`, `EcucParameter.value_type/reference_target`, `RteConnector.*_ref` — none are ever populated | the model over-promises; ARXML facts are lost | `src/ingestion/arxml/` |
| TD-12 | ARXML store is an in-memory dict | every ARXML upload is lost on restart; no artifact history | `apps/api/main.py` (`_ARXML_STORE`) |
| TD-13 | Two independent writers to `canonical.db` with no shared schema definition | silent divergence risk | `src/ingestion/pipeline.py`, `src/ingestion/project_sources.py` |
| TD-14 | `ChatStore.patch`/`delete` return a bool from connection-cumulative `conn.total_changes` | may report a wrong success value | `src/chat/store.py` |
| TD-15 | `apps/api/main.py` is a single 695-line module with 47 routes | every change risks import cycles; no router boundaries | `apps/api/main.py` |
| TD-16 | `apps/streamlit/app.py` (726 lines) and `frontend/` (Next.js) are **two independent UIs** against the same API | users get different capability from the same backend; the Streamlit one has none of the assistant features | `apps/streamlit/app.py`, `frontend/` |
| TD-17 | `run_ingest` is an import alias for `pipeline.run` | the name suggests a different entry point | `apps/api/main.py:23`, `apps/streamlit/app.py:122` |
| TD-18 | No indexes or foreign keys on either SQLite store | full scans as the corpus grows | `src/ingestion/pipeline.py`, `src/chat/store.py` |
| TD-19 | `nope.db` — a stray empty file at repository root | noise | repo root |
| TD-20 | `docker-compose.yml` declares postgres, neo4j, opensearch, redis but **no application code uses them** | the stack implies an architecture that does not exist | `docker-compose.yml` |

## 6. Security and functional-safety risks

| # | Risk | Why it matters | Mitigation available today |
|---|---|---|---|
| SR-1 | **No authentication or authorisation on any route.** All 47 endpoints are open; `SecurityContext` is never built in the request path | a deployment with real project data leaks it | none — must be built |
| SR-2 | **No tenant/project isolation in retrieval.** `HybridIndex` has no tenant field; `payload_for` does but is unused | a multi-tenant deployment cannot be safe | `collections.payload_for` + `qdrant_index.build_mandatory_filter` exist as a pattern |
| SR-3 | **Cloud routing defaults to off** (`cloud_routing_enabled=false`, `strict_local_only=true`) but `/api/chat` accepts a per-request `provider: "openai_compat"` + `api_key` with **no policy check** | a client can route controlled project data to a cloud model regardless of tenant policy | `src/security/policy.py::routing_decision` + `src/model_routing/router.py::route` exist but are not called |
| SR-4 | Upload endpoints (`/api/documents/upload`, `/api/arxml/upload`, `/api/diagrams/recreate`) have **no file-type, size, or malware validation** | untrusted binaries reach the parsers | none |
| SR-5 | No audit log for ingestion, retrieval, tool execution, export, or model requests | no way to answer "who asked what, and what was sent off-box" | `src/observability/logging.py::log_stage` (JSON, truncated to 2000 chars) |
| SR-6 | `src/security/redaction.py` exists but is not applied anywhere | controlled identifiers (VIN, private IP, e-mail) can reach a cloud provider | the redaction module |
| SR-7 | The corpus is copyrighted AUTOSAR specification text; the chunk store is local, but a cloud provider would receive verbatim spec text | licence exposure | policy + redaction + local-first defaults |
| SR-8 | Confidence is presented as a float without an answerability contract; nothing forbids an unsupported claim from being phrased confidently | functional-safety reviewers cannot tell a verified statement from a plausible one | `verification.py` verdicts exist but are not surfaced as a status |
| SR-9 | `DiffItem` severity/risk are canned strings, not derived from a rule engine | a reviewer may over-trust an auto-generated risk label | `diff_records` is explicit that it never fabricates a change |
| SR-10 | `apps/streamlit/app.py` and `frontend/` are both shipped and reachable; the Streamlit one bypasses every new guard | two different security postures for one product | none |
| SR-11 | The ARXML parser rejects DOCTYPE/ENTITY (XXE hardening) but does **not** capture line numbers or validate against the AUTOSAR schema | "validated" cannot be claimed | parser warning list only |

## 7. Safe incremental migration approach

1. **Additive only.** New tables in new SQLite files or new tables in the existing `canonical.db`
   — never a destructive `ALTER`/`DROP` of `chunks` or `documents`. The corpus is the user's
   property; rebuilding it must always be a user choice, not a migration side effect.
2. **Dual-read, single-write.** The existing `chunks` table stays the retrieval source of
   truth through the migration; the new provenance tables are populated *alongside* it
   during ingestion and are read only once their population is complete for an artifact.
3. **Feature flags for everything new.** The repo already has the pattern
   (`arxml_enabled`, `diff_enabled`, `code_intel_enabled`, `cloud_routing_enabled`,
   `strict_local_only`, `vendor_plugins_enabled`). New capability ships behind a flag
   whose default is **off** for anything that changes an answer, and **on** for anything
   that only adds information.
4. **One SQLite file per concern.** `data/canonical/canonical.db` (corpus),
   `data/canonical/chat.db` (sessions). New: `data/canonical/registry.db` (artifacts,
   projects, versions, jobs, audits). Migrations live beside it in `src/registry/migrations/`
   as ordered, idempotent SQL files with a `schema_version` table — no ORM, no new dependency.
5. **Public API stability.** All 47 existing routes keep their paths, request shapes and
   response keys. New capability is exposed under `/api/v2/...` or as additive fields on
   existing responses. `/api/chat` gains optional response fields; it does not change shape.
6. **The React app becomes the reference UI; Streamlit becomes a maintenance-mode client.**
   Rather than deleting the Streamlit app, mark it as legacy in the README and add the
   assistant's deterministic features to it only if cheap. The React `frontend/` becomes the
   workspace shell. This is the single biggest UX risk and is handled in Phase 1.
7. **Every phase is independently revertible.** Each phase lands as one commit with a
   documented rollback (`git revert <sha>`) and, where data is involved, a documented
   down-migration that leaves the old table readable.
8. **No silent failure.** New code paths that cannot complete must return a structured
   error with the searched scope, never an empty result presented as "nothing found".

## 8. Existing documentation (do not duplicate)

`docs/` already contains: `asrbrain-current-state-audit.md`, `asrbrain-data-classification-policy.md`,
`asrbrain-feature-gap-analysis.md`, `asrbrain-phase2-phase3-migration-plan.md`,
`asrbrain-project-sources.md`, `asrbrain-security-threat-model.md`, `chatbox-integration-plan.md`,
`current-state-audit.md`, `current-system-audit.md`, `failure-analysis.md`, `featureupdate.md`
(§20 determinism / §23 no-invented-evidence rules), `institutional-assistant-ui-plan.md`,
`migration-guide.md`, `migration-risk-register.md`, `migration-risks.md`, `multimodal-gap-analysis.md`,
`operations-guide.md`, `preserved-components.md`, `rag-anything-capability-mapping.md`,
`replacement-components.md`, `rollback-guide.md`, `target-architecture.md`, `troubleshooting.md`,
`ui-and-rag-upgrade-audit.md`.

`docs/architecture/` is a **new** namespace and does not overlap with `docs/target-architecture.md`
(that file describes the multimodal target; the new one describes the evidence-first platform).

## 9. Corpus and environment facts (measured)

| Fact | Value |
|---|---|
| Indexed documents | 3 |
| Chunks | 4 706 |
| Tables / figures | 590 / 331 |
| Distinct requirement IDs | 317 |
| Distinct API names | 967 |
| ECUC parameters | 313 |
| Releases | R22-11, R24-11 |
| Platform | Foundation |
| Modules | Com (4 402 chunks), SOME-IP (169), unassigned (135) |
| C source files in repo | 0 (so `code.*` tools have nothing to analyse until sources are uploaded) |
| Python | 3.14 |
| Tests | 106 passing (`python -m pytest -q`) |
| Frontend build | `npx next build` OK — route `/` 58.7 kB, 147 kB First Load JS |
| LLM | Ollama `qwen3:14b` at `http://127.0.0.1:11434`, timeout 180 s |
| Embeddings | TF-IDF (`embedding_backend=tfidf`) |

## 10. Open questions for the product owner

1. **Which UI is the product?** The React `frontend/` (needs `npm run dev`) or the Streamlit
   app (one command, already deployed, but no assistant features)? *Phase 1 implements the
   workspace shell in React and leaves Streamlit intact; a later phase can add a thin
   assistant panel to Streamlit if the answer is "both".*
2. **PostgreSQL or stay on SQLite?** The Compose file already ships postgres, but no code
   uses it. *Phase 2 keeps SQLite with a migration framework, so PostgreSQL is an adapter
   decision later, not a rewrite.*
3. **Is a graph database in scope now?** *No — Phase 2–4 implement a typed graph over SQLite
   behind an interface; Neo4j/RDF is a Phase 4+ adapter, matching the "local dev impl +
   production adapter" requirement without blocking earlier phases.*
