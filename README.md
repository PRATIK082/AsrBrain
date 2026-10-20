![AsrBrain — Your Local AI Co-Pilot for AUTOSAR Engineering](docs/images/project-overview.png)

# AUTOSAR Knowledge Copilot

Local-first, citation-grounded RAG for AUTOSAR Classic / Adaptive / Foundation specifications.
Chatbox-style chat UI (no filter forms to fill): the assistant asks back for a missing
release/platform, auto-detects the module with Confirm/Change, and routes document type
automatically. Every factual claim carries a source citation (PDF + pages + requirement IDs).

> **Merged:** `feature/multimodal-rag-chatbox-upgrade` → `main` via true merge
> commit `631778b` (parents: `main` + `875a9d5`; earlier squash `0726bb5`/PR #1
> carried the same content).
> Adds the multimodal RAG stack: canonical multimodal model (`src/schema/canonical.py`,
> `src/schema/multimodal_graph.py`), parser adapters (`src/ingestion/parser_adapter.py`),
> text/table/figure processors (`src/ingestion/processors.py`), query planner
> (`src/retrieval/planner.py`), modality fusion (`src/retrieval/modality_fusion.py`),
> context rules (`src/retrieval/context_rules.py`), generation routing
> (`src/generation/routing.py`), collections (`src/indexing/collections.py`),
> plus audits/migration docs in `docs/` and `tests/unit/test_canonical_multimodal.py`.

## UI view — chatbox at a glance

Streamlit (`apps/streamlit/app.py`, wide layout, dark/light themes) and the React
skeleton (`frontend/app/page.tsx`, same `/api/` SSE contract) share one look:

```
┌─────────────┬───────────────────────────────────────────────────┐
│  Sidebar    │  🚗 AUTOSAR Knowledge Copilot        [Chat|Evidence│
│  ────────   │───────────────────────────────────────────────────│
│ Conversations│  👤 Explain CanIf initialization                  │
│ New/Search/  │  🤖 CanIf init sequence … [E1][E2]                 │
│ Rename/Delete│  📚 Sources (2) ▸ SWS_CanIf.pdf p.12 · 4.4.0 …     │
│ ⑂ Fork      │  Detected: CanIf [✓ Confirm] [Change ▾]             │
│ 💾 Save/Load │  Mode: troubleshooting (auto) · Interpreted as …   │
│ 🤖 Model    │  [Evidence cards] [Trace timeline] [Graph] [👍][👎]  │
│ Ollama/Cloud│─────────────────────────────────────────────────── │
│ Eco/Bal/Deep│  Ask about AUTOSAR… [Send] [⏹ Stop]                 │
│ 📄 Upload   │  follow-ups: payoff chips (3–4, clickable)          │
└─────────────┴───────────────────────────────────────────────────┘
```

| Area | What you see | Source |
|---|---|---|
| Sidebar | Conversation list, search/rename/delete, ⑂ Fork with another model, 💾 Session save/resume (`.json` bundle), provider picker (Local Ollama / Cloud API key, session-only), Evidence depth Eco(4)/Balanced(8)/Deep(12), Response length Concise/Standard/Detailed, 📄 PDF upload + ingest, ⬇ Export `.md` | `apps/streamlit/app.py:145-239` |
| Chat tab | Streaming answer (`token` events + ▌ cursor), staged status (`QueryPlan → retrieval → RRF → rerank → generation`), clarification chips (releases/platforms), module Confirm/Change, `📚 Sources (n)` expander (one line per `[En]`: file · pages · release · section), 👍/👎 feedback, ✏️ Edit & resend, ⏹ Stop | `apps/streamlit/app.py:286-399`, `frontend/app/page.tsx:8-73` |
| Evidence tab | Cited passages `[En]` with PDF + pages + requirement/API IDs | `src/retrieval/modalities.py`, `src/schema/multimodal.py` |
| Trace tab | QueryPlan, routing (doctype auto), per-release retrieval, fusion/rerank, token caps, verification/confidence | `src/workflows/stages.py`, `src/generation/routing.py` |
| Graph tab | Requirement/API/ECUC/table/figure links (multimodal graph) | `src/schema/multimodal_graph.py`, `src/retrieval/graph.py` |

