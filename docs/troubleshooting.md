# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `503 Canonical store empty` from `/query` | no ingest yet | `POST /ingest` or `make ingest && make index` |
| Assistant keeps asking for release/platform | corpus spans versions and question names none | answer once (stored per conversation), or “any release”, or Advanced → “Answer generally” |
| Wrong module detected | alias overlap | use Change ▾ in the clarification card; filter applies after Confirm |
| Cloud model 401/errors | key/URL wrong | check Base URL + key; nothing is cached — retry immediately |
| Answers say "could not verify" for CanIf/4.x | corpus has only SOME/IP PRS | expected abstention — add Classic PDFs, re-ingest, `make eval` |
| Wrong model / slow generation | `LLM_MODEL` not pulled | API auto-picks an installed model; `ollama pull <model>` or rely on extractive fallback |
| Stale index after new PDFs | in-memory pipe cached | `POST /ingest` resets it; file mtime-hash replaced by sha256 |
| Legacy `streamlit_app.py` slow start | loads ST model at import | unchanged legacy; new UI (`apps/streamlit/app.py`) talks to the API instead |
| `eval(metadata)` errors in old DBs | legacy `str(dict)` rows | `database.py` now writes JSON and reads JSON-first with `ast.literal_eval` fallback |
| p50 latency ~35 s | 14 B local LLM per query | retrieval is <0.5 s; use smaller model or extractive fallback for bulk eval |
| “answer_drafting” spins for many minutes | uncapped output + 12 deep evidence on CPU | fixed: output capped (`LLM_NUM_PREDICT`, Concise 400 default), compression 1500 chars, Eco/Balanced/Deep depth; pick a smaller Ollama model (e.g. 8 B) or cloud for speed |
| Export gives empty file | fixed bug (conditional download button) | update to latest `apps/streamlit/app.py`; export is now always rendered |
| Upload seems stuck | full corpus re-index per upload | progress bar shows stage; time scales with corpus (500+ docs: prefer `POST /api/documents/upload` + Qdrant migration, see operations guide) |
