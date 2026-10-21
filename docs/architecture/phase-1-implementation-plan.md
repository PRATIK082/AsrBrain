# Phase 1 — Design System + Workspace Shell (implementation plan)

> Parent: `docs/architecture/target-architecture.md` · Discovery: `docs/architecture/current-state.md`
> Scope of this phase: the React application becomes the product shell. **No answer-quality
> change, no data-model change, no breaking API change.**
> Branch: `feature/mermaid-pdf-diagram-rendering`

---

## 1. What Phase 1 delivers

1. A **workspace shell**: persistent left navigation with a workspace/project selector and
   the nine product modules, a compact engineering-chat centre, and a right-hand
   **evidence drawer** that opens a citation at its exact source location.
2. The **answerability contract in the UI**: every assistant answer carries one of
   `VERIFIED · EVIDENCE_SUPPORTED · NEEDS_ENGINEER_REVIEW · INSUFFICIENT_EVIDENCE`
   instead of a correctness percentage, and is decomposed into explicit sections
   (answer, evidence, reasoning summary, assumptions, tool results, exclusions, audit).
3. **A CI workflow** that runs pytest, `tsc --noEmit` and `next build` — so the inert
   Tailwind pipeline (TD: it shipped once already) and any type break cannot land again.
4. Honest, actionable **empty states** for the modules whose backend does not exist yet
   (Requirements, Tests, Graph, Evaluation, Administration). No fake data, no fake
   progress, no silent failures.

**Explicitly not in Phase 1:** registry DB, migrations, ARXML parser rework, tool-first
executor, real answerability computation, requirements/test ingestion, PDF Evidence
Package, policy routing. Those are Phases 2–8 and each has its own ADR.

## 2. Why a shell first

The current product has two UIs (TD-16): a 726-line Streamlit chat app and a React app
that was only recently rebuilt. The user ran `streamlit run apps/streamlit/app.py` and
saw "no UI change" — correct, because the new surface lives in `frontend/` and needs
`cd frontend && npm run dev`. ADR-0008 fixes React as the product surface and freezes
Streamlit in maintenance mode. The shell makes that decision visible: the left nav is
the product's identity, and every module it lists is either working or explicitly marked
as not yet available.

## 3. File-by-file plan

### 3.1 New — types and API client

| File | Change |
|---|---|
| `frontend/lib/types.ts` | add `AnswerabilityStatus` (`"VERIFIED" \| "EVIDENCE_SUPPORTED" \| "NEEDS_ENGINEER_REVIEW" \| "INSUFFICIENT_EVIDENCE"`), `Answerability` object (`status`, `reason`, `missing`, `conflicts`, `checked`), `EvidenceDrawerTarget`, `WorkspaceModule` (id, title, href, status, description), `AnswerSection` union. Extend `AssistantTurn` with `answerability?: Answerability`. |
| `frontend/lib/api.ts` | `listModules()` → `GET /api/v2/modules` (new, additive). `getAnswerability(conversationId, messageIndex)` → `GET /api/v2/answerability/{cid}/{idx}` (new, additive, returns 501 until Phase 5 — the UI must handle "not implemented" as `NEEDS_ENGINEER_REVIEW`, never as success). |

### 3.2 New — design system additions

| File | Change |
|---|---|
| `frontend/app/globals.css` | add `.nav-item`, `.nav-item-active`, `.drawer`, `.drawer-header`, `.section-toggle`, `.answer-section`, `.empty-state`, `.empty-state-cta`, `.kbd-hint`, `.evidence-ref` (a clickable inline citation chip), and `.status-verified/.status-supported/.status-review/.status-insufficient` colour tokens. |
| `frontend/tailwind.config.js` | extend `colors` with `status` scale; add `text-2xs` (already there) and `z` tokens; keep the existing keyframes. |

### 3.3 New — shell components (`frontend/components/shell/`)

| File | Purpose |
|---|---|
| `WorkspaceShell.tsx` | root layout: `ModuleNav` (left, 248px) + `main` + `EvidenceDrawer` (right, overlay on narrow screens). Owns the active module state, the workspace selector and the drawer target. |
| `ModuleNav.tsx` | workspace/project selector, the nine modules with status dots (available / planned / not-yet), keyboard focus ring, and the "local only" indicator. |
| `EvidenceDrawer.tsx` | right drawer: opens on a citation click, shows the exact source location (PDF page + section, ARXML qualified path, code symbol, requirement/test link) and the passage text. Close on `Esc`, focus-trapped, `aria-modal`. |
| `EmptyModule.tsx` | shared empty state for modules with no backend yet: states exactly what is missing, links to the phase that delivers it, and never shows placeholder rows. |

### 3.4 Changed — existing assistant components

