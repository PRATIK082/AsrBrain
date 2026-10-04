# Rollback Guide

- Retrieval: set `RAG_PIPELINE_VERSION=v1` (legacy fusion/context/prompts; new modules ignored).
- Index: restore prior `data/canonical/canonical.db` backup; Qdrant snapshots per collection (`text, requirement, api, ecuc, table, image, diagram, equation`).
- Graph: `GraphEdge` store untouched by this branch; `multimodal_graph.py` types are additive — delete new edges by provenance `is_inferred=true` if needed.
- Code: `git revert` or checkout `main`; new files are isolated (`canonical.py`, `parser_adapter.py`, `processors.py`, `routing.py`, `multimodal_graph.py`, `collections.py`, `planner.py`, `modality_fusion.py`, `context_rules.py`).
- UI: Streamlit fallback always available; React gated by `full` profile.
- Verify: `python -m pytest tests/unit -q` (36 passed baseline: 28 existing + 8 new).
