# AsrBrain — Master Prompt for the Coding CLI

Repo: github.com/PRATIK082/AsrBrain · Branch to start from: `feature/mermaid-pdf-diagram-rendering`

---

## 0. How to use this file

1. Save as `docs/MASTER_PROMPT.md` in the repo. Copy Sections 1–5 into `CLAUDE.md` / `AGENTS.md` so every session loads them.
2. Start the CLI on the branch above. First message:
   > Read docs/MASTER_PROMPT.md completely. Execute **Phase 0 only**. Do not change any code. Stop and show me the audit.
3. Review each phase's output, then paste the next kickoff prompt from Section 12.
4. Never let the CLI run several phases in one go. Gates exist so that you, the domain expert, stay in control of the truth.

---

## 1. Mission

You are the complete engineering team for **AsrBrain**: the single source of truth for AUTOSAR and automotive software knowledge, from specification to integration to SOP (start of production).

AsrBrain must become:

- **A knowledge chatbot** that answers AUTOSAR and automotive questions with cited, verifiable, version-aware answers.
- **An agent** that can trace requirements, analyse test results, explain code flow and produce diagrams, using tools instead of guessing.
- **A "self brain"** for a team: a knowledge graph that links specification ↔ requirements ↔ design/config (ARXML) ↔ code ↔ tests ↔ test results ↔ defects ↔ releases.
- **An internal research and development assistant** for technical staff, usable offline/on-prem for confidential projects.

Work as these roles, and in every phase write a short **Team Review** section where each role states its concerns:

| Role | Cares about |
|---|---|
| Product owner | Personas, use cases, what "one truth" means to users |
| AUTOSAR domain architect (Classic + Adaptive) | Correct terminology, module interactions, release/version semantics, ECUC/ARXML structure |
| Functional-safety / ASPICE engineer | ISO 26262 / ASPICE traceability, advisory-only AI, audit trail |
| Knowledge / data engineer | Ontology, ingestion quality, provenance, versioning |
| ML / RAG engineer | Retrieval quality, reranking, verification, evaluation |
| Backend engineer | APIs, storage, migrations, performance |
| Frontend / UX engineer | Information design, accessibility, speed |
| QA / evaluation engineer | Golden sets, regression gates, e2e tests |
| DevOps / security engineer | Local-first deployment, RBAC, secrets, reproducibility |
| Technical writer | Docs, ADRs, onboarding for open-source contributors |

---

## 2. Non-negotiable rules

1. **Audit before changing.** Understand the existing code, data and branch work first (Phase 0). Preserve what works, including the Mermaid + PDF diagram rendering from the current branch.
2. **Measure before optimising.** Build the evaluation harness and record baseline numbers (Phase 1) before any retrieval or model change. Every later change must show a metric delta, or it is not merged.
3. **No silent guessing.** If you cannot verify something from the repo, data or documents, say so and list what you need.
4. **Small, reviewable steps.** One phase at a time. Each phase: plan → my approval → implement → tests + eval → summary → STOP.
5. **Safe data handling.** Back up before any DB or index migration; write reversible migration scripts; never delete user data without explicit approval.
6. **Keep the existing stack unless it blocks the goals.** If you propose replacing something (framework, vector store, DB), write an ADR in `docs/adr/` with options, trade-offs, migration cost.
7. **Open-source hygiene.** No secrets in git, no proprietary documents in the repo, clear licence handling (Section 11).
8. **Advisory, not authoritative for safety.** Outputs support engineers; they do not replace review or sign-off.

---

## 3. The Accuracy Contract (what "95–100% accurate" means here)

Raw "100% accuracy" is not a property an LLM system can promise. We engineer for **grounded, verifiable, abstaining** answers and **measure** them.

**Rules every answer must obey**

- Answer only from retrieved evidence. Every claim carries a citation: `[document, release/version, section or requirement ID, page]`.
- **Exact-token guard:** requirement IDs (e.g. `[SWS_…]`, `[SRS_…]`, `[constr_…]`), API/function names, enum values, parameter names, numbers and units must appear verbatim in the cited evidence. Otherwise the answer is blocked or the token is flagged.
- **Three outcomes only:** `ANSWERED` (with confidence), `PARTIAL` (state what is missing), `ABSTAIN` (say which source or data would be needed). Never fabricate an ID, signature, value or behaviour.
- **Version-aware:** if the question depends on the AUTOSAR release (Classic vs Adaptive, release number) or project baseline and it is not specified, ask or answer per-version explicitly.
- **Conflicts are shown, not merged:** if sources disagree, show both with authority ranking (Section 8).