**Screenshots:** none checked in yet (no `*.png` in repo). To add:
1. `streamlit run apps/streamlit/app.py` → ask “Explain CanIf initialization” → screenshot chat + Evidence/Trace tabs.
2. Save to `docs/images/chatbox-chat.png`, `docs/images/chatbox-evidence.png`, `docs/images/chatbox-trace.png`.
3. Reference them here:
   `![Chat](docs/images/chatbox-chat.png)` etc.

Run the UI:

```bash
streamlit run apps/streamlit/app.py   # self-contained, works without API server
# optional React: cd frontend && npm install && npm run dev   # needs API on :8000
```

## Quickstart

```bash
pip install -r requirements.txt
cp .env.example .env            # set LLM_MODEL to an Ollama model you have pulled
python -m src.ingestion.pipeline --pdf-dir pdf --out data/canonical
python -m src.indexing.build --canonical data/canonical/canonical.db
uvicorn apps.api.main:app --port 8000     # terminal 1 (chat API + legacy /query)
streamlit run apps/streamlit/app.py       # terminal 2 — chat UI (works without the API server too)
```

No Ollama running? Answers fall back to extractive, fully-cited passages. Cloud models
(OpenAI GPT, Gemini, Opencode/Cloud…) work via the provider picker + session-only API key.

## Asking questions (no corpus filters)

There is deliberately no release/platform/module sidebar. Flow:

1. Ask naturally, e.g. “Explain CanIf initialization”.
2. If release/platform are missing **and the corpus spans versions**, the assistant asks back
   with one-tap chips (“4.4.0”, “R22-11”, “any release”…).
3. Detected modules are proposed (`Detected: CanIf [✓ Confirm] [Change ▾]`) — the filter
   applies only after you confirm or when you named it yourself.
4. Document type (SWS/PRS/RS/…) is always routed automatically and shown in the trace.

Search mode is automatic too (ChatGPT/Gemini-style): the detected intent is shown as
`Mode: troubleshooting (auto)` with per-mode answer formats (comparison tables, diagnostic
sequences, configuration procedures). The view auto-follows new messages; long source lists
collapse into one `📚 Sources (n)` expander; every answer ends with 3–4 clickable follow-up
questions (grounded in the retrieved APIs/requirements/modules) or just type your own.
Spelling is auto-corrected before retrieval (`can if` → `CanIf`, `configurare` → `configure`;
identifiers, versions, and citations are never rewritten) with an “Interpreted as” note.

## Sessions: no re-loading, models per chat

- **Everything persists**: messages, release/platform/module slots, evidence cards, traces,
  follow-ups, and the model each chat uses — close the app, reopen, and continue. The
  Evidence/Trace/Graph tabs rehydrate from the saved context.
- **Follow-ups reuse context**: the previous exchange travels with the next question, so
  “its message format?” resolves against the prior SOME/IP answer without re-deriving state.
- **Different AI per workstream**: each conversation remembers its provider/model. **⑂ Fork
  with another model** clones the slots into a fresh history — pick another Ollama model or a
  cloud key and start the same topic elsewhere.
- **Portable save files**: sidebar → 💾 Session save/resume exports a `.json` bundle
  (messages + slots + model); import it here or on another machine. Same via
  `GET /api/conversations/{id}/export` + `POST /api/conversations/import`. The index itself
  stays on disk (`data/indexes/`) — sessions never trigger re-ingest.

## Architecture

```
pdf/*.pdf → ingestion (parser adapters: Docling-opt → PyMuPDF → pypdf; tables/figures
            captured with captions + structured rows; header/footer strip; req/API/ECUC
            signals; release/platform/doctype detect; per-PDF quality report)
            → canonical.db (documents + chunks + tables + figures, stable text chunk IDs)
            → hybrid index + modality indexes (requirement/API/ECUC/table/figure, exact-first)
            → chat workflow (QueryPlan → clarify-if-missing → per-release retrieval →
              RRF → rerank → parent-expand → compress → staged status/evidence/token events)
            → generation (Ollama local | OpenAI-compatible cloud w/ session API key;
              extractive fallback) → verifier → confidence/abstain
            → FastAPI chat contract (/api/chat, /stream SSE, conversations, documents,
              sources+page preview, feedback, models/releases/modules) + legacy /query
              + tooling contract (/api/tools, /api/mindmap, /api/graph/*, /api/agent/*)
            → Streamlit Chatbox UI (conversations, streaming, chips, evidence/trace/graph
              panels, upload, export) · React skeleton in frontend/ (same contract)

side-path: canonical.db + C code + ARXML → knowledge graph (src/graphrag) → tools
(src/tools) → bounded agent workflows (src/agents) → /api/agent/*, GraphRAG + Agent
tabs in frontend/
```

