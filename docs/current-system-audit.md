# Current System Audit (2026-10-04, branch `feature/multimodal-rag-chatbox-upgrade`)

Method: static reads of `src/`, `apps/`, `docker-compose.yml`, `requirements.txt` + prior `docs/current-state-audit.md`. No prod files modified for this doc.

## 1. UI framework / chat state / streaming / upload
- `apps/streamlit/app.py`: Streamlit Chatbox-like fallback UI, in-process engine, provider picker (Ollama/cloud), depth/length controls, upload + re-ingest, tabs chat/evidence/trace/graph, clarify chips, fork/model-per-chat, bundles.
- `apps/api/main.py`: FastAPI with `/query /ingest /evaluate` + `/api/` chat contract (conversations CRUD, `/api/chat`, `/stream` SSE, upload, documents, sources/page, feedback, models/releases/modules).
- `frontend/`: React app (full profile only). Streamlit remains fallback until parity.
- `src/workflows/stages.py`: `run_staged()` SSE events status/clarify/evidence/token/complete, clarification gate, history-aware retrieval, cancellation.
- `src/chat/store.py`: conversation persistence.

## 2. Backend pipeline
- Ingestion: `src/ingestion/pipeline.py` (hash → parse adapter → chunk → `canonical.db`), `pdf_extract.py`, `metadata.py` (release/platform/module/doctype), `chunking.py`.
- Parsers: `src/ingestion/parsers.py` sync `BaseParser` + `PyMuPDFParser` (find_tables, caption regex, quality flags), `PypdfParser`, `DoclingParser`, `MinerUParser` stub, `get_parser()`, `parser_quality_report()`.
- Schema: `src/schema/documents.py` (Chunk/DocumentRecord), `src/schema/multimodal.py` (MultimodalEvidence, is_inferred), `src/schema/graph.py` (GraphEdge + provenance + is_inferred), `src/schema/queries.py` (QueryPlan/ClaimVerdict).
- Retrieval: `query_understanding.py` deterministic parse (release/platform/module/API/REQ regex, intents), `modalities.py`, `metadata_filter.py`, `pipeline.py`, `graph.py`, `fusion.py` (RRF + weighted_fusion), `reranking.py`, `context.py` (parent_expand/compress, normative bonus), `clarify.py`.
- Generation: `providers.py` (ProviderSpec ollama/openai_compat, complete/stream, list_ollama_models), `prompts.py` (citation-grounded), `answer.py`, `citations.py`, `verification.py` (split_claims/verify/confidence/abstain).
- Indexing: `build.py`, `qdrant_index.py`, `hybrid.py` (BM25 lexical for identifiers).
- Config/obs/eval: `src/config/settings.py`, `src/observability/logging.py`, `src/evaluation/` (datasets/metrics/run/ablation A–F).
- Docker: `docker-compose.yml` profiles minimal/standard/full (api, streamlit, frontend, qdrant, ollama, postgres, opensearch, neo4j, redis). Persist canonical.db, qdrant, conversations, reports.

## 3. Capability matrix (summary; full table in rag-anything-capability-mapping.md)
Existing: Docker, chat UI, Ollama, cloud LLM compat, PDF tables/figures, RDF-like edges, vector+BM25 hybrid, version filter, citations, claim verification, Streamlit+React, tests/benchmarks.
Gaps closed by this branch (additive, no rewrite): exact-spec `CanonicalContent`, async `ParserAdapter`, 6 modality processors, provider Protocols + task routing + privacy policy, extended graph node/relation vocab + provenance, typed collections payload contract, modality-aware planner, spec fusion weights, modality context rules, strict system prompt, spec claim JSON, streaming event catalogue, upload/reprocess contract.

## 4. Risks / rollback
- Additive-only: existing Chunk/MultimodalEvidence/GraphEdge/ProviderSpec paths untouched; new modules are opt-in.
- `RAG_PIPELINE_VERSION=v1` ignores new tables; canonical.db rollback = restore prior db file.
- No accuracy claim without benchmark (spec §18/§21); run `pytest` + eval harness before enabling new pipeline.
