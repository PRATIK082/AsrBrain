# Current-State Audit — AsrBrain (repo: RAG_LLM)

Date: 2026-09-29. Method: static read of all 6 Python files + live inspection of `docling_rag.db` (53 chunks) and `pdf/AUTOSAR_FO_PRS_SOMEIPProtocol.pdf` (92 pages, 1.56 MB). No code modified.

## 1. Repository inventory

| Path | Role | Lines | Notes |
|---|---|---|---|
| `streamlit_app.py` | Streamlit entry point #1: Standard RAG vs DocLong RAG | 183 | Loads `all-mpnet-base-v2` at import; rebuilds FAISS per query |
| `docling_rag_app.py` | Streamlit entry point #2: Docling/TF-IDF UI | 237 | Sidebar exposes chunk_size/overlap/top_k/search mode/LLM model |
| `pdf_rag_system.py` | Standard RAG: pypdf + ST + FAISS IVF + BM25 | 524 | Duplicate fn defs (§3); hardcoded `qwen3:14b` |
| `doclong_rag.py` | Hierarchical parent/small chunk RAG | 364 | Own `VectorDatabase("doclong_database.db")`; parent retrieval returns parents only, small-chunk hits discarded |
| `docling_rag_v2.py` | TF-IDF + NumPy RAG, optional Docling | 805 | Duplicate `transform()`; dead ollama fallback after `return`; `do_ocr=False, do_table_structure=False` |
| `database.py` | SQLite vector store (`vectors(id, embedding BLOB, metadata TEXT)`) | 80 | `str(metadata)` + `eval()` round-trip (injection risk); should be JSON |
| `pdf/` | Corpus | — | Single file: `AUTOSAR_FO_PRS_SOMEIPProtocol.pdf` (Foundation, SOME/IP, not Classic CanIf) |
| `docling_rag.db` | Only populated index | — | 53 chunks, 1 doc record (`pdf\AUTOSAR_FO_PRS_SOMEIPProtocol.pdf`, source=`pypdf`), ~173k chars |
| Missing | `docker-compose.yml`, `Dockerfile`, `.env`, `requirements.txt`, `tests/`, `reports/`, eval scripts, RDF store/code | — | Spec §1 assumption of "Docker-based + RDF pipeline" is **incorrect for this repo**. No `rdflib`/`sparql`/`owl` references in code |

## 2. Architecture (as built)

```
pdf/*.pdf
  └─ pypdf PdfReader.extract_text()  (page text concatenated, page numbers/headers kept inline, tables flattened)
       └─ word-split chunking (500/50 standard; 300/50 + 1500/100 doclong; 500/100 docling, whitespace-normalised only)
            └─ embeddings: all-mpnet-base-v2 (systems 1+2) or TF-IDF fit_transform (system 3, refit on every build_index)
                 └─ SQLite BLOB store (3 separate DB files, incompatible schemas, `eval`-parsed metadata: {chunk, index, file_path} only)
                      └─ per-query FAISS IndexIVFFlat(nlist=min(128,N)) trained on first ≤500 vectors, or NumPy cosine
                           └─ naive hybrid: FAISS top_k=5 + BM25 top_k=5, score = (1-dist) + raw BM25 (systems 1+2) or 0.7/0.3 blend (system 3)
                                └─ context = " ".join(chunks) → ollama.generate(qwen3:14b, temp 0.3, num_ctx 8192, generic prompt)
                                     └─ Streamlit text output; NO citations, NO version filter, NO verifier, NO confidence
```

Three parallel, non-interoperable stacks share nothing except `pdf/` and the `ollama` endpoint (`127.0.0.1:11434`).

## 3. Data flow & dependencies

