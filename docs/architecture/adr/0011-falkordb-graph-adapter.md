# ADR-0011 — FalkorDB is the production graph adapter

- **Status:** accepted
- **Date:** 2026-10-21
- **Refines:** ADR-0007 (`GraphStore` protocol)
- **Product owner decision:** proposed 2026-10-21 ("Graph Engine: FalkorDB (LGPL-3.0) — high-performance, memory-optimized matrix graph engine").

## Context

ADR-0007 defined a `GraphStore` protocol (`upsert_nodes`, `upsert_edges`,
`neighbors`, `paths`, `subgraph`, `stats`) with a local implementation for
development and a production adapter to be chosen later. The product owner
proposed **FalkorDB** (LGPL-3.0), a Redis-modules property graph built on
RedisGraph, using a matrix-based adjacency representation.

## Decision

**FalkorDB is the production graph adapter.** ADR-0007's "Neo4j or RDF/Jena"
wording is superseded by this ADR. The `GraphStore` protocol is unchanged, and
the local SQLite implementation remains the development default.

## Why FalkorDB

* **Licence.** LGPL-3.0 is *less* restrictive for commercial use than Neo4j
  Community's GPLv3, and it is a weak copyleft: using it as a network service
  does not oblige us to publish our own code. The licence obligation sits on
  FalkorDB itself, not on this product.
* **Speed and footprint.** The matrix adjacency representation makes
  multi-hop traversal and neighbourhood expansion fast enough to run inside a
  request path, which matters because the answer pipeline expands the graph
  when the question is architectural.
* **Operational fit.** It is a Redis module, so it fits the existing
  `docker-compose.yml` topology and shares the memory model we already reason
  about; a separate JVM service (Neo4j) is a heavier addition.
* **Cypher.** openCypher is supported, so the query layer is portable and the
  `GraphStore` implementation stays small.

## Constraints this decision imposes

* **We depend on the `GraphStore` protocol, not on the FalkorDB server.** The
  server is a deployment choice, exactly like the S3 provider in ADR-0012. Any
  deployment must be able to run the SQLite adapter.
* **Every edge must carry provenance** (ADR-0004): artifact version, source
  location, extraction method, confidence, `is_inferred`, lifecycle state.
  FalkorDB's property model supports this; the discipline is enforced at write
  time by the store, not by the database.
* **Inferred edges can never satisfy `VERIFIED`** (ADR-0001). This is a
  property of the edge, not of the database, so it must be stored and queried.
* **Redis is a cache, not a system of record.** The graph is *derived* from
  artifacts and evidence; it can be rebuilt from the registry. Losing it must
  not lose evidence.

## Consequences

* **Positive:** a graph backend that can be dropped into the existing Compose
  topology, with a permissive licence and fast traversal.
* **Negative:** no RDF/SPARQL support, so a semantic-web stack is out of reach;
  and a Redis module has a smaller ecosystem than Neo4j — the adapter must stay
  thin and the protocol must stay the contract.
* **Risk:** if FalkorDB's Cypher support diverges from what the adapter needs,
  the fallback is the SQLite implementation, not a rewrite — the protocol
  bounds the blast radius.

## Alternatives considered

* **Neo4j** — rejected: GPLv3 for the community edition is a heavier
  obligation for a permissive-licence product, and the JVM service is
  operationally heavier.
* **RDF / Jena** — deferred: it would suit a standards-driven ontology
  workflow, but it forces an RDF data model onto a property graph that the
  ARXML and requirement models do not naturally use.
* **Store the graph in PostgreSQL (recursive CTEs + `ltree`)** — kept as a
  *legitimate* alternative for the traversal subset; it is the fallback if the
  graph never outgrows one machine.
