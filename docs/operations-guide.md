# Operations guide

## Index rebuild (reproducible)

```bash
python -m src.ingestion.pipeline --pdf-dir pdf --out data/canonical   # → canonical.db + *.quality.json + ingestion_report.json
python -m src.indexing.build --canonical data/canonical/canonical.db  # → data/indexes/hybrid.{npz,meta.json}
```

Or `POST /ingest` (does both and resets the in-memory pipeline). Quarantine rule: any PDF
with `quality_score < 0.5` or `pages_requiring_ocr` non-empty on scanned content is indexed but
flagged in `ingestion_report.json` — do not present it as reliable until re-extracted with OCR.

## Add PDFs

Drop files into `pdf/` (or set `PDF_DIR`), re-run ingest. Identity is sha256 (`document_id =
doc-<12hex>`); renames are safe, edits re-chunk. Paths stored POSIX-normalised on write.

## Model selection

Env (`cp .env.example .env`): `LLM_MODEL`, `EMBEDDING_BACKEND=tfidf` (default, CPU).
The API auto-picks an installed Ollama model if the configured one is absent, and falls
back to extractive answers with full citations when Ollama is down.

### Cloud providers (session API keys)

Sidebar → Provider → Cloud: set Base URL + Model + API key. Presets that work via the
OpenAI-compatible path: OpenAI (`https://api.openai.com/v1`, `gpt-4o-mini`), Gemini
OpenAI-compat endpoint, Opencode/Cloud or OpenRouter base URL + any model id. The key lives
in Streamlit session memory (or a single chat request) — it is never written to disk, the
database, or logs. React clients pass it per-request the same way.

## Rollback procedure

`RAG_PIPELINE_VERSION=v1`: legacy text-only retrieval, `/query` byte-identical behaviour,
`tables`/`figures` stores ignored. `v2` (default): multimodal + clarification + staged chat.
Chunk IDs are stable across versions, so switching needs no re-index — restart api/streamlit
(or the React frontend) with the flag set.

## Health / observability

- `GET /health` → `{status, llm, backend}`. Every retrieval stage logs via
  `src/observability/logging.py` (`log_stage`). Docker healthchecks hit `/health`.
- Volumes: `qdrant_vol, pg_vol, os_vol, neo4j_vol, canonical_vol, ollama_vol`. Backup
  `data/canonical/` + `data/indexes/`; PDFs live outside images.

## Feedback loop

UI 👍/🚨 → append the query + manually verified gold answer/claims to
`data/benchmarks/autosar_benchmark_v1.jsonl` → `make eval` → record in
`reports/evaluation/`. Never tune RRF k / weights / top_k on vibes — use ablation arms A–J.
