# Institutional Assistant UI — implementation plan (AsrBrain)

> Branch: `feature/mermaid-pdf-diagram-rendering` · Status: implemented
> Goal: a ChatGPT / Copilot / Claude-class institutional knowledge assistant over the
> existing AUTOSAR RAG backend — one surface that explains the concept flow, surfaces
> project knowledge and helps diagnose and fix issues, with every claim cited.

---

## 1. Why this was needed

The repo already had a strong retrieval core (canonical store → hybrid index → staged
retrieval → cited answer) and three thin surfaces (Streamlit chatbox, a React skeleton,
a legacy `/query`). Three gaps blocked the "institutional assistant" experience:

| Gap | Symptom |
|---|---|
| **No project knowledge surface** | The user could not ask "what *is* this project?" — modules, releases, documents and the concept flow were invisible. |
| **No diagnostic surface** | "The frame is never transmitted" had no path to a spec statement, a check list or a fix candidate. |
| **The React UI was unstyled** | `tailwindcss` was in `devDependencies` but there was no `tailwind.config.js`, no `postcss.config.js` and no `app/globals.css`. Every utility class in the tree rendered as inert HTML. |

The first two are product gaps, the third is a build bug — the UI *looked* like it
should work because the class names were right, but nothing was ever applied.

## 2. Target experience

```
┌──────────────┬───────────────────────────────────────────────┬───────────────┐
│  Sidebar     │  Scope bar: mode · provider · release · module │  Knowledge    │
│  surfaces    ├───────────────────────────────────────────────┤  Corpus       │
│  conversation│  Thread: user turn → assistant turn           │  Concept flow │
│  search      │    answer · confidence · steps · sources       │  Anchors      │
│  rename/del  │                                               │  Guarantees   │
│              ├───────────────────────────────────────────────┤               │
│  disclaimer  │  Composer: ask | diagnose · scope hint         │               │
└──────────────┴───────────────────────────────────────────────┴───────────────┘
```

Principles, in order of priority:

1. **Cited or silent.** Every factual claim carries a document/page/section reference.
   Where the corpus does not cover the question, the assistant says so.
2. **Inspectable.** The retrieval steps and the source list are part of the answer, not
   a debug panel.
3. **Deterministic first.** Triage, project knowledge and the concept flow work with no
   model at all. A model may re-phrase; it may not invent.
4. **Advisory, not autonomous.** Code findings are suggestions; a human approves changes.
5. **Local by default.** Nothing leaves the machine unless a provider is explicitly picked.

## 3. Backend

New package `src/assistant/` — read-only, model-free, over the canonical store.

### 3.1 `src/assistant/knowledge.py`

| Function | Returns |
|---|---|
| `corpus_manifest(db)` | documents/chunks/tables/figures/requirements/apis/ECUC-parameter counts + release, platform, module, document-type facets |
| `capabilities(db)` | assistant identity, corpus manifest, 5 answer modes, 5 surfaces, 5 guarantees, `ready` flag |
| `project_overview(db)` | per-module stats, releases, documents, `concept_flow` (module → requirement → API triples with source/page/section/chunk) and `entity_anchors` (most-mentioned requirements and APIs) |
| `starter_prompts(db)` | 4 prompt groups (understand / defect / lookup / compare) templated with the *real* module and release names of the indexed corpus |

Requirement identifiers (`SWS_CanIf_00123`, `PRS_SOMEIP_00051`) are separated from API
names by `_REQ_ID = ^[A-Z][A-Za-z0-9]*_[A-Za-z0-9]+_\d+$`, because the chunker also
stores requirement IDs inside `api_names` — without the filter the API facet is noise.

`concept_flow` rows are built from co-occurrence **inside a single chunk**, so every
triple is traceable to one passage of one document.

### 3.2 `src/assistant/triage.py`

A deterministic, evidence-grounded triage of a reported symptom.

* 9 categories, each with keyword triggers and a check list:
  `signal_not_transmitted`, `timeout`, `port_connection`, `state_machine`,
  `initialisation`, `configuration`, `api_mismatch`, `diagnostic`, `general`.
* `classify(symptom)` → category, matched keywords, confidence, checks.
* `diagnose(symptom, code, module, release, spec, top_k, pipe)` →
  `category`, `likely_causes[]` (each cited), `checks[]`, `fix_candidates[]` (each cited),
  `summary` (markdown), `confidence`, `level`, `followups[]`, `evidence[]`.
* Causes are normative sentences from the retrieved passages; fix candidates are the
  prescriptive ones. An optional LLM may re-phrase the summary, but only if the
  verifier scores the rewritten claims at `claim_support_rate ≥ 0.5` — otherwise the
  deterministic summary is kept.

