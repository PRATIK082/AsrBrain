# ADR-0001 — Evidence-first answers with four answerability gates

- **Status:** accepted
- **Date:** 2026-10-21
- **Deciders:** product owner, staff engineers
- **Relates to:** `docs/architecture/target-architecture.md` §1.1, §5.4

## Context

The current platform returns a `confidence` float (0.0–1.0) and a `level`
(`Low`/`Medium`/`High`) computed in `src/generation/verification.py::confidence_score`.
That number is a weighted heuristic over retrieval score, evidence count and a
verifier ratio. It is not interpretable, it is not comparable across questions, and a
user cannot act on "confidence 0.62". Worse, it is easy to present as a correctness
probability, which for a safety-relevant engineering tool is misleading.

Meanwhile, the product requirement is explicit: the assistant must not behave like a
generic chatbot, and must never claim 95–100 % correctness.

## Decision

Replace the confidence float as the *user-facing* contract with four discrete,
deterministically computed **answerability statuses**:

| Status | Rule |
|---|---|
| `VERIFIED` | A deterministic tool produced a result, and the cited authoritative source agrees with it. |
| `EVIDENCE_SUPPORTED` | Every material claim has at least one citation whose source location actually contains supporting text, and no deterministic validation applies to the claim. |
| `NEEDS_ENGINEER_REVIEW` | Any claim is partially supported, two cited sources conflict, a cited artifact version differs from the requested scope, or the claim is an interpretation/assumption. |
| `INSUFFICIENT_EVIDENCE` | No material claim has supporting evidence. The substantive answer is suppressed and replaced by a statement of exactly which artifact/metadata is missing, plus the scope that was searched. |

Rules:

1. The status is computed by deterministic code, not by the model. The model may
   *narrate* a status, never *assign* one.
2. A conflict between two sources is never silently resolved — both are cited and the
   status is downgraded to `NEEDS_ENGINEER_REVIEW`.
3. `INSUFFICIENT_EVIDENCE` is a successful response, not an error. It must name the
   missing artifact class (e.g. "no ARXML artifact version for project X, release
   R24-11") and the searched scope.
4. The numeric confidence is retained internally (it is useful for ranking and for
   the evaluation harness) but is never presented as a correctness probability.

## Consequences

**Positive**

- A user can act on the badge: green means "a tool proved it", amber means "a human
  must look", red means "the corpus cannot answer".
- The status is testable: each gate is a pure function over (claims, citations, tool
  results) and can be unit-tested with synthetic fixtures.
- The evaluation harness can measure *grounded-answer rate* and *abstention quality*
  without any notion of "95 % correct".

**Negative**

- Four states are coarser than a float; some legitimate gradations are lost.
- A `VERIFIED` verdict requires a deterministic tool to exist for the claim type. For
  pure prose questions there is no tool, so `EVIDENCE_SUPPORTED` is the ceiling until
  one is added.
- Existing clients that read `confidence`/`level` keep working — the new field is
  additive — but the UI must be updated to show the badge.

**Rejected alternatives**

- *Keep the float, add a tooltip* — still reads as a probability; not actionable.
- *Let the model self-report the status* — unauditable and prompt-dependent.
- *Only two states (supported / not supported)* — loses the "partial or conflicting"
  case, which is exactly where an AUTOSAR engineer needs to be warned.