| File | Change |
|---|---|
| `frontend/components/assistant/AssistantShell.tsx` | becomes the **Chat** module body. The internal `surface` switcher (assistant/arxml/diff/code) moves to the left nav; the assistant shell keeps only chat behaviour. Existing chat behaviour is preserved verbatim: streaming, conversation sidebar, scope bar, knowledge panel, composer, diagnose mode, follow-ups. |
| `frontend/components/assistant/AssistantMessage.tsx` | **replace the confidence percentage with the answerability badge**; add the section layout (answer / evidence / reasoning summary / assumptions / tool results / exclusions / audit) with collapsible sections; the `confidence` float stays available inside the collapsed "audit" section only. |
| `frontend/components/assistant/SourceViewer.tsx` | `onSelect` now opens the **evidence drawer** (not just an inline expansion); the inline expansion is kept as a secondary action. |
| `frontend/components/assistant/ScopeBar.tsx` | moves under the nav; gains the answerability legend tooltip. |
| `frontend/components/assistant/Workbench.tsx` | ARXML / Diff / Code panes become their own nav modules, unchanged in behaviour. |
| `frontend/app/page.tsx` | renders `<WorkspaceShell />`. |
| `frontend/app/layout.tsx` | metadata + skip-link + `lang`/theme bootstrap retained. |

### 3.5 New — backend (additive only)

| File | Change |
|---|---|
| `apps/api/main.py` | add `GET /api/v2/modules` (static module catalogue with `status` per module) and `GET /api/v2/answerability/{cid}/{idx}` (returns 501 + reason until Phase 5). No existing route changes shape. |
| `tests/integration/test_v2_modules_api.py` | asserts the module catalogue shape, that every module id is unique, and that the answerability endpoint answers 501 with a reason (never 200 with a fake status). |

### 3.6 New — CI

| File | Change |
|---|---|
| `.github/workflows/ci.yml` | on push/PR: `python -m pytest -q`; `npm ci && npx tsc --noEmit -p tsconfig.json && npx next build`; a **CSS assertion step** that fails if the built stylesheet does not contain the design-system classes (guards against the inert-Tailwind regression). |

## 4. Answerability in the UI (Phase 1 scope)

Phase 1 does **not** compute answerability — that is Phase 5. Phase 1 delivers the
**contract and the rendering**:

* The type exists (`AnswerabilityStatus`) and the badge exists (`StatusBadge`).
* The API returns `501 Not Implemented` until the gate is implemented.
* The UI maps `501` / "not available" to `NEEDS_ENGINEER_REVIEW` with the reason
  "answerability gate not yet computed (Phase 5)" — it never renders `VERIFIED` from a
  confidence float and never renders a bare percentage as a correctness claim.
* The badge is wired to the same four values the target architecture defines, so the
  later backend change is a pure data change.

## 5. Migration and rollback

* **Data model:** unchanged. No migration, no new table.
* **API:** purely additive. `/api/v2/*` is new; the 47 existing routes keep path, request
  shape and response keys. Rollback = `git revert <phase-1-sha>`; `/api/v2/*` disappears
  and nothing else changes.
* **Frontend:** the shell is a new component tree; the old assistant components are
  kept and re-hosted, so a revert restores the previous layout exactly.
* **Streamlit:** untouched. ADR-0008 freezes it in maintenance mode; a banner pointing
  at the React workspace may be added later, but no behaviour change is required.

## 6. Test and verification plan

| Gate | Command | Expected |
|---|---|---|
| Python | `python -m pytest -q` | 106 existing tests still green + the new v2 test module |
| Types | `npx tsc --noEmit -p tsconfig.json` | no errors |
| Build | `npx next build` | success; route `/` grows by the shell only |
| CSS | inspect `frontend/.next/static/css/*.css` | contains `.nav-item`, `.status-verified`, `.evidence-ref` (proves the pipeline is live) |
| Manual | open `/`, switch every nav module, open a citation, press `Esc` | no console errors, no placeholder data |

## 7. Risks

| Risk | Mitigation |
|---|---|
| Shell re-hosting breaks the existing chat | the assistant components are re-used, not rewritten; the 106-test suite and a manual smoke of ask/diagnose/follow-up guard it |
| "Not yet available" modules feel broken | every empty state names the missing backend and the phase that delivers it |
| Answerability shows `NEEDS_ENGINEER_REVIEW` everywhere until Phase 5 | the badge tooltip says the gate is not yet computed; Phase 1 is explicitly a shell phase |
| Tailwind pipeline breaks again | the CI CSS assertion fails the build |

## 8. Unresolved decisions (carried forward)

1. **Which UI is the product** — decided for Phase 1: React. Streamlit stays in
   maintenance mode (ADR-0008). Confirmation still wanted from the product owner.
2. **PostgreSQL vs SQLite** — Phase 2 keeps SQLite + a migration framework; Postgres
   remains an adapter decision, not a rewrite (ADR-0003).
3. **Graph database** — out of scope now; a typed graph over SQLite behind a
   `GraphStore` protocol, Neo4j/RDF later (ADR-0007).

---

# Appendix A - Phase 1 as built (outcome)

## A.1 What shipped

