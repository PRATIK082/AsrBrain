# AsrBrain — Deep Improvement Study and Feature Requirements

**Date:** 2026-11-04
**Branch:** `feature/document-intelligence-platform`
**Source inputs:** repository audit (`docs/AUDIT.md`, `docs/GAP_ANALYSIS.md`, `docs/RISK_REGISTER.md`), Phase 0 audit, Slice 1–5 implementation, skills.sh discovery, current UX/API/retrieval code.
**Status:** Draft for review (no code changes in this document)

---

## 1. Executive summary

AsrBrain already has a strong deterministic foundation: canonical SQLite store, hybrid retrieval, AUTOSAR-aware query understanding, ARXML topology, graph evidence, evaluation harness, and a new auth/workspace/collection/provider/config/reasoning layer. The main gaps are **productization gaps**, not core RAG gaps:

1. **Deployment flexibility is implicit, not configurable.** The system assumes one local SQLite DB, one fixed index path, and client-spoofed security context. It needs explicit deployment profiles for **workstation**, **on-prem server**, and **cloud/SaaS**.
2. **Self-context is not defined.** There is no machine-readable description of what the running instance can do, what data it has, which models are available, and which features are enabled. The UI and agents cannot adapt automatically.
3. **UX is developer-centric.** FastAPI/Streamlit endpoints are rich, but onboarding, navigation, empty states, progress, accessibility, and error recovery are not product-grade.
4. **Feature discovery is manual.** There is no in-product catalog of capabilities, no feature flags, no “what can I do here?” guidance, and no automatic recommendations.
5. **AUTOSAR depth is uneven.** Retrieval is good for spec questions; configuration, ARXML, test-result, and cross-artifact reasoning are only partially implemented.

This document converts those gaps into **numbered, testable requirements** and a prioritized roadmap.

---

## 2. Study method

1. **Repository audit** of `src/`, `apps/`, `frontend/`, `tests/`, `docs/`.
2. **Gap analysis** against the master prompt architecture and Accuracy Contract.
3. **Skills discovery** via `npx skills find` for:
   - RAG / knowledge graphs
   - local-first architecture
   - accessibility
   - UX design
   - deployment
4. **Cross-cutting review** of deployment, security, observability, and UX.
5. **Feature ideation** from user personas and AUTOSAR workflows.

---

## 3. Personas and top jobs-to-be-done

| Persona | Primary jobs | Current pain |
|---|---|---|
| AUTOSAR engineer | Ask spec questions with citations; understand module interactions | Good baseline; needs better config/code traceability |
| System integrator | Trace requirements → ARXML → code → tests | Partial; tools exist but not unified |
| Safety/ASPICE engineer | Traceability, evidence, audit trail | Auth/audit now started; needs reporting and export |
| Test engineer | Analyze failures, link to requirements/defects | Test-result ingestion not implemented |
| Knowledge manager | Ingest documents, manage collections, versions | Collections/auth started; needs admin UX |
| Platform admin | Deploy, monitor, back up, upgrade | No deployment profiles or health dashboard |
| New user | Understand capabilities and get started | No onboarding or feature catalog |

---

## 4. Deployment modes and self-context definition

### 4.1 Deployment profiles

AsrBrain must support three first-class profiles.

| Profile | Name | Target | Storage | Models | Auth | Notes |
|---|---|---|---|---|---|---|
| `workstation` | Local single-user | Laptop/dev machine | SQLite + local files | Ollama optional | Optional bootstrap admin | Fastest onboarding; no network exposure |
| `onprem-server` | Team server | Company LAN/on-prem VM | PostgreSQL recommended, SQLite allowed | Ollama or internal gateway | Required RBAC | Multi-user, backups, audit |
| `cloud-saas` | Hosted SaaS | Public/private cloud | PostgreSQL + object storage | Cloud LLM or managed local | Required SSO/RBAC | Tenant isolation, billing/quotas |

### 4.2 Self-context manifest

Every running instance must expose a machine-readable **self-context manifest** at `/api/context` (and embed it in the UI). This is the key to “adjust to any technology.”

**Manifest contents:**

- `profile`: `workstation | onprem-server | cloud-saas`
- `version`: app version + git commit
- `capabilities`: list of enabled features
- `data_sources`: counts by type (PDF, ARXML, code, config, tests)
- `collections`: accessible collections
- `models`: available LLM/embedding providers and health
- `storage`: backend type, size, backup status
- `limits`: max upload size, token caps, rate limits
- `security`: auth mode, RBAC enabled, tenant isolation mode
- `health`: dependency checks (DB, vector store, LLM, parser)
- `recommended_actions`: next steps for the user/admin

**Requirement:** The UI and agents must use this manifest to hide unavailable features, show setup guidance, and route tasks correctly. No feature should be assumed available.

### 4.3 Configuration model

Replace scattered env vars with a layered config:

1. **Defaults** (code)
2. **Profile defaults** (`config/profiles/*.yaml` or TOML)
3. **Instance config** (`config/instance.yaml`)
4. **Environment overrides** (`ASRBRAIN_*`)
5. **Runtime admin overrides** (DB-backed, audited)