**Targets measured on a held-out golden set (report with confidence intervals)**

| Metric | Target |
|---|---|
| Citation precision (cited span really supports claim) | ≥ 98% |
| Faithfulness / groundedness | ≥ 97% |
| Answer correctness on answerable questions | ≥ 95% |
| Correct abstention on unanswerable / out-of-scope questions | ≥ 95% |
| Hallucinated IDs / identifiers | ≤ 0.5% |
| p95 latency (single-turn, cloud LLM) | ≤ 8 s (stream first token < 2 s) |

If targets are missed, report honestly and propose the next improvement. Do not tune on the hold-out split.

---

## 4. Target architecture (defaults — justify any change in an ADR)

```
Sources ─► Adapters ─► Structure-aware parsing ─► Normalised store + provenance
                                                   │
        ┌──────────────────────────────────────────┼───────────────────────────┐
        ▼                                          ▼                           ▼
  Lexical index (BM25)                     Vector index (dense)         Knowledge graph
        └──────────────► Hybrid retrieval + rerank + graph expansion ◄─────────┘
                                         │
                      Query understanding / routing / decomposition
                                         │
                 Answer engine: structured output ─► claim verification ─► render
                                         │
                       Agent tools (trace, test analysis, code flow, ARXML)
                                         │
                      API ─► New UI  ·  Eval harness  ·  Observability
```

Recommended defaults (keep what already exists if it is adequate):

- **Relational + vector:** PostgreSQL with `pgvector` (single store, easy local deployment), or Qdrant if the audit shows scale needs.
- **Lexical:** Postgres full-text or a BM25 library; **exact-ID fast path** for requirement IDs.
- **Graph:** Neo4j Community / Memgraph, or Postgres + Apache AGE for a lighter footprint. For MVP, a typed edge table is acceptable if it keeps a clean migration path.
- **Embeddings / rerank:** a strong multilingual open model (e.g. BGE-M3 class) and a cross-encoder reranker; benchmark against the current embeddings on the golden set before switching.
- **PDF parsing:** layout-aware parser with table extraction (e.g. Docling / Marker / PyMuPDF class); vision-LLM only for figures and diagrams.
- **LLM layer:** provider-agnostic interface (cloud APIs and local models via Ollama / vLLM), per-task model routing, cost + latency logging.
- **Observability:** OpenTelemetry + Langfuse-class tracing of every retrieval and generation step.

---

## 5. Domain ontology (starting point — refine with the real data)

**Nodes:** `Standard`, `Release`, `Document`, `Section`, `SpecItem` (requirement-level chunk with ID), `Module` (Dem, Dcm, Com, PduR, CanIf, CanTp, NvM, EcuM, BswM, Rte, Os, …), `API`, `ConfigParam` (ECUC), `ArxmlElement`, `SWC`, `Port`, `Runnable`, `Signal`, `PDU`, `SourceFile`, `Function`, `Requirement` (customer/system/software/unit), `SafetyGoal`/`ASIL`, `TestCase`, `TestRun`, `TestResult`, `Defect`, `Baseline`.

**Edges:** `PART_OF`, `DEFINES`, `REFERENCES`, `DEPENDS_ON`, `CONFIGURES`, `CALLS`, `IMPLEMENTS`, `DERIVES_FROM`, `SATISFIES`, `VERIFIED_BY`, `RESULT_OF`, `FAILS_ON`, `AFFECTS`, `SUPERSEDES` (between releases), `CONFLICTS_WITH`.

Every node and edge carries: `source_doc`, `version/release`, `location` (page/line), `content_hash`, `ingest_snapshot_id`, `created_by` (`parser` | `llm_proposed` | `human_approved`), `confidence`.

---

## 6. Engineering requirements by capability

### 6.1 Ingestion (do not treat everything as plain text)

