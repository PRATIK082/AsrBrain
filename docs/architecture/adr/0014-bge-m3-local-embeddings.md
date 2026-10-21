# ADR-0014 — BGE-M3 locally via Ollama for dense retrieval

- **Status:** accepted
- **Date:** 2026-10-21
- **Product owner decision:** proposed 2026-10-21 ("Vector Embeddings: BGE-M3 or nomic-embed-text running locally on Ollama").

## Context

Dense retrieval currently uses **TF-IDF** (`settings.embedding_backend =
"tfidf"`), which is a lexical-overlap vectoriser, not a semantic model. It
works, it needs no model, and it has no licence obligations — but it cannot
match "the frame is never sent" to "signal transmission is not performed".

The owner proposed a local semantic embedding model served by Ollama.

## Decision

**BGE-M3 (MIT), served locally by Ollama, is the dense embedding model.**
`nomic-embed-text` is the documented runner-up.

### Model choice

| | BGE-M3 | nomic-embed-text |
|---|---|---|
| Licence | MIT | Apache-2.0 (note: **not** MIT as commonly stated) |
| Dimensions | 1024 | 768 |
| Context | 8192 tokens | 8192 tokens |
| Languages | 100+ (multilingual) | English-focused |
| Code & technical text | strong (trained on code + technical corpora) | weaker |
| Serving | Ollama `bge-m3` | Ollama `nomic-embed-text` |

BGE-M3 wins on the properties this corpus has: long technical sections,
German/English AUTOSAR documents, and code. The licence correction matters:
Apache-2.0 is permissive, so `nomic-embed-text` is perfectly usable — it is
simply the weaker model for this corpus, not a licensing problem.

### Non-negotiable constraint: the default does not change silently

`embedding_backend` stays **`tfidf`** until the evaluation harness shows the
new backend is better on our own corpus. The switch is a feature flag
(`ASRBRAIN_EMBEDDING_BACKEND=bge-m3`) and requires:

1. A measured **retrieval recall@k / precision@k** comparison against the
   golden dataset (`src/evaluation/`, `reports/evaluation/`) on the current
   TF-IDF baseline.
2. A measured effect on the citation-validity and grounded-answer metrics
   (ADR-0001's statuses must not get *worse*).
3. A recorded decision in this ADR's "review" section, with the numbers.

A retrieval change that silently degrades answer quality is worse than no
retrieval change at all.

### Hybrid stays hybrid

Dense retrieval is added **alongside** BM25 lexical scoring, not instead of
it. Technical identifiers (`SWS_CanIf_00123`, `Com_SignalTransmit`) are
matched by lexical search and by the exact-keyword modality indexes
(`src/indexing/collections.py::EXACT_KEYWORD_FIELDS`); a dense model alone
routinely mangles them. Fusion stays RRF (`settings.rrf_k = 60`).

### Where the vectors live

* **Phase 2/3:** dense vectors stay in the local `HybridIndex` artefact
  (`<path>.npz` + `.meta.json`) behind the existing abstraction.
* **Phase 3+:** the production vector store is **`pgvector` inside
  PostgreSQL** (ADR-0010) — one fewer service than a separate Qdrant
  deployment. `src/indexing/qdrant_index.py` remains an optional adapter, and
  its default-deny tenant filter is the reference behaviour for any adapter.

### Payload contract

Every vector record must carry the provenance fields required by ADR-0002:
`project_id`, `artifact_id`, `artifact_version_id`, `source_type`,
`autosar_release`, `document_id`, `module`, `language`, `access_policy`,
`source_location_id` (page/section), and the provenance ids. This is a change
to the current payload, which only carries document-level fields.

## Consequences

* **Positive:** semantic matching over technical prose; a well-understood
  MIT model; no data leaves the machine; the dense side becomes real rather
  than a lexical vectoriser in disguise.
* **Negative:** embedding a corpus costs CPU time on first run (one-time per
  artifact version, and re-run only when the version changes); a 1024-dim
  float32 vector per chunk is ~4 KB, so 4 706 chunks is ~19 MB — fine locally,
  and fine in `pgvector` at production scale.
* **Risk:** an embedding model change invalidates the index. Mitigated by
  storing the model name and dimension in the index metadata and rebuilding
  when they differ.
* **Rule:** never let a model produce the answer's evidence set. The model
  embeds; the retriever ranks; the verifier cites.

## Alternatives considered

* **nomic-embed-text** — runner-up; English-focused and weaker on code.
* **`all-mpnet-base-v2` via sentence-transformers (the current default name)** —
  kept as an optional offline backend; it requires `torch`, which is a heavy
  dependency for a CPU-only local deployment.
* **A hosted embedding API** — rejected: it would ship AUTOSAR specification
  text to a third party, which the data-classification policy forbids by
  default (ADR-0009).
