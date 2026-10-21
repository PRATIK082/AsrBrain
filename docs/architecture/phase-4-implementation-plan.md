# Phase 4 — ARXML as structured data, the deterministic tools and the Explorer (as built)

- **Branch:** `feature/mermaid-pdf-diagram-rendering`
- **Baseline:** Phase 3 (`80b3b8b`) — 147 pytest passing
- **Status:** implemented

Phase 4 turns ARXML from "RAG text with a parser bolted on" into **structured
data with a deterministic tool surface** (ADR-0005), and gives the graph a typed,
provenance-carrying home (ADR-0004, ADR-0007, ADR-0011).

---

## 1. What Phase 4 delivers

1. **A parser that keeps the facts.** Line ranges for every element, UUIDs,
   qualified paths that follow the `AR-PACKAGE` chain, and a release that is
   only recorded when the document states it.
2. **A validator that reports instead of asserting.** `validate_arxml` returns
   a `ValidationResult` payload: every check, every finding with a severity and
   a file/line. "Validated" is a claim, and a claim needs evidence.
3. **Six deterministic tools** with a discoverable catalogue.
4. **A typed graph store** with a closed vocabulary and mandatory provenance on
   every edge.
5. **A persistent ARXML runtime** so an uploaded document survives a restart.
6. **An additive v2 API** over the tools.
7. **The ARXML Explorer** in the React workspace.

### Not in Phase 4

* The ARXML graph is **not** yet persisted through the graph store — the tools
  answer from the parsed document; the store is ready for Phase 5.
* The `validate_arxml` result is not yet an `EvidenceClaim`; that binding lands
  with the answerability gate.
* No RDF/Jena adapter (ADR-0011 covers the production graph backend).

---

## 2. The parser rework

| Fact | Before | After |
|---|---|---|
| Source position | none | `line_start` / `line_end` on every element |
| UUID | never populated | captured from the `UUID` element |
| Release | always `None` | taken from `SCHEMA-VERSION` or a release element — **never invented**; an empty release produces a warning |
| Element containers | only *direct* children of a component | also `PORTS`, `INTERNAL-BEHAVIORS`, `IMPLEMENTATION/CODE` — the containers real ARXML uses |
| Port `comspec` | dead field | populated from `COM-SPECIFICATION` |
| Runnable `events` / `data_accesses` / `server_call_points` | dead fields | populated |
| ECUC `value_type` / `reference_target` | dead fields | populated |
| Connector component refs / composition ref | dead fields | populated |

The line numbers come from a small expat-based reader
(`src/ingestion/arxml/xml_reader.py`). `xml.etree.ElementTree` discards source
positions, and its C accelerator exposes no `CurrentLineNumber`, so the reader
builds the tree itself and records the line of every element. The reader also
keeps the raw prefixed tag names, so the AUTOSAR namespace is read from the
root's `xmlns` attribute.

**Security:** the DOCTYPE/ENTITY rejection of the previous parser is kept, and
the reader never resolves external entities.

---

## 3. The six deterministic tools

| Tool | Answers | Never does |
|---|---|---|
| `validate_arxml` | which checks ran, which findings were observed, at which line | say "the file is fine" without a finding list |
| `resolve_arxml_references` | which reference resolves to which element, and which do not | guess an unresolved target |
| `query_arxml_path` | where an element is, in the file | resolve an ambiguous short name to the first candidate |
| `diff_arxml_versions` | which elements were added, removed or changed | turn a wording change into a structural change |
| `trace_communication_path` | how a signal travels through the documented connectors | invent a path that no connector supports |
| `analyze_change_impact` | which elements and dependents a change affects | guess a dependency that is not in the file |

Every result carries the artifact id, the file path and the line numbers it
observed. A miss names the artifact, the path and the scope that were searched.

---

## 4. The typed graph store

`src/graph/store.py` defines the `GraphStore` protocol and a local SQLite
implementation:

* **Closed vocabulary.** 32 node types and 26 relations. An unknown type or
  relation is **rejected at write time** (`UnknownTypeError`,
  `UnknownRelationError`) rather than stored and hoped for.
* **Mandatory provenance.** Every edge carries `artifact_version_id`,
  `source_location_id`, `extraction_method`, `confidence`, `is_inferred` and
  `lifecycle_state`. An inferred edge can never satisfy `VERIFIED`
  (ADR-0001).