- **Ingestion:** `os.walk("pdf")` → mtime/size dedup (not sha256) → blocking encode at import/startup. `streamlit_app.load_standard_rag()` calls `process_pdf()` twice per new file (lines 77–87). No classification, no release/platform/module/document-type extraction, no requirement/API/ECUC parsing, no hierarchy, no table pass, no OCR path, no quality report.
- **Chunk metadata (actual):** `{file_path, chunk_index, total_chunks, source}` (+ `chunk_type/parent_index` in doclong). No `document_id, release, platform, module, page_start/end, section, requirement_ids, api_names, sha256` — i.e. none of the canonical schema (§3 of spec) exists.
- **Retrieval:** top_k=5 everywhere; pools of ≤10 candidates (spec wants 80–120 fused → 8–20 final). No metadata pre-filter, no RRF/weighted fusion, no cross-encoder rerank, no parent-merge (doclong retrieves parents by independent search, ignoring small-chunk evidence), no compression, no retry/abstain.
- **Generation:** prompts contain no citation instruction and no version discipline ("answer based solely on context" only in v2). `pdf_rag_system.generate_response()` ignores its `model`/`llm` args and calls `ollama.generate` directly.
- **Dependencies (unpinned, no lockfile):** `streamlit, sentence-transformers, torch, faiss, pypdf, rank_bm25, ollama, httpx, numpy, sklearn (opt), docling (opt)`. Torch+FAISS+ST make local run heavy; the TF-IDF path exists precisely to avoid them but then sacrifices semantic quality on technical identifiers.
- **Confirmed code defects:** (a) `pdf_rag_system.py` defines `create_faiss_index_from_database` and `load_vectors_from_database` **twice** (second wins, first dead); (b) `docling_rag_v2.py` has duplicate `TFIDFEmbedder.transform` and a ~55-line dead `try: import ollama` block after an unconditional `return`; (c) `eval(metadata_str)` on DB content; (d) `IndexIVFFlat` with nlist=128 on a 53-vector corpus (over-partitioned, recall-harming); (e) `SQLiteVectorDatabase.get_document_count` counts distinct metadata strings, not documents; (f) `LIKE '%file_path%'` file lookups; (g) TF-IDF `fit_transform` on `build_index()` invalidates previously stored embeddings and changes dim.

## 4. Baseline corpus vs. spec target

Spec assumes 3–5 GB across Classic/Adaptive × many releases. Actual: **1 Foundation PRS PDF**. `RS_`×1409 / `PRS_`×959 hits confirm SOME/IP requirement IDs exist in the text, but with word-split chunking they can straddle boundaries and carry no page/section locator. Every benchmark class in spec §2 except narrow SOME/IP lookup is unanswerable (no CanIf/CanSM/PduR/Com content, no second release to compare, no ECUC containers).

## 5. Reusable vs. replace

- **Retain:** folder watcher + incremental-skip idea; SQLite `documents(file_path, file_hash)` ledger concept; BM25-for-identifiers intuition; DocLong parent/small two-level idea; Streamlit sidebar controls as UX starting point.
- **Replace/rebuild:** PDF extraction (need staged pipeline: hash → classify → PyMuPDF+layout+table → hierarchy → quality report); chunking (structure-aware atomic/context/parent, §5); metadata (canonical chunk schema + release normalisation, §3/§6); index (Qdrant dense+sparse+filters; Postgres/DuckDB canonical store; graph later); retrieval (typed QueryPlan → filtered hybrid → RRF → rerank → parent expansion → compression → verifier → abstain); generation (citation-grounded prompts + claim verifier + calibrated confidence); packaging (FastAPI + Compose profiles + pinned deps + tests/eval harness).
- **Do not "migrate" RDF:** there is no RDF in this repo to preserve. Treat graph/provenance as greenfield (keep spec §27 steps 2–4 as no-ops with a note, proceed with re-extraction).

## 6. Immediate risks before any rewrite

1. `eval()` on DB metadata + `str()` serialisation — convert to JSON on touch.
2. No `requirements.txt`/pins — `pip freeze` before changing anything.
3. Dead-code/duplicates — delete only after tests exist; second definitions are currently live.
4. Corpus single-PDF + Windows paths (`pdf\...` in DB) — normalise to POSIX + sha256 before multi-OS Docker.
5. Ollama hardcoded (`qwen3:14b`, `127.0.0.1:11434`) — parameterise via env (spec §21) when touching generation.
