# Plan: Agentic Tooling, GraphRAG, Mindmaps and Traceability Workflows

Branch: `feature/agentic-graphrag-mindmap-tooling`

## 1. Goal

Turn AsrBrain from a "PDF RAG chatbot" into a **global automotive engineering assistant** that can:

1. Answer across the whole corpus (AUTOSAR specs + ARXML + C code + test cases + requirements)
   using **GraphRAG** (knowledge-graph retrieval, not only vector similarity).
2. Produce **mindmaps** (Mermaid `mindmap`) of any topic, module, requirement or code area.
3. Run **agentic workflows** that plan, call tools and verify — bounded, auditable, never
   allowed to invent metadata or drop citations.
4. **Link ARXML, C code, requirements and test cases** into one traceability graph so an
   engineer can ask "what implements `SWS_CanIf_00123`?" and get ARXML ports, C functions
   and the test case that covers it.

Everything is additive and local-first: no new mandatory server dependency, no cloud call
unless the user explicitly selects an OpenAI-compatible provider.

## 2. Design constraints (inherited from the project)

* Deterministic parsing first, RAG only *explains* (`src/ingestion/arxml/parser.py`).
* Inferred relations are always flagged (`is_inferred`) and never normative alone.
* No autonomous agent may: invent document metadata, ignore version filters, replace
  evidence with model knowledge, or emit uncited claims (`docs/featureupdate.md` §20).
* Every answer carries citations `[E#]` and a confidence/abstain verdict.
* Tenant/project scoping is server-enforced (`src/security/context.py`).

## 3. Module layout

```
src/
  graphrag/                 # NEW - Knowledge Graph for GraphRAG
    __init__.py
    store.py                # SQLite KG store (nodes/edges/communities) + trace_links
    extractor.py            # deterministic entity+relation extraction (spec, code, arxml)
    builder.py              # builds the KG from canonical chunks + sources
    community.py            # label-propagation communities + deterministic summaries
    retrieval.py            # local / global / hybrid GraphRAG retrieval
  tools/                    # NEW - tool framework the agent + API can call
    __init__.py
    base.py                 # ToolSpec, ToolResult, Tool protocol, ToolRegistry
    mindmap.py              # mindmap builder + Mermaid renderer
    graphrag.py             # graph search / neighborhood / path tools
    arxml.py                # ARXML topology / port / runnable / config tools
    code.py                 # C symbol, call-graph and RTE-map tools
    traceability.py         # requirement <-> code <-> testcase linking tools
    registry.py             # global REGISTRY wiring every tool
  agents/                   # NEW - agentic orchestration
    __init__.py
    planner.py              # LLM tool planner + deterministic fallback router
    executor.py             # bounded tool loop (max steps), trace, streaming events
    workflows.py            # named workflows (arxml/code/impact/explain)
    runner.py               # workflow registry + run_workflow()
```

New REST surface (`apps/api/main.py`):

```
GET  /api/tools                      list callable tools + JSON schemas
POST /api/tools/{tool_name}          invoke one tool directly
POST /api/mindmap                    build a mindmap (mermaid) from topic/graph
POST /api/graph/build                (re)build the KG from the canonical store
GET  /api/graph/stats                node/edge/community counts
POST /api/graph/query                local/global/hybrid graph search
GET  /api/graph/node/{node_id}       neighbourhood subgraph
GET  /api/agent/workflows            list workflows
POST /api/agent/run                  run a workflow (JSON result)
POST /api/agent/stream               run a workflow (SSE events)
```

Frontend (`frontend/`): new **Graph** tab (graph search + node neighbourhood + mindmap
renderer) and **Agent** tab (workflow picker + trace timeline + mindmap output).

## 4. GraphRAG design

### 4.1 Node/edge vocabulary

Nodes are typed and carry provenance:

| type | example | source |
|---|---|---|
| `module` | `CanIf` | module metadata |
| `requirement` | `SWS_CanIf_00042` | `requirement_ids` on chunks |
| `api` | `CanIf_Init` | `api_names` on chunks / C symbols |
| `ecuc_parameter` | `CanIfInitCfg` | `ecu_parameters` on chunks |
| `port` | `CanIf_TxPduInfo` | ARXML parser |
| `interface` | `CanIf_Interface` | ARXML parser |
| `swc` | `CanIfSwc` | ARXML parser |
| `runnable` | `CanIf_MainFunction` | ARXML parser |
| `connector` | `AssemblyConn` | ARXML parser |
| `function` | `CanIf_Init` (C) | C source scanner |
| `test_case` | `TEST_CANIF_001` | test source scanner |
| `document` | `doc-abc123` | canonical documents table |
| `community` | `c-17` | community detection |

Edges always carry `weight`, `confidence`, `is_inferred` and a provenance blob
(chunk id / file / line / release).

### 4.2 Extraction (deterministic)

* Spec chunks: requirement IDs (`SWS_*`, `SRS_*`, `R-*`), API names, ECUC parameter paths,
  module names, cross-references ("see `CanIf_Transmit`"), error codes.
* C sources: function definitions, `Rte_*` calls, `#include`, static/global symbols,
  AUTOSAR module prefix heuristic (`CanIf_` → `CanIf`).
* Test sources: test-case identifiers, `TEST_*`, `tcase*`, `@req`/`@covers` annotations.
* ARXML: reuse `src/ingestion/arxml/graph_export.py` (already deterministic).

### 4.3 Community detection

Label propagation over the undirected projection (deterministic, seeded by node id).
Each community gets a deterministic summary: top nodes by degree, top edges by weight,
plus the most frequent requirement/module labels. Optional LLM refinement is off by
default (`ASRBRAIN_GRAPH_LLM_SUMMARY=true`).

### 4.4 Retrieval

* **Local**: seed entities matched from the query → weighted BFS (depth ≤ 3) → ranked
  sub-graph with edge provenance.
* **Global**: community summaries ranked against the query (BM25 over summary text).
* **Hybrid**: local + global merged, then fused with the existing vector/BM25 evidence
  using RRF, so GraphRAG *adds* signal without replacing the proven pipeline.
* Answers built from graph evidence get `[G#]` citations resolving to
  `chunk_id` / `file:line` / ARXML xpath.

## 5. Tool framework

`ToolSpec` carries `name`, `description`, `parameters` (JSON Schema) and `fn`.
`ToolRegistry.invoke(name, args)` returns a `ToolResult` with `ok`, `data`, `error`,
`duration_ms`, `provenance`. Tools are pure-ish and side-effect free except
`graph.build`, which is explicitly flagged.

Tool list (as shipped — 22 tools in `src/tools/registry.py`):

| tool | purpose |
|---|---|
| `graph.search` | local/global/hybrid graph retrieval |
| `graph.neighbors` | neighbourhood of a node |
| `graph.path` | shortest path between two nodes |
| `graph.communities` | community list, optionally ranked against a query |
| `graph.community` | community summary and members |
| `graph.stats` | node / edge / community / trace-link counters |
| `graph.build` | **(mutating)** rebuild the KG from the canonical store + code folders |
| `mindmap.build` | Mermaid mindmap for a topic or node neighbourhood |
| `arxml.artifacts` | parsed ARXML artifacts of the tenant |
| `arxml.topology` | component/port/runnable list of an ARXML artifact |
| `arxml.neighbors` | ARXML graph neighbours |
| `arxml.search` | search components/ports/interfaces/runnables/ECUC values |
| `arxml.config` | ECUC parameter lookup |
| `code.symbols` | C functions/macros in a file or source set |
| `code.callgraph` | C call graph around a function |
| `code.rte_map` | RTE call → ARXML port mapping |
| `code.analyze` | advisory static checks on a C snippet |
| `trace.links` | raw traceability links filtered by type/id |
| `trace.requirements` | requirements linked to a code symbol / port / module |
| `trace.tests` | test cases linked to a requirement / API |
| `trace.matrix` | full requirement ↔ code ↔ test matrix for a module |
| `trace.gaps` | requirements without an implementation or without a test case |

CLI access: `python -m src.tools.cli list | call <tool> k=v | mindmap <topic> | agent <query>`.

## 6. Agentic workflows

