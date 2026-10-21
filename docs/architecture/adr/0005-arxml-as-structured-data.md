# ADR-0005 — ARXML is structured data, not RAG text

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §7.3, and the
  `arxml_*` tool family

## Context

`src/ingestion/arxml/` currently holds four files: `models.py`, `parser.py`,
`graph_export.py`, `__init__.py`. The parser is stdlib `xml.etree.ElementTree`,
namespace-agnostic by local-name stripping. It produces typed pydantic models
(`ArxmlArtifact`, `SoftwareComponent`, `Port`, `PortInterface`, `RteConnector`,
`RunnableEntity`, `EcucParameter`) and a deterministic graph projection.

But the parser captures **no line numbers**, **no UUIDs** (the `uuid` fields are
never populated), and **no `autosar_release`** (always `None`). Several model fields
are never filled: `Port.comspec`, `RunnableEntity.events/data_accesses/
server_call_points`, `EcucParameter.value_type/reference_target`,
`RteConnector.provider_component_ref/requester_component_ref/composition_ref`.
`source_xpath` is a *synthetic* XPath-like string, not a real path. Artifacts live in
an in-memory dict and are lost on restart. There is no schema validation — the
platform can currently claim nothing about whether an ARXML file is valid.

Meanwhile ARXML files are also being fed through the generic text pipeline
(`src/ingestion/project_sources.py` → `chunks`), which is how a structural question
("which port feeds CanIf_Tx?") becomes a fuzzy text-retrieval problem with fuzzy
answers.

## Decision

Treat ARXML as a **first-class structured artifact type**:

1. **Ingestion is a dedicated path**, not the generic chunker. It produces typed
   elements (`ARXMLElement` with `uuid`, `short_name`, `qualified_path`,
   `element_type`), typed edges, and `SourceLocation` records with **line numbers**
   (via a line-aware XML reader such as `xml.sax` with a locator, or an
   `lxml`-style parser if the dependency is accepted).
2. **Schema validation is a first-class result.** `validate_arxml` returns a
   `ValidationResult` (pass/fail/warn + parser errors + schema violations) bound to
   the artifact version. Nothing may claim an ARXML file is "validated" until this
   tool has run against that exact version.
3. **The explanatory summary is indexed separately** from the structure. Structural
   facts come from the typed graph; prose explanations come from the normal text
   index and are always labelled as commentary.
4. **Six deterministic tools** form the ARXML surface:
   `validate_arxml`, `resolve_arxml_references`, `query_arxml_path`,
   `diff_arxml_versions`, `trace_communication_path`, `analyze_change_impact`.
   They run before any LLM reasoning (see [ADR-0006]).
5. **Never fabricate structure.** When a tool finds nothing, it reports the searched
   artifact, version and scope — never a plausible-looking tree.
6. Unresolved references are data, not noise: they are collected, reported and linked
   to the artifact version.

## Consequences

**Positive**

- "Which port feeds X?" becomes a deterministic, citable answer instead of a
  semantic-similarity guess.
- The ARXML Explorer can offer real reference navigation, because references are
  resolved deterministically with qualified paths.
- `diff_arxml_versions` can be correct: the current
  `diff_arxml_topologies()` only diffs components/ports/interfaces and does not cover
  connectors, runnables or ECUC parameters, despite its docstring.
- Artifacts survive restarts and can be compared version-to-version.

**Negative**

- A dedicated XML path with line numbers is real work; it is Phase 4, not a patch.
- Schema validation needs the AUTOSAR schema, which is not redistributable — the
  tool must degrade to structural + well-formedness validation and say so, without
  ever reporting a false "valid".
- Two representations of the same file (typed graph + text index) must be kept
  consistent; a version mismatch between them is a reportable condition.

**Rejected alternatives**

- *Keep ARXML only as text chunks* — the current behaviour; loses every structural
  guarantee.
- *Adopt a heavyweight AUTOSAR toolchain* — licensing and size are disproportionate
  for an open-source project, and the structural needs here are modest.
- *Trust an external ARXML parser service* — breaks local-first and adds a network
  dependency to the core path.
