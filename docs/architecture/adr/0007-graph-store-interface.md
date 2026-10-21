# ADR-0007 — Graph behind an interface: local SQLite now, Neo4j/RDF as an adapter

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §3.2, ADR-0004

## Context

The target product needs a Knowledge Graph Explorer and graph-aware retrieval
(Requirement → ArchitectureElement → ARXMLElement → CodeSymbol; Requirement →
TestCase → TestRun → TestResult; ChangeSet → impacted entities).

`docker-compose.yml` already defines a `neo4j:5` service (profile `full`,
credentials `neo4j/autosar`) — and **no code uses it**. There is no Neo4j driver, no
RDF store, no Jena. The only graph in the product is (a) per-request co-mention edges
derived from chunk text and (b) an in-memory ARXML projection with a BFS
`neighbors()`.

Adopting Neo4j immediately would mean: a mandatory second datastore for a local-first
tool, a new driver dependency, a second schema language (Cypher vs SQL) to maintain
alongside the corpus, and a graph that is unavailable in the "minimal" Compose
profile most contributors use. It would also front-load the hardest phase (typed
graph + provenance) behind an infrastructure decision.

## Decision

1. **Define a `GraphStore` protocol** now: `upsert_nodes`, `upsert_edges`,
   `neighbors(node_id, depth, filters)`, `paths(from, to, max_hops)`,
   `subgraph(ids)`, `stats()`. Filters must support the provenance fields
   (`artifact_version_id`, `extraction_method`, `is_inferred`, `lifecycle_state`,
   `project_id`, `release`).
2. **Implement it over SQLite** in the registry database (Phases 2–4). SQLite is
   already required, supports recursive CTEs for path queries, and keeps the
   deployment story simple.
3. **Treat the Neo4j/RDF adapter as a later, optional implementation** (Phase 4+)
   behind the same protocol. The Compose `neo4j` service stays as a reserved
   profile, documented as such, until an adapter exists.
4. **Query semantics are defined by the protocol, not the backend.** Node/edge
   typing, provenance filters and traversal depth caps are part of the contract, so
   an adapter cannot change the product's behaviour.
5. **The graph is optional in the request path.** If the graph is empty or
   unavailable, retrieval degrades to hybrid search and the answer status reflects
   the reduced evidence.

## Consequences

**Positive**

- The graph becomes a real, typed, persistent store without new infrastructure.
- The Neo4j/RDF option stays open without a rewrite; the adapter is an
  implementation of an existing interface.
- One datastore to back up in the default profile.
- Traversal depth caps and provenance filters are enforced in one place.

**Negative**

- SQLite graph queries are slower than a dedicated graph engine at large scale; the
  product's scale (thousands to low millions of edges) is well within SQLite's
  comfort zone, so this is acceptable for the target.
- A future Neo4j adapter must be behaviourally identical, which needs a
  contract-test suite over both implementations.
- "No graph" becomes a legitimate degraded mode that must be tested.

**Rejected alternatives**

- *Adopt Neo4j now* — new mandatory infrastructure for an unproven scale need, and
  it would front-load the graph work behind deployment concerns.
- *Keep the per-request co-mention graph* — it is not traversable, not persistent and
  not typed; it cannot back a Graph Explorer.
- *RDF/Jena as the primary store* — excellent semantics, heavy JVM dependency,
  awkward fit with the Python services.
