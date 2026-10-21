# Phase 6 — Requirements and test intelligence (as built)

- **Branch:** `feature/mermaid-pdf-diagram-rendering`
- **Baseline:** Phase 5 (`55fee6b`) — 220 pytest passing
- **Status:** implemented

Phase 6 adds the two engineering surfaces that were still missing: **requirements
intelligence** and **test/log intelligence**, joined by a bidirectional
traceability matrix.

The wording of this phase is deliberate. A requirement that has a test case has
**evidence available for review**. It is *not* "compliant", it is *not* "ISO 26262
verified", and nothing in this code asserts a standard. A machine may *propose* a
trace link; only a human may approve it.

---

## 1. What Phase 6 delivers

1. **Requirement ingestion and normalisation** — CSV and JSON, with the many
   spellings a real requirement tool produces mapped onto one shape
   (id, title, revision, status, source, parent, verification method, module,
   release, description). Unknown columns are kept in `properties`; nothing is
   thrown away silently.
2. **Test ingestion** — JUnit XML and a generic CSV format, plus an adapter
   catalogue so another format is one adapter away.
3. **Failure clustering** — failures grouped by the *shape* of their message
   (hex blobs and digit runs normalised), so "the same bug in 40 tests" is one
   finding, not forty.
4. **Trace links with a review state** — `proposed`, `machine-extracted`,
   `reviewed`, `approved`, `rejected`. The machine proposes; a human decides.
5. **Findings** — severity, status, reproducibility, linked evidence, owner,
   affected configuration, suspected root cause and a review state.
6. **The traceability matrix** — requirement → test cases *and* test case →
   requirements, plus a coverage report, an orphan report and an impact report.
7. **Two workspace modules** — Requirements and Tests are now real screens in
   the React workspace, not empty states.

### Not in Phase 6

* XLSX import (the CSV adapter reads what an XLSX export produces; a native
  reader is Phase 7).
* CAN/log-derived test summaries.
* A link-approval screen — the review state can be set through the API, but
  there is no dedicated review UI yet.
* Requirement revision history in the UI (the `requirement_versions` table
  exists and is written by the store).

---

## 2. The data model

Migration `008_requirements_tests.sql` adds seven tables to the registry:

| Table | Holds |
|---|---|
| `requirements` | the normalised requirement (id, title, revision, status, source, parent, verification method, module, release, artifact version, review state, extra properties) |
| `requirement_versions` | one row per revision, with who changed it and why |
| `trace_links` | a link between two entities, with its **review state**, confidence, `is_inferred`, extraction method, artifact version and source location, and who reviewed it |
| `test_cases` | the test identity (suite, name, classname, file, line, parameters, tags) |
| `test_runs` | one execution (tool, CI run id, branch, commit sha, duration, summary) |
| `test_results` | one result of one test case in one run (status, duration, message, stdout, stderr) |
| `findings` | an engineering finding (severity, status, summary, linked test run/result, affected configuration, suspected root cause, owner, review state, evidence) |

The migration header says it plainly: *a machine may propose a trace link, but
only a human can approve it* — and *no table in this migration asserts
compliance; it records the evidence that is available for review*.

---

## 3. The matrix

`src/traceability/matrix.py` answers one question in both directions.

* `traceability_matrix(requirements, links, test_cases, results)` — one row
  per requirement with the test cases that touch it and the latest status of
  each; a reverse list per test case with the requirements it covers.
* `coverage_report(...)` — how many requirements have an **accepted** link, how
  many only have a proposed one, how many have none, and which requirements are
  covered by a currently failing test. The statement it returns is *"evidence
  available for review — this is not a compliance claim; a qualified human
  approves the links"*.
* `orphan_report(...)` — requirements with no link and test cases with no
  requirement. Orphans are reported *for review*; they are not automatically
  failures and they are not automatically defects.
* `impact_of_requirement(...)` — the requirement's descendants (transitively)
  plus the requirements that share a test case with it.

A link counts as **accepted** only when its review state is `reviewed` or
`approved`. A `proposed` link is visible everywhere but is never counted as
evidence.

---

## 4. Failure clustering

`cluster_failures(results)` groups failed and errored results by the *shape* of
their message: hex blobs become `<hex>` and digit runs become `<n>`. So
`"timeout after 30 ms at 0x7f3a"` and `"timeout after 40 ms at 0x91bc"` are one
cluster with a count of two, not two unrelated failures. Each cluster keeps up
to three example messages and the test-case ids involved.

