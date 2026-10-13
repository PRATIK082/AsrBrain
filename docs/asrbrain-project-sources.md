# Project sources — link local folders / Git links (UI-visible)

Covers the reported gap: no visible ARXML/config loader, no C/C++/Python
project linking, chat abstaining on project questions.

## Where (Streamlit — the served UI)

- Sidebar → **Project scope**: scope type (project / oem / open_program /
  customer / customer_project / generic) + scope name + tenant + project.
- Sidebar → **Documents**: upload ARXML / config / code files → "Link + index".
- Tab **Project Sources**: form for **local PC folder/file** (`C:\work\ecu`)
  or **server Git link** (`https://git.company.com/ecu.git`) → Link + index;
  list with Re-index buttons.
- Tab **ARXML & Code**: deterministic topology preview per linked ARXML
  (SWCs, connectors, unresolved refs).
- Tab **Token Config**: edits `config/generation.yaml` in place.

Same operations exist on the API for the React studio:
`GET /api/sources`, `POST /api/sources/register`,
`POST /api/sources/{id}/reindex`, `GET /api/config/tokens`.

## Grounding (why chat answers now)

Before, project chunks were dropped by the metadata hard filter whenever the
query plan named a spec release/module. Now (`metadata_filter.py`) chunks with
`document_type in (code, arxml, config, diagram)` or `chunk_id ps-*` bypass the
release/platform filter — they are scoped at link time, not by spec version.
The system prompt only says "no diagram available" when no project/ARXML
evidence exists at all; otherwise it generates a cited mermaid flowchart.

## Token caps (`config/generation.yaml`)

```yaml
response_presets: {concise: 400, standard: 600, detailed: 1200}
num_ctx: 8192
evidence_depths: {eco: 4, balanced: 8, deep: 12}
```

Sidebar presets + `LLM_NUM_PREDICT` (env wins) read these values.
