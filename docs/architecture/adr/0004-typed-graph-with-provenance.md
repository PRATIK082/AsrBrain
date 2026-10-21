# ADR-0004 — Typed graph with mandatory provenance; no untyped "AI relationships"

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §3.2, §3.3

## Context

There are two unrelated "graphs" in the repository today.

1. `src/retrieval/graph.py::extract_edges()` derives edges **on every request** from
   chunk text: module names co-mentioned in a passage become
   `predicate="co_mentioned_with"` (confidence 0.7, `is_inferred=True`), and the first
   five API names of a chunk become `predicate="implements"` (confidence 0.9,
   `is_inferred=False`). Nothing is stored; there is no traversal; the only consumer is
   the `graph` field of the `complete` SSE event.
2. `src/ingestion/arxml/graph_export.py::export_graph()` produces a deterministic
   in-memory graph with five relations (`CONTAINS`, `HAS_PORT`,
   `REFERENCES_INTERFACE`, `ASSEMBLY_CONNECTS`, `DELEGATES_TO`) and a BFS
   `neighbors()`.

`src/schema/graph.py` contains only `GraphEdge` — there is no `GraphNode` model
anywhere. `src/schema/multimodal_graph.py` defines a `NODES`/`RELATIONS` vocabulary
(19 strings each) and a `TypedEdge` with `model_valid()`, but it is **not wired** to
anything, and `ClaimVerdict` is referenced nowhere outside its own module.

The failure mode we must prevent: an LLM emits a relationship, it is stored as a
string, and weeks later a user cannot tell whether it came from the specification or
from a guess. That is precisely the "untyped AI relationship" the product must not
have.

## Decision

1. **Every graph node and edge is typed.** A node has a `node_type` from a closed
   vocabulary; an edge has a `predicate` from a closed relation vocabulary. Writing
   an edge whose predicate is not in the vocabulary is **rejected at write time**, not
   filtered at read time.
2. **Provenance is mandatory on every edge.** `artifact_version_id` +
   `source_location_id` (or explicit `not_applicable`), `extraction_method`
   (`parser` | `regex` | `llm` | `import`), `confidence`, `is_inferred`,
   `lifecycle_state` (`proposed` | `machine_extracted` | `reviewed` | `approved` |
   `rejected`).
3. **Inferred edges can never satisfy `VERIFIED` on their own** (§ADR-0001). They are
   rendered distinctly everywhere in the UI and are filterable by provenance.
4. **Adopt the existing `multimodal_graph` vocabulary as the seed**, extend it with the
   ARXML and requirement/test types, and make `TypedEdge` the single edge type. The
   `GraphEdge` dataclass is kept for backward compatibility and adapted.
5. A **graph interface** (`GraphStore` protocol) with a local SQLite implementation
   and a production adapter — see [ADR-0007].

## Consequences

**Positive**

- Every relationship in the product is explainable: "this edge came from this
  version of this file, at this location, by this method, with this confidence".
- The UI can filter by provenance and by extraction method, which is what an
  engineer needs to trust a graph view.
- The type vocabulary is enforceable in tests, so a model cannot invent relations.

**Negative**

- The vocabulary must be curated; a new AUTOSAR release or a new artifact type
  requires a vocabulary change and a migration.
- LLM-extracted relations are constrained and will be refused more often — the
  remedy is to extend the vocabulary deliberately, not to relax the check.
- The current `co_mentioned_with` edges are inferred co-mentions with no artifact
  location; they are migrated as `machine_extracted` with `is_inferred=True` and
  `source_location_id=not_applicable`, and they are excluded from `VERIFIED`.

**Rejected alternatives**

- *Keep free-text predicates* — the status quo, and the exact failure being prevented.
- *Store the LLM output verbatim in a notes field* — the same problem with extra steps.
- *Use only the deterministic ARXML graph* — loses the spec-level relations that
  make the graph useful for reasoning; the deterministic graph remains a subset.
