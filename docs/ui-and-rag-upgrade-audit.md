# UI + RAG Upgrade Audit (Part A)

Date: 2026-09-30. Scope: current repo before Chatbox/multimodal upgrade. No production code modified for this audit.

## What exists

| Area | State |
|---|---|
| Streamlit UIs | 3: legacy `streamlit_app.py` (Standard/DocLong radio), legacy `docling_rag_app.py` (TF-IDF controls), new `apps/streamlit/app.py` (filter sidebar: release/platform/module/doctype selects, mode radio, evidence/trace expanders, feedback, export). None has chat history, streaming, conversations, or upload |
| Backend API | `apps/api/main.py`: `GET /health`, `POST /query`, `/ingest`, `/evaluate`. No conversations, no streaming, no documents/sources/feedback/models endpoints |
| Document model | `src/schema/documents.py` (Chunk, text-only) + canonical SQLite (`documents`, `chunks`). No tables/figures/images/OCR fields |
| PDF parsing | `src/ingestion/pdf_extract.py`: PyMuPDF preferred → pypdf fallback, header/footer strip, requirement/API/ECUC/heading signals, release/platform/doctype detect, quality report. Docling optional only in legacy `docling_rag_v2.py` (tables/OCR disabled). No parser interface, no MinerU/Marker/Unstructured |
| Chunking | `src/ingestion/chunking.py`: atomic (220w) + context (600w) + stable IDs + page ranges. Text-only |
| Indexes | Local `HybridIndex` (BM25 tech-tokens + TF-IDF dense, `data/indexes/hybrid.*`, 169 chunks) + `qdrant_index.py` mirror stub. No separate requirement/API/ECUC/table/figure indexes; no OpenSearch wiring |
| Retrieval | `src/retrieval/`: deterministic QueryPlan parsing, controlled rewriting, hard metadata filters, RRF + weighted fusion, identifier-boost rerank, parent-expand, extractive compression, co-mention graph edges. Single text pool |
| Generation | `src/generation/`: citation-enforced prompt, Ollama-only (`pick_model()` auto-fallback + extractive fallback), claim verifier, confidence/abstain, citation block |
| Graph | `src/retrieval/graph.py` (co-mention + implements edges) + `src/schema/graph.py` (no confidence/is_inferred fields) |
| Eval | `src/evaluation/`: 8-query JSONL gold set, runner (hit/abstain/claim-support/latency), metrics incl. nDCG/MRR helpers, ablation arm map |
| Docker | `docker-compose.yml` (profiles minimal/standard/full), `docker/Dockerfile.{api,streamlit}`. No frontend service, no `RAG_PIPELINE_VERSION` |
| Config/tests | `src/config/settings.py` env-driven; 12 tests pass (unit + retrieval + API integration) |

## Gaps vs. target (Parts B–O)

1. No conversational slot-filling: release/platform filters are sidebar dropdowns; empty = unfiltered (silent version mixing risk). No ask-back, no module confirm/change, no doctype auto-routing surfaced.
2. Search-mode radio is non-standard (ChatGPT/Copilot/Gemini auto-detect intent). Intent is detected but exposed as a manual mode switch.
3. Provider lock-in: Ollama only; no cloud (OpenAI/Gemini/Opencode) path, no API-key handling.
4. UI is form-submit Q&A, not Chatbox-like: no sidebar conversations, history, streaming, regenerate/edit/stop, citation chips, page preview, upload/drag-drop.
5. No multimodal records (tables/figures/diagrams/equations/images/OCR), no parser adapters, no modality indexes, no SSE chat contract, no React frontend.
