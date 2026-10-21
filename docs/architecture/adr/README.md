# Architecture Decision Records

Decision records for the **AsrBrain Engineering Workspace** redesign. Each ADR states
the context, the decision, the consequences, and the alternatives that were rejected.
ADRs are immutable once accepted — a change of mind is a new ADR that supersedes an
old one.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-evidence-first-answerability-gates.md) | Evidence-first answers with four answerability gates | accepted | 2026-10-21 |
| [0002](0002-provenance-first-data-model.md) | Provenance-first data model with an artifact/version spine | accepted | 2026-10-21 |
| [0003](0003-sqlite-with-migration-framework.md) | Stay on SQLite, but introduce a migration framework now | accepted | 2026-10-21 |
| [0004](0004-typed-graph-with-provenance.md) | Typed graph with mandatory provenance; no untyped "AI relationships" | accepted | 2026-10-21 |
| [0005](0005-arxml-as-structured-data.md) | ARXML is structured data, not RAG text | accepted | 2026-10-21 |
| [0006](0006-tool-first-policy.md) | Tool-first policy: deterministic results before model reasoning | accepted | 2026-10-21 |
| [0007](0007-graph-store-interface.md) | Graph behind an interface: local SQLite now, Neo4j/RDF as an adapter | accepted | 2026-10-21 |
| [0008](0008-react-is-the-product-surface.md) | React is the product surface; Streamlit enters maintenance mode | accepted | 2026-10-21 |
| [0009](0009-local-first-model-routing.md) | Local-first model routing with a default-deny data policy | accepted | 2026-10-21 |

## Template

```markdown
# ADR-NNNN — Title

- **Status:** proposed | accepted | superseded by ADR-NNNN
- **Date:** YYYY-MM-DD
- **Relates to:** …

## Context
## Decision
## Consequences (Positive / Negative)
## Rejected alternatives
```
