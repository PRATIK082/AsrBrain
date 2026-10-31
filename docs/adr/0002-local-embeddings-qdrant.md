# ADR-0002 — Local dense embeddings (BGE-M3 class) + Qdrant mirror for retrieval

- **Status:** Proposed (spike in progress; Accepted/Rejected after golden-set benchmark)
- **Date:** 2026-10-23
- **Deciders:** repository owner, engineering
- **Context:** AGENTS.md §4 (defaults), §6 (ADR required to replace vector store / embeddings)

---

## Context

Dense retrieval today is hand-rolled TF-IDF over a numpy matrix (`EMBEDDING_BACKEND`
has an `sbert` setting with no code path behind it; `qdrant_index.py` is an ops-only
stub). Hand rules (aliases, expansions, typo maps) ethically cannot scale to 10k+
paraphrased question forms: similar meaning needs vector semantics. Measured floor:
retrieval recall **0.115 ± 0.002** (run-to-run noise band, documented 2026-10-23).

## Decision (spike)

1. **Embeddings:** BGE-M3-class multilingual open model, run **locally** via
   `sentence-transformers` (already installed: 5.2.3 + CUDA torch). No cloud calls,
   no data leaves the box (confidential-project constraint). Wired as a real
   `EMBEDDING_BACKEND=sbert` path in `HybridIndex`, keeping `tfidf` as default
   until the benchmark decides.
2. **Vector store:** Qdrant in **local persistent mode** (`QdrantClient(path=...)`,
   no Docker/server needed — Docker is unavailable on this machine). Payloads carry
   the existing metadata (release/platform/module/ids/pages) so filters stay
   server-side. Extends `qdrant_index.py`; local npz index remains the default.
3. **Kept regardless:** vectorised BM25 (0.05 s, no server), SQLite canonical store +
   provenance, hash-frozen hold-out, CombMAX fusion, exact-ID fast path.

## Alternatives considered

- **Ollama embeddings (nomic-embed-text):** zero new deps, but weaker multilingual
  retrieval quality than BGE-M3 class and tied to the Ollama server lifecycle.
- **Qdrant server via Docker:** unavailable here; local mode is benchmark-identical
  for single-node scale and migrates to server mode with one client-arg change.
- **Cloud embeddings API:** rejected — violates the offline/on-prem constraint.
- **TF-IDF only:** rejected as the ceiling — measured 0.15 cosine on a clear
  paraphrase pair during flywheel mining.

## Consequences

- New local artefacts (model cache ~2.3 GB, `data/indexes/qdrant/`) stay git-ignored;
  only code + eval numbers are committable.
- If recall delta < noise band (±0.002) on the frozen hold-out, the spike is
  **rejected** and removed — no dead code left behind (post-cleanup rule).
- Slice 3 (cross-encoder rerank) reuses whichever dense backend wins here.

## Gate

`python -m src.evaluation.cli run --mode retrieval` on `train` (tune) then `holdout`
(report only), same index content, both backends. Numbers in the slice-2 review.