---

## 5. API (additive only)

| Route | Behaviour |
|---|---|
| `GET /api/v2/traceability/adapters` | the ingestion adapters that exist today |
| `POST /api/v2/requirements/ingest` | body: `format` (`csv`/`json`), `content`, `project_id`, `artifact_version_id` → normalises and stores, returns `{ingested, requirements}` |
| `GET /api/v2/requirements` | the requirements of a project |
| `GET /api/v2/requirements/{id}` | one requirement (404 when unknown) |
| `POST /api/v2/traceability/links` | creates a link; the review state is validated against the allowed set (400 otherwise) |
| `POST /api/v2/traceability/links/{id}/review` | the human decision: set the review state, reviewer and note (404 when unknown) |
| `GET /api/v2/traceability/matrix` | the bidirectional matrix |
| `GET /api/v2/traceability/coverage` | the coverage report |
| `GET /api/v2/traceability/orphans` | the orphan report |
| `GET /api/v2/traceability/impact?requirement_id=` | the impact set of one requirement |
| `POST /api/v2/tests/ingest` | body: `format` (`junit`/`csv`), `content`, `run_id`, `suite`, `branch`, `commit_sha`, `ci_run_id` → `{run, test_cases, results}` |
| `GET /api/v2/tests/runs` | the test runs |
| `GET /api/v2/tests/results` | the results of a run |
| `GET /api/v2/tests/clusters` | the failure clusters of a run |
| `GET /api/v2/findings` | the findings |
| `POST /api/v2/findings` | records a finding |

The 47 v1 routes and the Phase-2/3/4/5 v2 routes are unchanged.

---

## 6. The workspace modules

`frontend/components/shell/TraceabilityExplorer.tsx` renders both modules from
the deterministic API:

* **Requirements** — the coverage tiles, the orphan lists, and the matrix table
  with an evidence badge that reads *"available for review"* or *"not yet
  reviewed"*.
* **Tests** — the runs, the failure clusters, the results and the findings.

The empty states name the ingest endpoints rather than showing a blank table.

Both modules moved from `planned` to `partial` in the module catalogue — in
`apps/api/main.py` and in the frontend fallback, so the two agree.

---

## 7. Migration and rollback

* **Data model:** one new migration, `008_requirements_tests.sql`. It is
  additive, portable across SQLite and PostgreSQL, and applied automatically by
  the migration runner.
* **Rollback:** `git revert <phase-6-sha>` and delete the registry file if the
  new tables are not wanted. The v1 routes never read them, so the product keeps
  working without them.
* Migrations are forward-only: to undo 008, add 009 — never edit 008.

---

## 8. Changed files

**New**
* `src/registry/migrations/008_requirements_tests.sql`
* `src/traceability/{__init__,requirements,tests,matrix,store}.py`
* `frontend/components/shell/TraceabilityExplorer.tsx`
* `tests/unit/test_traceability_{requirements,tests,matrix}.py`
* `tests/integration/test_v2_requirements_api.py`

**Modified**
* `apps/api/main.py` (the v2 traceability routes, the `uuid` import, the
  module catalogue)
* `frontend/lib/{api,types}.ts`
* `frontend/components/shell/WorkspaceShell.tsx`
* `README.md`

---

## 9. Risks that remain

* A link is only as good as the human who reviews it. The "accepted" count is
  meaningless until someone actually reviews links — the API cannot tell the
  difference between a reviewed link and a rubber stamp.
* The requirement normaliser handles the spellings it was given. A tool with
  unusual column names will land in `properties` and need a mapping.
* Failure clustering is shape-based. Two different bugs with the same message
  shape will cluster together; the examples are there so a human can split
  them.
* The test ingestion covers JUnit XML and CSV. CAN and log-derived summaries
  still have no adapter.

---

## 10. Unresolved decisions

* Should a `proposed` link be visible in the matrix by default, or only after
  a human opens it?
* Is one status per requirement enough, or should the matrix carry a status per
  link?
* Does a requirement without a test case block a release, or is it simply
  reported? (Today: reported.)
* Should the review state change be audited like an answer? The `answer_audits`
  table exists; a `link_reviews` audit does not.
