# Phase 5 — Scope-first retrieval, the answerability gate and the audit trail (as built)

- **Branch:** `feature/mermaid-pdf-diagram-rendering`
- **Baseline:** Phase 4 (`9c4e5e2`) — 190 pytest passing
- **Status:** implemented

Phase 5 is where the product stops being "a chatbot with a confidence number"
and becomes an **evidence-first** assistant: the scope decides what may be
retrieved, the answerability gate decides how much the answer can be trusted,
and every answer leaves an audit record.

---

## 1. What Phase 5 delivers

1. **The answerability gate** (`src/answerability/gate.py`) — the four statuses
   are computed **by code**, never claimed by the model.
2. **Scope-first retrieval** (`src/retrieval/scope.py` + the pipeline) — the
   scope decides the plan *before* anything is scored, and every filter that
   cannot be applied is reported.
3. **The audit trail** (`src/audit/trail.py`) — one `answer_audits` row per
   answer, with the status, the scope, the citations and the model route.
4. **Real endpoints** — `GET /api/v2/answerability/{conversation_id}[/{index}]`
   and `GET /api/v2/audit/{conversation_id}` replace the 501 placeholder; the
   chat endpoints now store the status with the answer and return it.
5. **The UI shows the real status** — the SSE `complete` event carries the
   computed `answerability`, so the badge is never a guess.

### Not in Phase 5

* The graph-aware planner (the typed `GraphStore` exists, but the planner does
  not expand with it yet).
* The scope cannot yet be enforced on project/branch/ECU/vendor/tenant/source
  type/artifact version, because the canonical chunk rows do not carry those
  columns — they are reported as *unapplied* instead of being silently ignored.
* The audit trail is stored but not yet exposed as an export or a retention
  policy.

---

## 2. The answerability gate (ADR-0001)

| Status | Meaning |
|---|---|
| `VERIFIED` | a deterministic tool result and the authoritative source evidence agree |
| `EVIDENCE_SUPPORTED` | the cited sources support the answer; no deterministic validation applies |
| `NEEDS_ENGINEER_REVIEW` | partial evidence, ambiguity, a conflict, or missing context |
| `INSUFFICIENT_EVIDENCE` | the corpus does not cover the question — the result names the missing artifact and the scope that was searched |

Decision order (`evaluate_answerability`):

1. **No evidence** → `INSUFFICIENT_EVIDENCE` ("no passage in the searched scope").
2. **A conflicting or uncertain tool result** → `NEEDS_ENGINEER_REVIEW`.
3. **Nothing cited** (`citation_coverage <= 0` or `claim_support_rate <= 0`) →
   `INSUFFICIENT_EVIDENCE`.
4. **Partial support** (support rate below 1, or a sentence without a citation)
   → `NEEDS_ENGINEER_REVIEW`.
5. **Every claim cited and a confirming tool** → `VERIFIED`.
6. **Every claim cited, no tool** → `EVIDENCE_SUPPORTED`.

The result is `{status, reason, missing[], conflicts[], checked[], scope{}}`.
`reason` is always filled in; `missing` says what would lift the status;
`conflicts` says what disagrees.

**A numeric confidence is not a correctness rate** and is never used as the
user-facing contract — it stays inside the collapsed "Audit" section of the
answer card. The integration test asserts that the status is never a number
and never contains "%".

---

## 3. Scope-first retrieval

```
question ──► scope ──► plan (scope wins) ──► filters ──► scoring ──► evidence
                │                                    │
                └── report: kept / dropped / unapplied
```

* `Scope` carries `project_id, branch, ecu, vendor, tenant_id, releases,
  platforms, modules, document_types, source_types, artifact_versions,
  access_policy`.
* The scope is applied **before** scoring: a chunk that is out of scope can
  never be ranked into the answer.
* The scope also **overrides the plan** (`plan.releases`, `plan.platforms`,
  `plan.modules`, `plan.document_types`), so the plan and the filter can never
  contradict each other.
* **Nothing is dropped silently** — the report gives `kept`, `dropped` (per
  reason), `dropped_total` and `total`.
* **A filter that cannot be applied says so.** The canonical chunk rows carry
  release, platform, module and document type only. A scope that names a
  project, branch, ECU, vendor, tenant, source type or artifact version is
  reported in `unapplied`, because a filter that appears to work but does not
  is worse than no filter at all.