The executor is a **bounded loop**: plan → select tool → call tool → observe → repeat,
maximum `max_steps` (default 6), every step recorded in a trace. It never mutates the
index except through the explicitly whitelisted `graph.build` tool, and it always
returns citations plus a confidence verdict.

Workflows:

1. `arxml_requirement_trace` — ARXML artifact → components/ports/runnables →
   linked requirements → linked test cases → mindmap.
2. `code_requirement_trace` — C source → functions/RTE calls → ARXML ports →
   requirements → test cases → mindmap.
3. `impact_analysis` — changed requirement/API/module → affected ARXML, code and tests.
4. `deep_explanation` — question → GraphRAG hybrid retrieval → sub-questions →
   cited answer + mindmap.

Planning uses the LLM when a provider is supplied (tool-calling via
`/api/chat/completions` `tools` or Ollama `tools`), otherwise a deterministic keyword
router picks the workflow — the agent never blocks on a missing LLM.

## 7. Traceability storage

New tables in the KG database (`data/canonical/graph.db`):

```
kg_nodes(id PK, type, label, properties JSON, degree, community)
kg_edges(src, dst, rel, weight, confidence, is_inferred, provenance JSON)
kg_communities(id PK, level, title, summary, member_count)
trace_links(link_id PK, source_type, source_id, target_type, target_id,
            link_type, confidence, evidence JSON, is_inferred)
```

`trace_links` is written by the builder (requirement ↔ API ↔ code ↔ test) and by the
traceability tools when the user confirms a link.

## 8. Implementation order

1. `src/graphrag/store.py` → `extractor.py` → `builder.py` → `community.py` → `retrieval.py`
2. `src/tools/*`
3. `src/agents/*`
4. `src/generation/providers.py` tool-calling support
5. API endpoints + frontend
6. Tests + docs + Makefile/CLI targets

## 9. Acceptance criteria

* `pytest -q` green (existing + new tests).
* `python -m src.graphrag --canonical data/canonical/canonical.db` builds a KG
  from any corpus without network access.
* `POST /api/tools/graph.search` returns graph evidence with provenance.
* `POST /api/mindmap` returns a valid Mermaid `mindmap` block.
* `POST /api/agent/run` with `workflow=code_requirement_trace` returns a trace,
  a traceability matrix and a mindmap.
* Frontend shows the Graph and Agent tabs and renders the mindmap.
* All new behaviour is behind feature flags with a safe default (`true` for local-only
  deterministic features, `false` for anything that calls a cloud model).

## 10. Risks

| Risk | Mitigation |
|---|---|
| KG explosion on large corpora | node/edge caps per build, batching, configurable depth |
| Hallucinated links | every inferred link carries `is_inferred` + confidence; tools report raw evidence |
| Agent loops | hard `max_steps`, per-step timeout, deterministic fallback planner |
| Slow builds | incremental build (only new chunks), cache of extraction |
| Regex noise from C code | symbol scanner restricted to function-definition syntax; findings are advisory |

## 11. Implementation status

Implemented on branch `feature/agentic-graphrag-mindmap-tooling`:

* `src/graphrag/` — store, extractor, builder (`python -m src.graphrag`), communities,
  retrieval, runtime singleton.
* `src/tools/` — framework, 22 tools, CLI (`python -m src.tools.cli`).
* `src/agents/` — planner, bounded executor, 4 workflows, runner.
* `src/generation/providers.py` — `chat_with_tools` (Ollama `/api/chat` + OpenAI-compatible
  `/chat/completions`), used by the LLM planner.
* `apps/api/main.py` — `/api/tools`, `/api/tools/{name}`, `/api/mindmap`, `/api/graph/*`,
  `/api/agent/*`; the ARXML artifact store moved to `src/ingestion/arxml/runtime.py` so
  the API and the tools share it.
* `frontend/` — GraphRAG Explorer and Agent Workflows tabs (+ mindmap renderer).
* `tests/` — 6 new unit modules and `tests/integration/test_graphrag_api.py`.

Deliberate defaults: the agent endpoints run **without a model** (`provider="none"`)
so the answer is a deterministic, cited digest; a model only re-phrases it. Only
`graph.build` mutates, and only with an explicit `allow_mutating` grant.