| Area | Delivered |
|---|---|
| Workspace shell | `frontend/components/shell/WorkspaceShell.tsx` - left module nav, module body, evidence drawer overlay, catalogue-error banner |
| Module nav | `frontend/components/shell/ModuleNav.tsx` - 10 modules split into "Workspace" and "Planned", each with a status dot |
| Evidence drawer | `frontend/components/shell/EvidenceDrawer.tsx` - opens at the exact cited location (pages, section, release, platform, module, chunk id, requirement ids, passage text) |
| Honest empty states | `frontend/components/shell/EmptyModule.tsx` - what works today, what is missing, which phase delivers it, and a jump to the assistant |
| Answerability in the UI | `frontend/components/assistant/StatusBadge.tsx` (`status-verified` / `status-supported` / `status-review` / `status-insufficient`) + `UNCOMPUTED` fallback. The confidence **percentage was removed from the answer header**; the numeric confidence now lives only inside the collapsed "Audit" section and is labelled "heuristic, not a correctness rate" |
| Answer card sections | `AssistantMessage.tsx` now renders Answer / Evidence / Reasoning summary / Assumptions / Tool results / Exclusions / Audit as collapsible sections (`AnswerSectionId`) |
| Interactive citations | inline `[E1] p.42` chips under the answer open the evidence drawer at that passage |
| Design system | `globals.css`: `.nav-item .nav-item-active .nav-group-label .drawer .drawer-header .drawer-body .answer-section .section-toggle .evidence-ref .empty-state .empty-state-cta .kbd-hint .status-verified/.status-supported/.status-review/.status-insufficient`; `tailwind.config.js`: `status.*` colour scale |
| Types / client | `lib/types.ts`: `AnswerabilityStatus`, `Answerability`, `AnswerSectionId`, `EvidenceDrawerTarget`, `ModuleStatus`, `WorkspaceModule`, `ModuleCatalogue`, `AssistantTurn.answerability?`; `lib/api.ts`: `listModules()`, `getAnswerability()`, `AnswerabilityUnavailableError` |
| Backend (additive) | `GET /api/v2/modules`; `GET /api/v2/answerability/{conversation_id}/{message_index}` -> **501** with a reason until Phase 5 |
| Tests | `tests/integration/test_v2_modules_api.py` - 5 tests: catalogue shape, never-overclaim, the nine product modules, 501-not-200 for answerability, v1 routes still healthy |
| CI | `.github/workflows/ci.yml` - `backend` (compileall + pytest), `frontend` (tsc + next build + **design-system CSS assertion**), `security` (pip-audit + secret-file scan) |

## A.2 Verification

| Gate | Result |
|---|---|
| `python -m pytest -q` | **111 passed** (106 baseline + 5 new) |
| `npx tsc --noEmit -p tsconfig.json` | clean |
| `npx next build` | success - route `/` 63.1 kB, First Load JS 151 kB |
| Built CSS (`9636887ba921be53.css`, 49 697 B) | all 13 asserted classes present: `nav-item status-verified status-supported status-review status-insufficient evidence-ref kbd-hint drawer empty-state panel btn-primary answer-section section-toggle` |

**A defect found and fixed by the CI assertion logic before it shipped:** Tailwind only
emits `@layer components` classes that are *referenced* by the content globs.
`.evidence-ref` and `.kbd-hint` were defined but unused, so they were dropped from the
built stylesheet - the exact failure mode of the original inert-Tailwind bug, one level
down. Both are now used (`AssistantMessage.tsx` citation chips, `Composer.tsx` keyboard
hints) and the assertion in CI greps for them.

## A.3 API changes (additive only)

| Route | Behaviour |
|---|---|
| `GET /api/v2/modules` | static workspace catalogue with per-module `status` (`available` / `partial` / `planned`), `capability`, `missing`, `phase` |
| `GET /api/v2/answerability/{conversation_id}/{message_index}` | `501` + `X-AsrBrain-Reason: answerability-gate-not-implemented`. Never returns a status before the gate exists |

All 47 v1 routes keep their path, request shape and response keys.

## A.4 Migration and rollback

* No data-model change. No table is created, altered or dropped.
* The API change is purely additive; no existing client is affected.
* Rollback: `git revert <phase-1-sha>`. Nothing in the data directory needs a down-migration.
* `apps/streamlit/app.py` is untouched and still works against the unchanged v1 API.

## A.5 Risks that remain

* Answerability shows `NEEDS_ENGINEER_REVIEW` for every answer until Phase 5 - the badge
  tooltip states that the gate is not yet computed, so the UI never overclaims.
* The module catalogue is duplicated in `apps/api/main.py` and in the frontend `FALLBACK`
  constant. This is deliberate (the UI must render without the API) but it can drift; it
  should move to the registry DB in Phase 2.
* The React workspace has no automated UI test yet - only the CI gates (tsc, build, CSS
  assertion). Playwright/React Testing Library comes with the Phase 1 item 1.9 and the
  Phase 2 component tests.
