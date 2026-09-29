# Migration Risks (UI + multimodal upgrade)

| ID | Risk | Mitigation |
|---|---|---|
| U1 | Breaking working `/query` + Streamlit fallback | Additive only: new endpoints under `/api/`; legacy kept; `RAG_PIPELINE_VERSION=v1\|v2` rollback flag |
| U2 | API keys leaked (logs/db) | Session-state/memory only, `type="password"`, never logged or persisted; cloud calls direct from backend per-request |
| U3 | Slot-fill interrogation loops annoy users | Ask at most once per missing slot; "answer generally / all versions" escape; remember convo-level slots |
| U4 | Module auto-detect wrong → wrong filter | Show `Detected: X [Confirm] [Change]`; filtering applies only after confirm or on explicit terms |
| U5 | Streaming complexity breaks Streamlit | Server streams SSE for React; Streamlit simulates tokens from complete draft + uses stop flag; both behind same router |
| U6 | Multimodal re-ingest invalidates chunk IDs | Additive `evidence`/`figures`/`tables` stores; text chunk IDs stable; versioned index dir; shadow compare before switch |
| U7 | Generated figure descriptions treated as fact | Descriptions stored `is_inferred=true`, never cited alone; citations require source page |
| U8 | React build doubles maintenance | React is a skeleton over the same `/api/` contract; Streamlit remains the supported fallback; no retrieval logic in frontend |
| U9 | Heavy parser deps (Docling/MinerU) break install | Optional extras only; PyMuPDF/pypdf path is the guaranteed default; adapters import-guarded |