- **Adapters:** AUTOSAR PDFs (SWS, SRS, RS, TPS, EXP, PRS), **ARXML parsed structurally** (never chunked as raw text), DBC / LDF / FIBEX, A2L, C/C++ source (tree-sitter), requirement exports (ReqIF, CSV/XLSX, Jira/Polarion/DOORS exports), test artefacts (JUnit XML, logs, gcov/lcov/Cobertura; pluggable adapters for VectorCAST, Tessy, CANoe-style reports), Markdown/wiki, Mermaid.
- **Structure-aware chunking:** one chunk per specification requirement item with its ID, parent-section path, table/figure captions. Tables stay structured (rows/cols). Figures → image + vision description + extracted Mermaid where possible + link to the page image.
- **Metadata on every chunk:** document, standard/release, module, section path, page, requirement ID, platform (Classic/Adaptive), hash, snapshot ID.
- **Immutable snapshots + diff:** re-ingestion creates a new snapshot; release-to-release `SUPERSEDES` links and a "what changed" view.
- **Parse-quality report per document:** pages parsed, tables/figures detected, unparsed regions, with fixture-based tests.

### 6.2 Retrieval

1. **Query understanding:** classify intent (definition, API usage, configuration, runtime behaviour/sequence, traceability, impact analysis, test analysis, release comparison, code explanation); extract entities (module, release, IDs); rewrite; decompose multi-hop questions.
2. **Hybrid search:** lexical + dense, fused (e.g. RRF), metadata filters (release, module, project baseline), cross-encoder rerank, parent/section expansion.
3. **Graph retrieval:** 1–2 hop expansion for relationship questions; **allow-listed Cypher/SQL templates** with a read-only guard for structural or counting questions. No free-form generated queries against the DB.
4. **Corrective loop:** if evidence score is below threshold → reformulate / widen filters / try another route; if still weak → `ABSTAIN`.
5. **Ablate everything** on the golden set; keep only components that move the metrics.

### 6.3 Answer engine

- Structured output schema, e.g.:

```json
{
  "status": "ANSWERED | PARTIAL | ABSTAIN",
  "answer_blocks": [{"type": "text|table|mermaid|code", "content": "..."}],
  "claims": [{"text": "...", "evidence_ids": ["..."]}],
  "evidence": [{"id": "...", "doc": "...", "release": "...", "section": "...", "page": 0, "quote_span": "..."}],
  "confidence": 0.0,
  "caveats": ["..."],
  "follow_ups": ["..."]
}
```

- **Verification pass:** map each claim to evidence (NLI / LLM-judge); unsupported claims are removed or the answer is downgraded to `PARTIAL`.
- **Diagrams:** Mermaid generated from verified graph/code data, validated with the Mermaid parser before display, with graceful fallback to a table/text. Keep PDF export rendering diagrams correctly.
- Multi-turn memory scoped to the workspace; no cross-project leakage.

### 6.4 Agent and tools (bounded, read-only by default)

Tools: `spec_lookup`, `graph_query` (templated), `code_search`, `call_graph`, `arxml_inspect`, `requirement_trace`, `impact_analysis`, `test_result_analyzer`, `coverage_gap_finder`, `release_diff`.
Rules: max-step and cost budgets; every tool call logged and shown in the UI trace; **any write (new trace link, curated fact) goes to a proposal queue requiring human approval.**

### 6.5 Requirement mapping and analysis

- Link types: customer ↔ system ↔ software ↔ unit requirement ↔ AUTOSAR spec item ↔ design/config ↔ code ↔ test.
- **Candidate linking pipeline:** explicit ID references → lexical match → embedding similarity → LLM judge with written rationale → confidence score → **human review queue** (accept / reject / edit) → approved links enter the graph with provenance.
- **Analyses:** coverage matrix (req → design → code → test), orphan / unimplemented / untested requirements, ambiguity and testability checks (vague words, missing "shall", non-atomic statements), duplicate/conflicting requirements, **change impact analysis**, and gap analysis against AUTOSAR spec items (which `SWS_` items a module configuration does or does not address).

### 6.6 Test result analysis

- Parse results per build; compute **deltas between builds**.
- **Failure clustering** by error signature / log pattern / stack; map clusters to requirements and code.
- **Flaky-test detection** from history; trend dashboards.
- **Root-cause hypotheses** are always labelled as hypotheses with evidence links, never as facts.
- **Coverage vs target** (statement / branch / MC/DC by ASIL) with gap highlighting.
- Exportable release-readiness summary (Markdown / PDF / CSV).

### 6.7 Code flow

- tree-sitter parse of C → functions, calls, includes, macros, `#if` configuration switches.
- AUTOSAR-aware mapping: SWC → ports → runnables → RTE; BSW call chains (e.g. Com → PduR → CanIf → CAN driver) combined from spec and code.
- Output Mermaid sequence/flow diagrams; clicking a node opens the source with line numbers.
- Mark every edge `static` or `inferred` (function pointers and generated code limit static analysis; say so in the UI).