Each setting must declare:
- key
- type
- default
- profile availability
- sensitivity (`public`, `internal`, `secret`)
- restart required (yes/no)
- validation rule

---

## 5. Automatic feature discovery and user guidance

### 5.1 Feature catalog

The product must maintain a **feature catalog** (code + DB) with:

- `feature_id`
- `name`
- `description`
- `category`
- `required_capabilities`
- `required_data`
- `status` (`available`, `disabled`, `needs_setup`, `experimental`)
- `help_url`
- `example_prompts`

The UI must render:
- “What can I do here?” panel
- feature cards with setup status
- contextual suggestions based on uploaded data

### 5.2 Smart onboarding

On first run:
1. Detect profile.
2. Create bootstrap admin if needed.
3. Show a 3-step wizard:
   - Add data (PDF/ARXML/code/config)
   - Choose model (Ollama/cloud)
   - Ask first question
4. Provide sample questions and demo dataset (optional, non-proprietary).

### 5.3 Contextual help

- Inline “why this answer?” explanations
- “What sources are needed?” prompts on abstain
- Tooltips for AUTOSAR terms
- Guided wizards for ingestion, collection sharing, model setup

---

## 6. User-friendly UX requirements

### 6.1 Information architecture

- Top-level navigation: **Chat**, **Knowledge**, **Documents**, **Collections**, **Models**, **Config**, **Admin**, **Help**
- Persistent context bar: current workspace, collection, model, profile
- Global search across documents, chunks, requirements, ARXML elements

### 6.2 Chat UX

- Streaming with first-token < 2s
- Citation chips that open evidence drawer
- “Show reasoning” panel (retrieval steps, conflicts)
- “Ask follow-up” suggestions
- Save/share conversations
- Export answer as Markdown/PDF
- Feedback buttons (helpful/incorrect) feeding eval

### 6.3 Evidence UX

- Evidence drawer with document, release, module, section, pages, requirement IDs
- Highlight cited span
- “Open source preview” (PDF page / code line / ARXML node)
- Confidence and abstention explanation

### 6.4 Document/knowledge UX

- Upload progress and parsing status
- Document preview (PDF/image/text)
- Chunk browser with filters
- Re-ingest / re-index actions
- Version comparison

### 6.5 Accessibility (WCAG 2.2 AA target)

- Keyboard navigation for all actions
- Screen-reader labels
- Color contrast compliance
- Reduced motion option
- Focus management in modals/drawers
- No color-only status indicators

### 6.6 Performance UX

- Skeleton loading states
- Virtualized long lists
- Optimistic updates for chat
- Background job status for ingestion

---

## 7. Functional requirements

### 7.1 Knowledge ingestion

| ID | Requirement | Priority |
|---|---|---|
| ING-01 | Support PDF, ARXML, source code, config, test results, and markdown docs | P0 |
| ING-02 | Track ingest run provenance (`ingest_runs`, snapshot IDs, content hashes) | P0 |
| ING-03 | Detect release/platform/module and store as filterable metadata | P0 |
| ING-04 | Chunk hierarchically (atomic + context) with requirement/API/ECUC signals | P0 |
| ING-05 | Extract tables/figures and link to chunks | P1 |
| ING-06 | Support incremental re-ingestion and deduplication | P1 |
| ING-07 | Show ingestion progress and errors in UI | P1 |
| ING-08 | Support collection-scoped ingestion | P0 |
| ING-09 | Support git source registration and sync | P1 |
| ING-10 | Validate ARXML against schema and report errors | P1 |

### 7.2 Retrieval and answer generation

| ID | Requirement | Priority |
|---|---|---|
| RET-01 | Hybrid retrieval (dense + BM25 + exact-ID fast path) | P0 |
| RET-02 | Metadata filtering by release/platform/module/collection | P0 |
| RET-03 | Query understanding for AUTOSAR modules, IDs, intent | P0 |
| RET-04 | Multi-hop retrieval for complex questions (opt-in) | P1 |
| RET-05 | Conflict detection across sources | P1 |
| RET-06 | Abstain when evidence insufficient | P0 |
| RET-07 | Version-aware answers and per-release breakdown | P0 |
| RET-08 | Citation precision ≥ 98% on golden set | P0 |
| RET-09 | Corrective retry when evidence thin | P1 |
| RET-10 | Graph expansion for related requirements/modules | P1 |

### 7.3 AUTOSAR intelligence

| ID | Requirement | Priority |
|---|---|---|
| ASR-01 | Module alias expansion (Eth, EthIf, EthSwt, etc.) | P0 (done) |
| ASR-02 | Configuration query support (ECUC containers/params) | P0 (started) |
| ASR-03 | ARXML topology visualization | P1 |
| ASR-04 | Requirement → design → code → test traceability | P1 |
| ASR-05 | Test result analysis and failure clustering | P2 |
| ASR-06 | Defect linkage and impact analysis | P2 |
| ASR-07 | Release supersession and delta analysis | P2 |
| ASR-08 | Safety/ASIL-aware filtering and warnings | P2 |

### 7.4 Security and multi-user