* **Deterministic traversal.** `neighbors` and `paths` are breadth-first with a
  stable order, so the same graph always produces the same answer.
* **Replaceable backend.** The protocol is the dependency; FalkorDB is the
  production adapter (ADR-0011). The local SQLite store is the development
  default.

---

## 5. The persistent ARXML runtime

`src/ingestion/arxml/runtime.py` stores each parsed topology under
`data/canonical/arxml/<artifact_id>.json` and re-hydrates it with
`ArxmlTopology.model_validate`. The previous behaviour — an in-memory dict in
the API module — lost every uploaded document on restart.

---

## 6. API changes (additive only)

| Route | Purpose |
|---|---|
| `GET /api/v2/arxml/tools` | the deterministic tool catalogue |
| `GET /api/v2/arxml/artifacts` | the registered ARXML artifacts |
| `GET /api/v2/arxml/{artifact_id}/validate` | the validation result |
| `GET /api/v2/arxml/{artifact_id}/references` | resolved and unresolved references |
| `GET /api/v2/arxml/{artifact_id}/path?path=&kind=` | look an element up |
| `GET /api/v2/arxml/{artifact_id}/communication?source=&target=` | trace a path |
| `GET /api/v2/arxml/{artifact_id}/tree` | the component tree for the Explorer |
| `POST /api/v2/arxml/diff` | diff two artifacts |
| `POST /api/v2/arxml/impact` | change impact between two artifacts |
| `POST /api/v2/arxml/upload` | parse, validate, persist, register |

The 47 v1 routes, the Phase-2 v2 registry/jobs routes and the Phase-3 v2
ingest/citation routes are unchanged. The API now exposes **78** routes.

---

## 7. The ARXML Explorer

`frontend/components/shell/ArxmlExplorer.tsx` replaces the legacy ARXML pane in
the workspace navigation. It shows the artifact picker, the deterministic tool
catalogue, the validation findings with their lines, the reference resolution
and the component tree — and it says *"no element matches … in this artifact"*
instead of showing an empty tree when a lookup misses.

---

## 8. Migration and rollback

* **No data-model change.** The ARXML runtime writes new files under
  `data/canonical/arxml/`; the registry and the canonical store are untouched.
* **Rollback:** `git revert <phase-4-sha>`. The uploaded files stay on disk and
  are simply ignored by the older code.
* The legacy `/api/arxml/*` routes keep working; the new v2 routes sit beside
  them.

---

## 9. Changed files

**New**
* `src/ingestion/arxml/xml_reader.py`, `src/ingestion/arxml/validation.py`,
  `src/ingestion/arxml/tools.py`, `src/ingestion/arxml/runtime.py`
* `src/graph/store.py`, `src/graph/__init__.py`
* `frontend/components/shell/ArxmlExplorer.tsx`
* `tests/unit/test_arxml_parser.py`, `tests/unit/test_arxml_validation.py`,
  `tests/unit/test_arxml_tools.py`, `tests/unit/test_graph_store.py`,
  `tests/integration/test_v2_arxml_api.py`

**Modified**
* `src/ingestion/arxml/parser.py`, `src/ingestion/arxml/models.py`
* `apps/api/main.py`, `frontend/lib/api.ts`, `frontend/lib/types.ts`,
  `frontend/components/shell/WorkspaceShell.tsx`, `README.md`

---

## 10. Risks that remain

* The ARXML graph is not yet written to the graph store; the tools answer from
  the parsed document. The store is exercised by tests only.
* The `validate_arxml` result is not yet an `EvidenceClaim`, so a validation
  finding cannot yet be cited in an answer.
* The parser recognises a fixed set of AUTOSAR element types. An element it
  does not know is ignored — silently. It should become a finding.
* The upload route registers the artifact in the registry, but a registry
  failure is reported rather than raised, so an upload can succeed without
  provenance.

---

## 11. Unresolved decisions

* Should an unknown AUTOSAR element be a warning or an error in the validator?
* Should the ARXML topology be projected into the graph store at upload time,
  or lazily on the first traversal?
* Does the tenant filter belong in the v2 ARXML routes, and should a
  non-matching tenant be a 404 or a 403?
