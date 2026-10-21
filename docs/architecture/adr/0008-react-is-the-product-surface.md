# ADR-0008 — React is the product surface; Streamlit enters maintenance mode

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §7.4

## Context

The repository ships **two** user-facing clients over the same `/api/` contract:

| Client | Entry point | State |
|---|---|---|
| Streamlit | `apps/streamlit/app.py` (726 lines) | Legacy chat UI: `st.tabs` of chat, evidence, trace, graph, sources, ARXML, tokens; sidebar with conversations, model picker, project scope, documents. **No assistant, no triage, no knowledge panel, no module navigation.** |
| React/Next | `frontend/` | The institutional assistant built in `73a80bb`: shell, scope bar, cited thread, triage report, steps timeline, source viewer, knowledge panel, starter prompts, ARXML/diff/code workbenches. |

The product owner ran `uvicorn apps.api.main:app --port 8000` and
`streamlit run apps/streamlit/app.py` and reported **"no UI change"**. The cause is
not a bug: the new UI is in the React app, which is started with
`cd frontend && npm run dev` (or the `full` Compose profile). The Streamlit app is a
different client with a different feature set, and it was never updated.

Maintaining two clients with different capabilities is itself a defect: it produces
exactly the confusion reported, doubles the surface area for fixes, and makes the
product's capabilities depend on which command the user happened to run.

## Decision

1. **React (`frontend/`) is the product surface.** All new modules, the evidence
   drawer, the module navigation and the answerability badges land there.
2. **Streamlit is frozen in maintenance mode.** It keeps working against the
   unchanged `/api/*` contract and continues to receive security and bug fixes, but
   receives no new features. A banner in the Streamlit app points to the React
   workspace, and the README's quickstart names the React command as the primary
   path.
3. **The Compose `frontend` service is promoted** from the `full` profile to
   `standard` (and the profile list in the README is corrected), so the product is
   reachable with the default stack.
4. **A single design system** (`frontend/app/globals.css` + `tailwind.config.js`)
   is the only style source. The Tailwind/PostCSS pipeline is mandatory and
   **verified in CI** by a build that fails on a missing config — the inert-Tailwind
   bug (tailwindcss present, no config, no `globals.css`, every utility class dead)
   must not recur.
5. **The two clients never diverge on contracts.** Any API change that affects
   Streamlit is either additive or is accompanied by a Streamlit update in the same
   commit.

## Consequences

**Positive**

- One product surface; the capabilities a user sees no longer depend on the launch
  command.
- The evidence-first UX (status badge, evidence drawer, module navigation) becomes
  universally available.
- The design system is exercised by CI, so the styling cannot silently die again.

**Negative**

- Streamlit users lose new features — a visible capability regression for anyone
  who prefers the one-command start.
- The React app needs a Node toolchain, which is heavier than Streamlit.
- Both clients must be kept alive until the React app is mature enough to retire
  Streamlit.

**Rejected alternatives**

- *Update both clients in parallel* — doubles every feature; rejected for a
  small-team open-source project.
- *Delete Streamlit now* — breaks the one-command start for existing users before
  the React app covers the ARXML/diff/diagram surfaces.
- *Keep Streamlit as the product* — it cannot deliver the required evidence drawer,
  module navigation and answerability badges at reasonable effort.
