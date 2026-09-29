# Replacement Components (this upgrade)

| Old | New |
|---|---|
| Sidebar corpus filters (release/platform/module/doctype) | Conversational slot-filling: ask-back for missing release/platform, auto-detect module + confirm/change chips, doctype auto (trace-only) |
| Search-mode radio | Auto intent (`Mode: <intent> (auto)` caption) + advanced expander |
| Ollama-only generation | Provider abstraction: `OllamaProvider` + `OpenAICompatibleProvider` (GPT/Gemini/Opencode/cloud) with session-scoped API keys, streaming |
| Form-submit Streamlit UI | Chatbox-like chat UI: conversation sidebar, `st.chat_message` history, streaming tokens, regenerate/edit/stop, citation chips, evidence/trace/graph panels, upload, feedback, export |
| `POST /query` only | Full chat contract: conversations CRUD, `/api/chat`, `/api/chat/stream` (SSE), `/stop`, documents upload/list/reprocess, sources/page, feedback, models/releases/modules |
| Single text Chunk | `MultimodalEvidence` record (text/table/figure/diagram/equation/requirement/api/configuration/graph) + parser adapters (Docling primary-opt, PyMuPDF validator, MinerU/Marker optional, pypdf baseline) + modality indexes |
| Flat prompt draft | Per-mode answer formats (normal/comparison/troubleshooting/insufficient) |
| Static answer | Staged workflow events (status/evidence/token/complete) for streaming + cancellation |