Phasing (spec §7): Phase 1 (this repo, default) = SQLite canonical + local hybrid + FastAPI +
Streamlit + Ollama. Phase 2 adds OpenSearch; Phase 3 adds Neo4j/graph + Qdrant mirror
(`src/indexing/qdrant_index.py`, `src/retrieval/graph.py` stubs ready, Docker profiles ready).

## Project layout

| Path | Content |
|---|---|
| `apps/api/main.py` | FastAPI: legacy `/query /ingest /evaluate` + chat contract `/api/conversations /api/chat /api/chat/stream /api/chat/stop /api/documents /api/sources /api/feedback /api/models /api/releases /api/modules` + tooling contract `/api/tools /api/mindmap /api/graph/* /api/agent/*` |
| `apps/streamlit/app.py` | Chatbox UI: conversation sidebar (new/search/rename/delete), chat history, streaming, regenerate/edit/stop, clarification chips, citation cards, evidence/trace/graph tabs, upload, export |
| `frontend/` | React/Next.js skeleton (same `/api/` contract, SSE streaming, zustand settings) — `full` Compose profile |
| `src/ingestion/` | `pipeline.py` (+tables/figures stores), `parsers.py` (Docling/PyMuPDF/pypdf adapters + quality routing), `pdf_extract.py`, `chunking.py`, `metadata.py`, `parser_adapter.py` + `processors.py` (merged multimodal adapters) |
| `src/schema/` | `documents.py`, `queries.py`, `graph.py` (+confidence/is_inferred), `multimodal.py` (MultimodalEvidence), `canonical.py` + `multimodal_graph.py` (merged multimodal model) |
| `src/retrieval/` | `query_understanding.py`, `clarify.py` (slot-fill), `modalities.py` (req/API/ECUC/table/figure), `fusion.py`, `reranking.py`, `context.py`, `pipeline.py`, `graph.py`, `planner.py` + `modality_fusion.py` + `context_rules.py` (merged) |
| `src/generation/` | `providers.py` (Ollama + OpenAI-compat cloud, streaming), `prompts.py` (per-mode formats), `answer.py`, `citations.py`, `verification.py`, `routing.py` (merged multimodal routing) |
| `src/workflows/` | `router.py` (legacy path), `stages.py` (SSE staged events + cancel) |
| `src/chat/store.py` | Conversations/messages/slots/feedback SQLite |
| `src/graphrag/` | Knowledge graph for GraphRAG: `store.py` (SQLite `kg_nodes`/`kg_edges`/`kg_communities`/`trace_links`), `extractor.py` (deterministic entities/relations from chunks, C code, tests), `builder.py` (`python -m src.graphrag`), `community.py` (label-propagation communities), `retrieval.py` (local / global / hybrid search), `runtime.py` (shared store singleton) |
| `src/tools/` | Tool framework: `base.py` (`ToolSpec`/`ToolResult`/`ToolRegistry`), `registry.py` (the 22 shipped tools), `graphrag.py`, `mindmap.py`, `arxml.py`, `code.py`, `traceability.py`, `cli.py` (`python -m src.tools.cli`) |
| `src/agents/` | Agentic layer: `planner.py` (deterministic + LLM planning, intent detection), `executor.py` (bounded tool loop with citations), `workflows.py` (4 named workflows), `runner.py` (workflow runner + SSE events) |

## GraphRAG, tools & agentic workflows

Beyond plain RAG, the repo can build a **knowledge graph** over the same canonical
store and answer with it. The graph mixes four worlds that the text index keeps
apart: AUTOSAR **requirements** ↔ **APIs/ECUC values** (from the specs), **ARXML**
components/ports/interfaces/runnables, **C code** functions and RTE call sites, and
**test cases** — with explicit, inspectable traceability links between them.

```
canonical.db + C sources + ARXML
        │  deterministic extraction (src/graphrag/extractor.py)
        ▼
   knowledge graph  (kg_nodes / kg_edges / kg_communities / trace_links)
        │  local search (neighbourhood) + global search (community summaries)
        ▼
    tools  (graph.*, mindmap.*, arxml.*, code.*, trace.*)
        │  bounded agent loop (src/agents) — deterministic plan, cited answer
        ▼
  4 workflows: arxml_requirement_trace · code_requirement_trace · impact_analysis · deep_explanation
```

