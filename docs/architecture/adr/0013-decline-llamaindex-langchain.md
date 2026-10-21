# ADR-0013 — LlamaIndex / LangChain are not the orchestration core

- **Status:** accepted
- **Date:** 2026-10-21
- **Product owner decision:** proposed 2026-10-21 ("Orchestration & Ingestion: LlamaIndex / LangChain (MIT) — frameworks to glue document chunking, graph population and LLM querying together").

## Context

The owner proposed LlamaIndex or LangChain as the orchestration and ingestion
layer that "glues document chunking, graph population and LLM querying
together".

AsrBrain already contains that glue, written against the product's own
evidence model:

| Concern | Existing implementation |
|---|---|
| chunking | `src/ingestion/chunking.py` → `src/schema/documents.py::Chunk` |
| retrieval | `src/indexing/hybrid.py::HybridIndex` (BM25 + TF-IDF), `src/retrieval/pipeline.py::RetrievalPipeline` |
| query understanding | `src/retrieval/query_understanding.py` → `src/schema/queries.py::QueryPlan` |
| routing & planning | `src/retrieval/planner.py`, `src/retrieval/clarify.py`, `src/retrieval/modes/` |
| fusion & reranking | `src/retrieval/fusion.py`, `src/retrieval/reranking.py`, `src/retrieval/context.py` |
| generation & citation | `src/generation/{answer,prompts,citations,verification}.py` |
| staged orchestration | `src/workflows/stages.py` (10 stages, SSE event contract) |
| graph population | `src/retrieval/graph.py`, `src/ingestion/arxml/graph_export.py` |
| multimodal ingestion | `src/ingestion/processors.py`, `src/ingestion/diagram_mermaid.py`, `src/ingestion/vlm.py` |

## Decision

**We do not adopt LlamaIndex or LangChain as the orchestration or ingestion
core.** The existing deterministic pipeline stays.

Both frameworks may be used later **behind an interface**, for one narrow
connector only — for example a third-party document source that one of them
reads better than we do. That is a connector decision, not an architecture
decision, and it must not become a path by which the product's own evidence
model is bypassed.

## Why

1. **The evidence-first contract depends on the pipeline we already have.**
   `run_staged` emits a fixed event sequence (`status`, `clarify`, `evidence`,
   `token`, `complete`), the clarify gate fires on missing slots, and
   `verification.verify` maps claims back to evidence ids. ADR-0001 turns
   those outputs into the four answerability statuses. Swapping the
   orchestrator would mean re-implementing the gate, the verifier and the UI
   event contract against a framework's abstractions.
2. **They duplicate our canonical and evidence models.** Both bring their own
   node, chunk, embedding and prompt abstractions. Our `CanonicalContent`,
   `SourceLocation`, `Citation` and `EvidenceClaim` records are the ones that
   satisfy ADR-0002's provenance requirements. Keeping two parallel models
   guarantees they drift.
3. **"No invented evidence" becomes hard to prove.** Our guarantee is
   structural: claims are extracted, matched to evidence ids, and downgraded
   when they are not. Framework-managed prompt assembly and post-processing
   make that guarantee a matter of configuration rather than code.
4. **Dependency and maintenance cost.** These are large dependency trees with
   frequent breaking changes; the repository is currently dependency-light and
   the corpus pipeline is stable.
5. **They optimise for the wrong thing.** Their default goal is "answer the
   question", ours is "answer the question *with its evidence, or say that the
   evidence is missing*". The second is a harder constraint that our own code
   expresses directly.

## Consequences

* **Positive:** the deterministic, inspectable, citation-bound behaviour that
  the product promises stays under our control and is testable.
* **Negative:** we build and maintain the graph/ingestion glue ourselves. This
  is a real cost, accepted deliberately — it is the same cost that makes the
  evidence guarantees possible.
* **Rule:** if a framework is introduced for a connector, it must terminate at
  our own model boundary. A connector may *produce* `Artifact` /
  `ArtifactVersion` / `SourceLocation` records; it may not produce answers.

## Alternatives considered

* **Adopt LangChain for agent orchestration only** — deferred and currently
  rejected: the product's agent surface is a bounded, tool-first loop
  (ADR-0006) with a hard step budget; a general agent framework is larger than
  the problem.
* **Adopt LlamaIndex for ingestion only** — deferred: our ingestion already
  handles PDF, tables, figures, ARXML, Mermaid and diagrams with per-modality
  provenance. A connector adapter is possible later for a source we do not
  have a parser for.
