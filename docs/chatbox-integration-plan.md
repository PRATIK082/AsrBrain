# Chatbox Integration Plan

## Strategy
1. Improve Streamlit first (`apps/streamlit/app.py` already Chatbox-like fallback).
2. FastAPI streaming endpoints already in `apps/api/main.py` (`/api/chat`, `/stream` SSE); event catalogue below is the contract.
3. React frontend in `frontend/`; keep Streamlit until parity. No Chatbox Community Edition code vendored; backend stays separate via API/provider integration only (license-safe).

## Separation rules
- UI: no retrieval logic. API: no parser logic. Parsers → CanonicalContent only. RAG independent of LLM provider (same interface for Ollama/cloud). RDF/edges retained. Provenance on every result. No hidden CoT in UI.

## Views (1–9)
Chat, Conversations, Documents, Ingestion status, Evidence, Graph explorer, Settings, Model routing, Evaluation dashboard — mapped to existing `/api/` routes + new docs contract.

## Streaming events (SSE/WS)
`conversation_created, query_started, query_plan, filters_applied, retrieval_started, evidence_found, graph_path_found, reranking_complete, context_ready, answer_token, citation_added, validation_update, warning, answer_complete, answer_abstained, error` — see `src/workflows/stages.py` (status/clarify/evidence/token/complete today; remaining events are thin wrappers documented here and emitted by planner/fusion/context/verify stages).

## Renderer rules
Streaming responses, citations as clickable source cards (`sources/page` endpoint), tables/Markdown render, evidence side panel, credentials in renderer only from session (never persisted/logged), secure IPC/preload if wrapped in desktop shell.