**Build and explore**

```bash
make graph-build CODE_DIRS="src"        # canonical.db + C code → data/graph/graph.db
make graph-stats                        # node / edge / community / trace-link counts
make graph-query QUERY="CanIf init" MODE=hybrid
make tools                              # list every tool with its JSON schema
make mindmap TOPIC=CanIf SOURCE=graph   # Mermaid mindmap on stdout
make agent QUERY="which tests cover SWS_CanIf_00123" WORKFLOW=auto
```

**REST surface** (same contract as the chat API, all under `/api`)

| Endpoint | Purpose |
|---|---|
| `GET /api/tools` | Tool catalogue: name, description, JSON-Schema, tags, mutating flag |
| `POST /api/tools/{name}` | Invoke one tool (`{"args": {...}, "allow_mutating": false}`) |
| `POST /api/mindmap` | Mermaid mindmap from the graph, from evidence or from an outline |
| `POST /api/graph/build` | Rebuild the graph (mutating: needs `allow_mutating`) |
| `GET /api/graph/stats` | Graph counters + store path |
| `POST /api/graph/query` | `mode` = `local` \| `global` \| `hybrid` search |
| `GET /api/graph/node/{node_id}` | One node plus its neighbourhood subgraph |
| `GET /api/agent/workflows` | The named workflows and their fixed tool plans |
| `POST /api/agent/run` | Run a workflow → answer, citations, observations, plan |
| `POST /api/agent/stream` | Same, as SSE (`workflow`, `plan`, `tool_call`, `tool_result`, `complete`) |

The React UI has two new tabs — **GraphRAG Explorer** (graph stats, search, entity
browser, communities, mindmap) and **Agent Workflows** (workflow runner + tool
catalogue) — in `frontend/components/graph/` and `frontend/components/agent/`.

**Safety rules that the agent layer enforces** (see `docs/featureupdate.md` §20):

- the *plan* is deterministic by default; a model may only re-order or trim it,
- a tool can never invent document metadata — it only reports what the graph holds,
- only `graph.build` may mutate, and only when `allow_mutating` is explicitly granted,
- every answer is built from tool observations with `[G<n>]` citations; when the model
  is unavailable a deterministic digest is produced instead,
- a workflow that finds nothing says so instead of filling the gap with general knowledge.

Design rationale, the node/edge vocabulary and the acceptance criteria are in
`docs/agentic-graphrag-tooling-plan.md`.

## Benchmark (measured, 2026-09-29)

`reports/evaluation/validated.json` on the 1-PDF corpus (SOME/IP PRS R24-11, 169 chunks):

```json
{"n": 8, "hit_rate": 1.0, "abstention_rate": 0.5, "mean_claim_support": 0.3611, "p50_latency_s": 36.3}
```

Read it as: in-corpus SOME/IP lookups answered with citations; the 4 CanIf/Classic
comparison items correctly **abstained** (corpus gap — flagged `needs_human_validation`).
No "95% accuracy" is claimed; see `reports/evaluation/comparison.md` and
`docs/failure-analysis.md` for the honest breakdown. Latency is LLM-bound (~35 s/query on a
14 B local model); retrieval itself is <0.5 s.

## Docker

```bash
make docker-minimal    # api + streamlit + qdrant + ollama
make docker-standard   # + postgres + opensearch
make docker-full       # + neo4j + redis + react frontend
```

`RAG_PIPELINE_VERSION=v1|v2` (default v2) selects legacy vs. multimodal chat pipeline.
**Rollback:** set `RAG_PIPELINE_VERSION=v1`, restart api/streamlit — text-only retrieval,
`/query` unchanged; v2 stores (`tables`, `figures`) are ignored, chunk IDs stable so no
re-index is needed either way. Source PDFs are never baked into images.

## Contributing / feedback

UI has 👍 / 🚨 buttons. To add a gold case: append a JSON line to
`data/benchmarks/autosar_benchmark_v1.jsonl` (schema in `src/evaluation/datasets.py`),
then `make eval`. See `docs/operations-guide.md`, `docs/troubleshooting.md`,
`docs/migration-risk-register.md`.