### 3.3 API (`apps/api/main.py`)

| Endpoint | Purpose |
|---|---|
| `GET /api/assistant/capabilities` | what the assistant knows and can do |
| `GET /api/assistant/overview` | project knowledge: modules, releases, documents, concept flow, anchors |
| `GET /api/assistant/prompts` | `{"groups": [...]}` — starter-prompt library |
| `GET /api/assistant/triage/categories` | `{"categories": [...]}` — symptom taxonomy |
| `POST /api/assistant/diagnose` | evidence-grounded triage (deterministic without a provider) |

`/api/chat` and `/api/chat/stream` now persist the per-turn `evidence` events into the
assistant message `meta`, so the source panel survives a page reload.

## 4. Frontend

### 4.1 Styling foundation (fixes the inert UI)

* `frontend/tailwind.config.js` — CommonJS, dark mode by `class` and `[data-theme]`,
  content globs over `app/ components/ hooks/ lib/ store/ stores/`, design tokens mapped
  to CSS variables (`ink`, `edge`, `fg`, `muted`, `faint`, `accent`, `accent-2`, `warn`,
  `good`, `bad`), `text-2xs`, panel/lift shadows, `fade-up` / `pulse-dot` / `shimmer`
  keyframes, `@tailwindcss/typography`.
* `frontend/postcss.config.js` — tailwindcss + autoprefixer.
* `frontend/app/globals.css` — dark/light token sets, base layer (borders, focus ring,
  selection), components layer (`.panel .btn .btn-primary .btn-ghost .btn-icon .btn-xs
  .input .select .chip .chip-active .badge .badge-good/warn/bad/accent`) and a full
  `.md` markdown scope (headings, lists, tables, code, blockquote) used by the answer
  renderer.
* `frontend/app/layout.tsx` — imports the stylesheet, sets the theme before hydration
  (inline bootstrap script reading `localStorage["asrbrain-theme"]`).

### 4.2 New modules

| File | Role |
|---|---|
| `hooks/useAssistant.ts` | session controller: conversations (server-backed), streaming, per-turn evidence, live steps, scope, diagnose, stop |
| `components/assistant/AssistantShell.tsx` | layout orchestrator + surface routing |
| `components/assistant/ConversationSidebar.tsx` | surfaces, conversation search/rename/delete, disclaimer |
| `components/assistant/ScopeBar.tsx` | mode, provider, release/module chips, corpus badge, theme + knowledge toggles |
| `components/assistant/Composer.tsx` | auto-growing composer, ask/diagnose mode, contextual hints |
| `components/assistant/AssistantMessage.tsx` | user bubble / assistant card (confidence, level, model badge, citation coverage) |
| `components/assistant/TriageReport.tsx` | causes / checks / fixes tabs, citation chips that jump to the source |
| `components/assistant/StepsTimeline.tsx` | the 10 backend stages, collapsible |
| `components/assistant/SourceViewer.tsx` | numbered sources with snippet, requirement IDs, chunk id, relevance |
| `components/assistant/KnowledgePanel.tsx` | corpus stats, concept flow, entity anchors, guarantees |
| `components/assistant/StarterPrompts.tsx` | grouped empty state |
| `components/assistant/Markdown.tsx` | react-markdown + remark-gfm, Mermaid fences, copyable code |
| `components/assistant/Workbench.tsx` | the legacy ARXML / diff / code panes, restyled |

`app/page.tsx` now renders `<AssistantShell />`.

## 5. Tests

| File | Coverage |
|---|---|
| `tests/unit/test_assistant_knowledge.py` | requirement/API separation, manifest shape, capabilities, overview, prompt library |
| `tests/unit/test_assistant_triage.py` | classification per symptom family, abstention on empty symptom and on an empty corpus, cited causes/checks/fixes, determinism, code-identifier extraction |
| `tests/integration/test_assistant_api.py` | all five assistant endpoints, the `{"groups": …}` / `{"categories": …}` envelopes, deterministic diagnose, and `meta.evidence` persistence on `/api/chat` (generator mocked — no model contact) |

Triage unit tests use a stub pipeline, so they never touch the model or the network.

## 6. Known constraints

* The triage confidence is a retrieval/evidence heuristic, not a calibrated probability.
* `code_files` in this repo is zero — the corpus has no C sources, so the code-review
  surface only exercises its advisory path until sources are uploaded.
* The React surfaces (`arxml`, `diff`, `code`, `diagrams`) are switched inside one
  shell; separate routes are a later step.
* `make` is not available on every developer machine — the Python commands in the
  README are the source of truth.