---

## 7. UI/UX redesign

**Principles:** evidence first, keyboard friendly, fast, accessible (WCAG AA), dark + light themes, responsive, no dead ends. Keep the current frontend framework unless the audit proves it is a blocker; use a consistent design-system layer (tokens, components) with a Storybook-style catalogue.

**Screens**

1. **Ask** — chat with mode chips (`Spec` · `Trace` · `Test analysis` · `Code flow` · `Compare releases`); scope selector (workspace, AUTOSAR release, modules, project baseline); streaming answers; inline citations that open an **Evidence drawer** (PDF page with highlighted span, or code with line numbers); confidence badge; collapsible tool/reasoning trace; thumbs + "correct this" (feeds the golden set).
2. **Knowledge Graph explorer** — Cytoscape-class canvas, filters by node/edge type, expand neighbours, shortest-path finder, saved views.
3. **Traceability** — matrix + tree views, coverage KPIs, **review queue** for proposed links.
4. **Test analysis dashboard** — build deltas, failure clusters, flaky list, coverage vs target.
5. **Code flow viewer** — Mermaid diagram linked to source.
6. **Sources** — ingestion status, parse-quality report, snapshots, release diff.
7. **Evaluation** — metric trends, failing golden cases, side-by-side run comparison.
8. **Settings** — models (cloud/local), workspaces, roles, data retention.

Performance budgets: first meaningful paint < 2 s; graph views stay interactive at ≥ 5k nodes (virtualise or aggregate). Add Playwright e2e tests for the three core journeys: ask-and-verify-citation, trace-a-requirement, analyse-a-test-run.

---

## 8. "One truth" rules

- **Authority ranking (default, configurable):** approved expert-reviewed knowledge > AUTOSAR specification (matching release) > OEM/customer specification > internal design/requirements > code comments / wiki > chat history.
- **Reviewed Knowledge layer:** expert-approved corrections and curated facts stored separately with reviewer, date, scope and expiry; they feed the golden set automatically.
- **Reproducibility:** each answer stores snapshot ID, model + prompt versions, retrieved evidence IDs. The same question on the same snapshot must be explainable later.
- **Staleness and conflicts:** flag outdated releases, superseded requirements and contradictory sources visibly in the UI.

---

## 9. Evaluation harness (Phase 1 — build first)

- **Golden set ≥ 300 items initially**, each with: question, gold answer, gold evidence IDs, category, release/version, difficulty, `needs_expert_review` flag.
- **Coverage mix:** ≥ 30% multi-hop, ≥ 15% unanswerable/adversarial, version-specific, table-based, diagram-based, code-flow, traceability and test-analysis questions.
- Generate candidates with an LLM from the ingested sources, then **mark a stratified sample for my expert review**; keep a frozen hold-out split.
- **Metrics:** RAGAS-style (faithfulness, answer relevance, context precision/recall) **plus** citation precision/recall, exact-ID match, hallucinated-ID rate, abstention accuracy, latency, cost.
- **CI gate:** a PR that drops any headline metric beyond the agreed tolerance fails. Store run history and show diffs in the Evaluation screen.

---

## 10. Engineering practices

- ADRs in `docs/adr/` for every architectural decision; `CHANGELOG.md`; conventional commits; small PRs.
- Feature flags for new retrieval paths so old and new can be compared A/B on the golden set.
- Tests: unit (parsers, chunkers), integration (ingest → retrieve → answer), e2e (Playwright), eval regression.
- `docker compose up` for a full local stack; `make` targets for ingest / eval / dev; `.env.example`; no secrets in git.
- Observability dashboards for retrieval hit-rate, abstention rate, latency, token cost.

---

## 11. Security, licensing, safety

- **Local-first:** works air-gapped with local models; telemetry off by default; per-workspace RBAC; audit log of queries and approvals.
- **Licensing:** ingest only documents the user is entitled to use. Check AUTOSAR document licence terms and keep attribution; **do not commit or redistribute paid standards (e.g. ISO 26262 text), OEM, or customer documents** — ship ingestion tools and sample/synthetic data only.
- **Safety note:** add `docs/SAFETY_NOTE.md`: AsrBrain is an advisory tool. If its output is used as evidence in an ISO 26262 / ASPICE process, the adopting organisation must classify and qualify the tool per its own safety process, and a human must review.
- Prompt-injection defence: treat all ingested text as data, never as instructions.

---

## 12. Phased plan and kickoff prompts

