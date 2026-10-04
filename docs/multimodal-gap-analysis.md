# Multimodal Gap Analysis

## What exists
- Tables/figures extracted (captions, find_tables rows), stored in `tables`/`figures` SQLite + MultimodalEvidence (text/table/figure/diagram/equation/requirement/api/configuration/graph).
- OCR text field, generated-description slot (is_inferred), parent evidence id, parser + quality score.
- VLM/LLM via Ollama + OpenAI-compat; embeddings via existing backends; reranker present.

## Gaps → this branch (all clean-room, no HKUDS/RAG-Anything code)
1. Exact-spec `CanonicalContent` (11 content types incl. audio/video) → new `src/schema/canonical.py`, converters from Chunk/ParsedPage.
2. Async `ParserAdapter` (inspect/parse/parse_pages) + routing (PDF type, scanned, table complexity, OCR need, quality, disagreement) → new `src/ingestion/parser_adapter.py` wrapping existing sync parsers; optional MinerU/Marker/DOCX paths never required for startup.
3. Independent processors (Text/Requirement/Table/Image/Diagram/Equation) preserving raw source, normative language, table structure, VLM descriptions as supplementary → new `src/ingestion/processors.py`.
4. Provider Protocols + task routing (text_answer, requirement_extraction, table_interpretation, diagram_analysis, entity/relationship extraction, verification) + privacy (local_only, cloud_allowed, non-source-query-only, never_send_images) → new `src/generation/routing.py` over existing complete()/stream().
5. Graph vocab extension (15 nodes, 17 relations + provenance incl. is_inferred) → new `src/schema/multimodal_graph.py`; existing GraphEdge retained.
6. Typed collections payload contract (exact keyword fields, no stemming for identifiers) → new `src/indexing/collections.py`.
7. Modality-aware planner + vector-graph fusion spec weights + context inclusion rules + strict prompt + spec claim JSON → `src/retrieval/planner.py`, `src/retrieval/modality_fusion.py`, `src/retrieval/context_rules.py`, prompt constant + `to_spec_claim()` adapter.
8. Streaming event catalogue (16 events) + upload/reprocess contract → documented in chatbox-integration-plan; implemented via existing stages/api.

No silent Classic/Adaptive or release mixing: exact filters applied before context assembly (planner + metadata_filter + verification).
