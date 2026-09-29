# Preserved Components (do not rewrite)

- `src/ingestion/pdf_extract.py` signal extractors + quality report shape; `chunking.py` stable-ID atomic/context scheme.
- `src/schema/queries.py` QueryPlan/ClaimVerdict; canonical SQLite layout (additive migrations only).
- `src/indexing/hybrid.py` tokenizer + BM25/TF-IDF (kept as the CPU default index).
- `src/retrieval/`: parsing, rewriting, metadata_filter, fusion (RRF/weighted), reranking, context (parent-expand/compress), pipeline per-release branches.
- `src/generation/`: prompts, citation block, verifier, confidence/abstain math; `pick_model()` fallback idea extended to providers.
- `src/workflows/router.py` orchestration (extended with staged events, not replaced; no LangGraph/LlamaIndex swap — router is already the "strong implementation").
- `src/evaluation/` datasets/runner/metrics; `POST /query` + legacy Streamlit apps (kept as fallback).
- Docker profiles, volumes, healthchecks; `database.py` JSON-metadata fix.
