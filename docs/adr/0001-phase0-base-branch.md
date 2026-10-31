# ADR-0001 — Base branch and reuse strategy for the phased master-prompt plan

- **Status:** Accepted
- **Date:** 2026-10-21
- **Deciders:** domain expert (repository owner), engineering
- **Context:** `docs/MASTER_PROMPT.md` §0, §2 rule 1, §12

---

## Context

`docs/MASTER_PROMPT.md` states at line 3 that the plan is to start from
`feature/mermaid-pdf-diagram-rendering`, and §2 rule 1 requires that "the Mermaid + PDF diagram
rendering from the current branch" be preserved. Rule 6 requires an ADR for any decision to keep
or replace an existing component.

The repository currently holds four branches:

| Branch | Head | Delta vs `main` |
|---|---|---|
| `main` | `8191264` | — |
| `feature/mermaid-pdf-diagram-rendering` | `7b48c8b` | 133 files, +21,486 / −866 |
| `feature/agentic-graphrag-mindmap-tooling` | `b42220f` | +8,893 (46 files) |
| `feature/enterprise-ai-orchestration-phase2-phase3` | `cf543a7` | behind `main` by 6 |

The Phase 0 audit (`docs/AUDIT.md`) established that `main` contains **no** Mermaid or PDF
rendering: the only `mermaid` reference in tracked code is a prompt instruction
(`src/generation/prompts.py:9`) and its assertion (`tests/unit/test_project_sources.py:106`).
The Mermaid + PDF rendering, the Phase 2–6 work (ARXML structured parsing, the answerability gate,
the traceability matrix, a typed graph store, an audit trail) and the Tailwind wiring exist only on
`feature/mermaid-pdf-diagram-rendering`.

The repository owner instructed: *"create new branch from main and feature/mermaid is not reverted
so will create _1 as new and start"*, which was confirmed as the base for this work.

---

## Decision

1. **The new branch is `feature/mermaid-pdf-diagram-rendering_1`, created from `main` @ `8191264`.**
   The Phase 0 audit is therefore a clean audit of `main`, with no unreviewed Phase 2–6 code
   influencing the findings.
2. **The sibling branches are left intact** — nothing is deleted, reset or merged at this point.
3. **Reuse is by selective cherry-pick during the phased plan, not by wholesale merge.** The
   expected order is:
   - **First:** the Mermaid + PDF rendering and the Tailwind/PostCSS configuration
     (`feature/mermaid-pdf-diagram-rendering`), because §2 rule 1 requires the Mermaid + PDF
     capability to be preserved and §6.3/§7 require it in the answer engine and the UI.
   - **Second:** the traceability matrix and requirements/test intelligence
     (`feature/mermaid-pdf-diagram-rendering`, `7b48c8b`) and the GraphRAG store and tool framework
     (`feature/agentic-graphrag-mindmap-tooling`, `b42220f`), in Phase 4 and Phase 6, once the
     Phase 1 harness can prove they move the metrics.
   - **Not yet decided:** the answerability gate (`55fee6b`) and the remaining Phase 2–6 modules.
     They are adjudicated in Phase 5 against the §3 Accuracy Contract, using the Phase 1 harness.
4. **Every cherry-pick is measured.** A component is adopted only if it shows a metric delta or
   closes a gap on the golden set, per §2 rule 2. A cherry-pick that regresses a metric is
   re-implemented rather than kept.

---

## Consequences

**Positive**

- The Phase 0 audit measures the system the product actually ships today, uncontaminated by
  unreviewed work. Every defect in `docs/AUDIT.md` is a defect in the shipped product.
- The 21,486 lines on the sibling branch are not thrown away; they are treated as an implementation
  backlog to be validated rather than a frozen deliverable.
- The phased plan stays honest: each phase's "metric delta" is measured against a baseline that
  was recorded from the real product.

**Negative / accepted costs**

- Some Phases 2–6 work must be re-validated, and the re-integration cost is estimated at ≈ 6 days
  (`docs/EFFORT_ESTIMATE.md` §3), partly offsetting the reuse saving.
- A cherry-pick of Phase 2–6 code onto a `main`-based branch will need conflict resolution against
  `main`'s Phase 2/3 enterprise-orchestration work, which touches overlapping files
  (`src/workflows/`, `src/retrieval/`, `apps/api/main.py`).
- Two feature flags exist for the pipeline version and are currently mis-wired
  (`ASRBRAIN_PIPELINE_VERSION` vs `RAG_PIPELINE_VERSION`, `docs/AUDIT.md` D-33). A cherry-pick
  must not reintroduce a second flag name.

**Risk accepted**

- If the owner intended "start from main" to *abandon* the Phase 2–6 work rather than to
  *re-audit from a clean base*, the Phases 4, 5 and 6 estimates in `docs/EFFORT_ESTIMATE.md`
  (≈ 100 days) would need to be re-planned from scratch, and the Mermaid + PDF requirement of
  §2 rule 1 would be unmet. **This ADR is the decision record for that question and can be
  superseded by a new ADR if the intent was different.**

---

## Links

- `docs/AUDIT.md` — Phase 0 audit, §1 (branch state) and §13 (defect register)
- `docs/EFFORT_ESTIMATE.md` — §3 (reuse saving), §6 (what would change the estimate)
- `docs/RISK_REGISTER.md` — R-35
- `docs/MASTER_PROMPT.md` — §2 rule 1, §2 rule 6, §12
