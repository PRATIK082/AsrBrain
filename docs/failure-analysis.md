# Failure Analysis — why factual accuracy is capped at ~30–35%

Scope: maps each spec failure hypothesis to observed evidence in code/DB. No accuracy % is claimed as measured (no eval harness exists); "30–35%" is taken as the reported prior.

## 1. Verdict first

Dominant failure cluster is **retrieval recall + metadata absence**, not LLM size. With top_k=5 word-split chunks, no page/section/requirement/version fields, and a single-PDF corpus, most benchmark queries fail before generation. Fixing prompts or upgrading `qwen3:14b` alone cannot recover version routing, citations, or comparison support.

## 2. Hypothesis-by-hypothesis disposition

| Spec hypothesis | Finding | Evidence |
|---|---|---|
| Incorrect PDF extraction / missing pages | CONFIRMED (structural) | `process_pdf` = `page.extract_text() or ""` concatenation (`pdf_rag_system.py:36-42`, `doclong_rag.py:31-36`, `docling_rag_v2.py:435-445`). Page index, printed page no., headers/footers, reading order, scanned-page detection: none. Docling path disables OCR + table structure (`docling_rag_v2.py:371-373`) and live DB shows `source=pypdf` |
| Incorrect section boundaries | CONFIRMED | Word-window chunking only (`split_text_into_chunks`, `_split_into_chunks`). No heading detection, no hierarchy reconstruction |
| Table loss | CONFIRMED | No table extractor; pypdf flatten only. SOME/IP PRS is table-heavy → parameter/byte-layout answers will be garbled |
| Header/footer contamination | CONFIRMED | Only `re.sub(r"\s+"," ")` normalisation; no header/footer strip. Repeated AUTOSAR boilerplate pollutes every chunk and TF-IDF idf |
| Requirement IDs separated from text | HIGHLY LIKELY | 959 `PRS_` + 1409 `RS_` occurrences in a 53-chunk word split with no atomic-requirement rule; boundary straddles inevitable, unverifiable per-chunk without locators |
| Version metadata errors | CONFIRMED (by absence) | Metadata = `{file_path, chunk_index, total_chunks}`. No release/platform/module/doctype → every version-specific query (§2.B/C) is unroutable; silent wrong-version answers likely |
| Wrong document classification | CONFIRMED | No classifier. Only doc in corpus is Foundation PRS; system will answer "CanIf" questions from SOME/IP text or empty context |
| Ambiguous module names | CONFIRMED | No alias dictionary, no entity registry; `CanIf` vs `CanDrv` vs `Com` indistinguishable to TF-IDF-tokenised (`[^a-z0-9]` → space) or raw BM25 `split()` |
| Poor query understanding | CONFIRMED | No QueryPlan/intent/entities/releases. Raw string passed to all retrievers; comparison queries retrieved as one mixed pool |
| Retrieval recall failure | CONFIRMED (primary) | Candidate pool ≤10 (5 dense + 5 BM25), final top-5; spec floor is 80–120 fused. IVF nlist=128 on ~53–hundreds of vectors over-partitions; per-query retrain; TF-IDF refit per build; doclong discards small-chunk hits (`retrieve_with_parent_documents` returns parents only) |
| Reranking failure | CONFIRMED (missing stage) | No reranker of any kind |
| Context truncation | LIKELY | `" ".join(relevant_chunks)` with no token budget, no compression, `num_ctx=8192`; multi-chunk SOME/IP tables overflow or get cut mid-requirement |
| LLM synthesis errors | CONTRIBUTING | Generic prompts, no citation/version instruction in systems 1–2; temp 0.3 still free-form; no structured output |
| Citation mismatch / unsupported claims | CONFIRMED | No citation pipeline at all. Best case shows `file_path` in an expander; answers are plain text with zero page/section/requirement locators |
| Incorrect confidence scoring | CONFIRMED (missing) | No confidence, no verifier, no abstention path. "No relevant documents found" is the only fallback, triggered only on empty retrieval |

## 3. Predicted benchmark behaviour (pre-measurement)

- **A. Exact lookup** (e.g. `PRS_SOMEIP_...` in indexed PDF): partial success — the only class that can work, iff the ID survives in one chunk. `SWS_`-style Classic IDs: guaranteed fail (not in corpus).
- **B. Version-specific** / **C. Comparison** / **D. Relationships** / **E. Config** / **F. API+reqs** / **G. Troubleshooting** / **H. Deep explanation**: systematic fail — missing metadata, single release, no graph, no ECUC/API parsers, top-5 context too thin for multi-hop.
- Net: matches the reported 30–35% (narrow in-corpus lookups occasionally right; everything version-/citation-sensitive wrong or uncited).

## 4. What to measure first (not intuition)

Per spec §2/§22–23, before tuning: build the gold benchmark (A–H, with `gold_pages/sections/requirement_ids/claims`), then run ablations A–J and report Recall@10/MRR/faithfulness/citation-precision/version-accuracy/latency. The highest-leverage fix order predicted by this analysis: (1) canonical chunks + metadata + page locators, (2) hybrid with hard filters + RRF + rerank at proper candidate depths, (3) citation-grounded generation + verifier/abstain. Graph and agents only if (1)–(3) plateau.
