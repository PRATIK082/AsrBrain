# ADR-0012 — Depend on the S3 API, not on MinIO the product

- **Status:** accepted
- **Date:** 2026-10-21
- **Product owner decision:** proposed 2026-10-21 ("Object & Binary Storage: MinIO (AGPL-3.0) — S3-compatible file engine to hold the raw 1GB source files and PDFs").

## Context

The product needs object storage for the raw bytes: 1 GB+ of source PDFs,
ARXML files, diagrams and test artefacts, addressed by content hash, with
owner, project, branch, release and access policy recorded alongside the
object (ADR-0002, `Artifact` / `ArtifactVersion`).

The owner proposed **MinIO**, which is AGPL-3.0.

## Decision

**We depend on the S3 API, never on MinIO the product.**

* The product code speaks the **S3 protocol** (`GetObject`, `PutObject`,
  `ListObjectsV2`, presigned URLs) over HTTP.
* **MinIO is one deployment target of that protocol**, not a dependency.
* The development default is a **local content-addressed filesystem**
  implementation of the same interface.
* The registry records the object store *location* (`storage_uri`) on each
  `ArtifactVersion`, so the store can change without touching the evidence
  model.

Any S3-compatible server works: MinIO, Ceph RGW, SeaweedFS, Garage, or a
hosted bucket. Nothing in this repository links MinIO code.

## Why this matters: AGPL-3.0

AGPL-3.0 is the strongest copyleft in common use. If we *link* or *ship* MinIO
code as part of the product, network use of the modified product would oblige
us to publish the corresponding source. Keeping MinIO at arm's length — as a
separate service we talk to over the S3 API — keeps that obligation entirely
on MinIO and off this product.

The same rule applies to the operator: an organisation that runs MinIO as its
object store is making its own AGPL compliance judgement, which is their
call, not ours. We simply do not make the decision for them by shipping code.

## Interface

Phase 3 introduces a narrow `ObjectStore` protocol:

```python
class ObjectStore(Protocol):
    def put(self, key: str, data: bytes, *, content_type: str = "") -> str: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def stat(self, key: str) -> dict: ...      # size, content hash, mtime
    def delete(self, key: str) -> None: ...
    def presigned_url(self, key: str, *, expires_s: int = 900) -> str: ...
```

Two implementations: `LocalObjectStore` (content-addressed under
`data/objects/<sha256[0:2]>/<sha256>`) and `S3ObjectStore` (any S3-compatible
endpoint, configured by `OBJECT_STORE_*` settings). The registry stores the
`storage_uri`, never a vendor-specific handle, so the two are interchangeable.

## Consequences

* **Positive:** no AGPL in the product; deployment freedom; the local
  filesystem keeps development zero-dependency and offline.
* **Negative:** a compatibility surface to maintain — we implement the subset
  of S3 we need, and we must test against at least one real S3 server in CI.
* **Rule:** the object store holds **bytes only**. All metadata, provenance and
  access policy live in the relational registry. A lost bucket must never mean
  lost provenance.
* **Rule:** objects are content-addressed; a re-upload of identical bytes
  produces the same hash and a new `ArtifactVersion` row that points at it.

## Alternatives considered

* **Ship MinIO as a bundled service in `docker-compose.yml`** — rejected as
  the *product* decision; it is fine as one *deployment* option.
* **Ceph RGW (LGPL/Apache mix)** — a valid S3 target; heavier to deploy.
* **Store bytes in PostgreSQL as `bytea`** — rejected: large-object handling
  and backup size make the database the wrong place for 1 GB+ of binaries.
