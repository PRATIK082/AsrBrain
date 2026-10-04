# Migration Guide (shadow mode → new pipeline)

1. Stay on `main` for production. Work on `feature/multimodal-rag-chatbox-upgrade`.
2. Ingest in shadow: run new `parser_adapter` + `processors` alongside existing pipeline; compare `ingestion_report.json` + `.quality.json` per document.
3. Keep `canonical.db` versioned: back up before migration; new `tables`/`figures` + typed collections are additive.
4. Gate with `RAG_PIPELINE_VERSION`: `v1` = legacy retrieval (ignores new stores), `v2` = planner + modality fusion + context rules + strict prompt + claim check.
5. Benchmark A–F (`src/evaluation/`): only switch default to v2 after Recall@10/MRR/nDCG, version/platform precision, citation precision/recall, claim support, abstention correctness meet bar. Never claim 95% without manual AUTOSAR benchmark.
6. Rollback: see `docs/rollback-guide.md`.