| ID | Requirement | Priority |
|---|---|---|
| SEC-01 | Real authentication (password/OAuth/SSO) | P0 (started) |
| SEC-02 | RBAC with roles: viewer, contributor, maintainer, admin | P0 |
| SEC-03 | Tenant/workspace/collection isolation | P0 |
| SEC-04 | Audit log for security-relevant actions | P0 |
| SEC-05 | Secret management and redaction before cloud LLM | P0 |
| SEC-06 | Rate limiting and abuse protection | P1 |
| SEC-07 | Data export/delete with approval | P1 |

### 7.5 Models and providers

| ID | Requirement | Priority |
|---|---|---|
| MOD-01 | Provider registry (Ollama, OpenAI-compatible, local) | P0 (done) |
| MOD-02 | Model health checks and discovery | P0 |
| MOD-03 | Per-task model routing | P1 |
| MOD-04 | Cost/latency tracking | P1 |
| MOD-05 | Fallback when provider unavailable | P1 |
| MOD-06 | Embedding model benchmarking on golden set | P1 |

### 7.6 Configuration versioning

| ID | Requirement | Priority |
|---|---|---|
| CFG-01 | Store pipeline config versions | P0 (done) |
| CFG-02 | Activate/rollback with audit | P0 |
| CFG-03 | Diff between config versions | P1 |
| CFG-04 | Environment-specific config profiles | P1 |
| CFG-05 | Validation before activation | P1 |

---

## 8. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | p95 single-turn latency (cloud LLM) | ≤ 8s |
| NFR-02 | First token (stream) | < 2s |
| NFR-03 | Local workstation cold start | < 10s |
| NFR-04 | On-prem server supports 50 concurrent users | P1 |
| NFR-05 | Backup/restore documented and tested | P0 |
| NFR-06 | No secrets in git | P0 |
| NFR-07 | Audit trail for data changes | P0 |
| NFR-08 | Observability (tracing, metrics, logs) | P1 |
| NFR-09 | Accessibility WCAG 2.2 AA | P1 |
| NFR-10 | Data portability (export/import) | P1 |

---

## 9. Detailed UX requirements

### 9.1 Onboarding

- First-run wizard with 3 steps.
- Sample dataset optional.
- “Test your setup” button runs health checks.

### 9.2 Chat

- Evidence chips clickable.
- Abstain reasons explicit.
- Follow-up suggestions.
- Conversation history and search.

### 9.3 Admin

- User management
- Collection management
- Model management
- Config management
- Backup/restore
- Health dashboard

### 9.4 Empty states

Every list view must have:
- explanation
- primary action
- link to docs

---

## 10. Observability requirements

- OpenTelemetry traces for retrieval and generation
- Structured logs with request IDs
- Metrics: latency, token usage, retrieval hit rate, abstention rate
- Eval dashboard with trend lines
- Error reporting without leaking secrets

---

## 11. Recommended skills to install

Based on skills.sh discovery, the following are high-value and reputable:

| Skill | Source | Installs | Use |
|---|---|---|---|
| accessibility | `addyosmani/web-quality-skills` | 66.9K | Frontend accessibility audit |
| knowledge-graph | `giuseppe-trisciuoglio/developer-kit` | 1.9K | Graph modeling patterns |
| local-first | `oakoss/agent-skills` | 164 | Local-first architecture patterns |
| ux designer | `bmad-code-org/bmad-method` | 13.7K | UX design workflow |
| penpot-uiux-design | `github/awesome-copilot` | 12.9K | UI/UX design guidance |

Install command example:

```bash
npx skills add addyosmani/web-quality-skills@accessibility -g -y
```

These are **optional** and should be reviewed before installation.

---

## 12. Prioritized roadmap

### Phase A (now): Product foundation
- Self-context manifest
- Feature catalog
- Deployment profiles
- Onboarding wizard

### Phase B: UX and accessibility
- Evidence drawer
- Admin console
- Accessibility audit
- Performance polish

### Phase C: AUTOSAR depth
- Configuration query improvements
- ARXML visualization
- Traceability graph
- Test result analysis

### Phase D: Enterprise readiness
- Observability
- Backup/restore
- SSO
- Rate limiting
- Multi-tenant hardening

---

## 13. Acceptance criteria for “improved project”

1. A new user can install, configure, and ask a question in < 10 minutes.
2. `/api/context` accurately reports capabilities and health.
3. All features are gated by capability manifest.
4. Golden-set metrics do not regress.
5. Accessibility audit passes WCAG 2.2 AA for core flows.
6. Deployment profile can be switched without code changes.
7. Admin can back up and restore data.

---

## 14. Open questions

1. Should on-prem default to PostgreSQL or keep SQLite for simplicity?
2. Should SaaS be multi-tenant single DB or DB-per-tenant?
3. Which SSO providers are required first?
4. Should test-result ingestion be prioritized over config depth?
5. Is a desktop (Tauri/Electron) wrapper desired?

---

## 15. Next action

Review this document and select the first slice to implement. Recommended: **Self-context manifest + feature catalog** (Phase A), because it unlocks adaptive UX and deployment flexibility with low risk.