The scope report travels with the retrieval result under the new `scope` key;
the existing keys (`plan, rewrites, evidence, per_release, retrieval_score`)
are unchanged, so the v1 contract is intact.

---

## 4. The audit trail

Every answer writes one `answer_audits` row:

| Column | Meaning |
|---|---|
| `request_id` | a per-answer id (`req-<uuid12>`) |
| `conversation_id`, `message_id` | where the answer lives |
| `question`, `answer` | the exchange |
| `answerability_status` | the gate's verdict |
| `project_id`, `scope` | the scope the answer was allowed to use |
| `citations`, `tool_calls` | what the answer was based on |
| `model_provider`, `model_name`, `routing_reason` | how the answer was produced |
| `latency_ms` | how long it took |

Auditing is wrapped in `try/except` — a failing audit must never break an
answer.

---

## 5. API changes (additive only)

| Route | Behaviour |
|---|---|
| `GET /api/v2/answerability/{conversation_id}/{message_index}` | the status of one stored assistant turn; `404` for an unknown conversation or index |
| `GET /api/v2/answerability/{conversation_id}` | every assistant turn of a conversation (`turns[]`, `count`) |
| `GET /api/v2/audit/{conversation_id}` | the audit rows of a conversation (`audits[]`, `count`) |

`POST /api/chat` and `POST /api/chat/stream` now:

* compute `verification` (`citation_coverage`, `claim_support_rate`,
  `evidence_coverage`) from the staged run;
* compute the `answerability` with the gate;
* store `verification`, `answerability` and `scope` in the assistant message
  meta (so the status survives a reload);
* record the audit;
* return `answerability` in the response, and the SSE `complete` event carries
  it too.

The 47 v1 routes and the Phase-2/3/4 v2 routes are unchanged.

---

## 6. Migration and rollback

* **No data-model change** — the audit rows live in the registry database
  created in Phase 2 (`data/canonical/registry.db`), in the `answer_audits`
  table that already exists.
* **Rollback:** `git revert <phase-5-sha>`. The audit rows stay in the
  database (they are append-only history) and are ignored by the old code.
* The scope parameter is optional everywhere: `retrieve(query, top_k_final=0,
  scope=None)` behaves exactly as before when no scope is given.

---

## 7. Changed files

**New**
* `src/answerability/{__init__,gate}.py`
* `src/retrieval/scope.py`
* `src/audit/{__init__,trail}.py`
* `tests/unit/test_answerability_gate.py`
* `tests/unit/test_retrieval_scope.py`
* `tests/unit/test_audit_trail.py`
* `tests/integration/test_v2_answerability_api.py`
* `docs/architecture/phase-5-implementation-plan.md`

**Modified**
* `src/retrieval/pipeline.py` — the scope decides the plan before scoring; the
  result carries the scope report.
* `src/workflows/stages.py` — the scope is built from the conversation slots
  and passed to the pipeline.
* `apps/api/main.py` — the real answerability/audit endpoints; `/api/chat` and
  `/api/chat/stream` compute the status, store it and audit the answer; the
  SSE `complete` event carries it.
* `frontend/lib/types.ts` — `StreamEvent`'s complete variant carries
  `answerability`.
* `frontend/hooks/useAssistant.ts` — the turn keeps the computed status.
* `README.md` — the Phase 5 section.

---

## 8. Risks that remain

* The scope cannot be enforced on the dimensions the corpus does not carry;
  they are reported, not applied. This becomes enforceable when the ingestion
  path writes project/branch/artifact-version onto the chunks (Phase 6+).
* The gate works on the *answer text* and the *verifier* output. It cannot
  tell whether a cited passage is the right passage for a claim — that needs a
  deterministic tool result, which only the ARXML tools provide so far.
* `INSUFFICIENT_EVIDENCE` does not yet tell the user **which artifact** would
  fix it in every case; it names the scope that was searched.
* The audit trail grows without bound; retention is an open decision.

---

## 9. Unresolved decisions

* How long are audit rows kept, and may a user delete them?
* Should the answerability status be computed for the *whole* answer or per
  claim? Today it is per answer, with the claims in the verifier output.
* Does a `NEEDS_ENGINEER_REVIEW` answer block the audit record, or is the
  audit record exactly what makes the review possible?