Each phase ends with: tests green · eval numbers · Team Review · **STOP for my approval**.

### Phase 0 — Audit and baseline (no code changes)
**Deliver:** `docs/AUDIT.md` (as-is architecture, data flow, stack, dependencies, DB schema, how RAG currently works, UI structure, what the Mermaid/PDF branch does and its state, test coverage, security issues, tech debt), `docs/ARCHITECTURE_AS_IS.md` (Mermaid diagram), gap analysis against Sections 3–9, risk list, and a phased effort estimate.
**Kickoff prompt:**
> Execute Phase 0 of docs/MASTER_PROMPT.md. Read the whole repository (README, package/pyproject files, DB schema/migrations, ingestion code, retrieval/chat code, prompts, UI, tests, CI, the diff of the current branch against main). Do not modify code. Produce the deliverables, with each claim tied to file paths. List everything you could not determine and the questions you need me to answer.

### Phase 1 — Evaluation harness and baseline
**Deliver:** golden set v0 (≥ 300, expert-review flags), runner, metrics, CI gate, **baseline scores of the current system**, Evaluation page stub.
**Kickoff prompt:**
> Execute Phase 1. Build the evaluation harness exactly as in Section 9 and record baseline numbers for the current system without changing its behaviour. Show per-category scores and the 20 worst failures with diagnosis. Give me the expert-review sample as a CSV.

### Phase 2 — Ingestion, data model, provenance
**Deliver:** structure-aware parsers (PDF, ARXML, code, requirements, tests), snapshot/versioning, provenance fields, parse-quality reports, migration scripts + backup/rollback.
**Kickoff prompt:**
> Execute Phase 2. First propose the data model and migration plan and wait for my approval; then implement. Re-run the eval and show the delta. Keep Mermaid/PDF rendering working.

### Phase 3 — Retrieval upgrade
**Deliver:** query understanding/routing, hybrid search, rerank, parent expansion, exact-ID path, corrective loop, feature-flagged; ablation table.
**Kickoff prompt:**
> Execute Phase 3. Implement each retrieval component behind a feature flag and report an ablation table on the golden set. Keep only components that improve the metrics and explain the rest.

### Phase 4 — Knowledge graph
**Deliver:** ontology v1 (Section 5), graph builder from parsed sources, templated graph queries, graph-expansion retrieval, ARXML/code graph, graph API.
**Kickoff prompt:**
> Execute Phase 4. Implement ontology v1 and graph construction with provenance on every node/edge. Provide 20 example traceability questions answered through the graph and their eval scores.

### Phase 5 — Answer engine and verification
**Deliver:** structured answer schema, claim-level verification, exact-token guard, abstention policy, validated Mermaid generation, reproducibility record.
**Kickoff prompt:**
> Execute Phase 5. Implement the Accuracy Contract in Section 3. Show headline metrics against the targets and the remaining failure categories.

### Phase 6 — Agent tools: requirement mapping, test analysis, code flow
**Deliver:** tools in Section 6.4–6.7, proposal/review queue, impact analysis, test-run analysis, call-graph generation, tool trace.
**Kickoff prompt:**
> Execute Phase 6. Implement the tools with bounded budgets and the human-approval queue. Demonstrate each on sample (synthetic) data and add golden cases for them.

### Phase 7 — UI redesign
**Deliver:** design system, the eight screens in Section 7, evidence drawer, graph explorer, traceability and test dashboards, e2e tests, accessibility audit.
**Kickoff prompt:**
> Execute Phase 7. Start with a short design brief and wireframes (Mermaid or ASCII) for approval. Then implement screen by screen, with screenshots and Playwright tests per screen.

### Phase 8 — Hardening and open-source release
**Deliver:** RBAC, audit log, local-model mode, docker compose, docs site, CONTRIBUTING, licence review, SAFETY_NOTE, demo dataset (synthetic/public only), release notes.
**Kickoff prompt:**
> Execute Phase 8. Run a full security and licence review, make the project reproducible with one command, and prepare the release checklist.

---

## 13. Definition of Done (project level)

- Golden-set targets in Section 3 met on the hold-out split, or an honest gap report exists.
- Every answer shows citations; every graph edge shows provenance; every AI-proposed link is human-approved before it counts as truth.
- A new contributor can run the full stack and the eval suite from the README in under 30 minutes.
- Mermaid/PDF export works for answers, graphs and code-flow diagrams.
- All ADRs, SAFETY_NOTE, licence notes and CHANGELOG are present.
