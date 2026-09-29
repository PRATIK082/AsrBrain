# Target architecture

## Data flow

```
                         ┌────────────────────────────┐
 pdf/*.pdf ─────────────▶│ ingestion.pipeline          │
                         │ discovery/sha256 → extract  │
                         │ (PyMuPDF→pypdf) → normalize │
                         │ → signals (req/API/ECUC/    │
                         │   headings) → release/      │
                         │   platform/doctype detect   │
                         │ → quality report            │
                         └─────────────┬──────────────┘
                                       ▼
                         canonical.db (documents+chunks, §3 schema)
                                       ▼
                         hybrid index (BM25 tech-tokens + TF-IDF dense)
                          │  optional mirror: Qdrant / OpenSearch / Neo4j
                          ▼
 query ──▶ QueryPlan ──▶ hard filters ──▶ BM25+dense ──▶ RRF ──▶ rerank
   (intent/releases/        (never mix       (50+50)      (k=60)   (identifier
    modules/APIs/reqs)       releases)                                     boost)
            │ per-release branches for comparison │ parent-expand │ compress │
            ▼
     Ollama (citation-enforced prompt) or extractive fallback
            ▼
     claim↔evidence verifier → confidence → answer | abstain
            ▼
     FastAPI (/query /ingest /evaluate /health) · Streamlit (filters/trace/evidence/export)
```

## Boundaries

- Deterministic stages (parsing, filtering, fusion, verification, eval): pure functions, tested.
- Bounded LLM use: query is parsed deterministically; LLM only drafts from cited evidence,
  auto-falls back to an installed model (`pick_model()`), else to extractive passages.
- Graph/Neo4j is provenance-only; it never substitutes for document evidence.
