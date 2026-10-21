# ADR-0006 — Tool-first policy: deterministic results before model reasoning

- **Status:** accepted
- **Date:** 2026-10-21
- **Relates to:** `docs/architecture/target-architecture.md` §5.2, ADR-0005

## Context

The current answer path is model-centric: `run_staged()` retrieves, then calls
`generate()` (Ollama / OpenAI-compatible) and then `verify()`s the draft against the
evidence. The verifier can detect an unsupported claim, but by then the model has
already produced the structural content of the answer — including the specific
entities, relationships and values that a deterministic tool could have produced
exactly.

That is the wrong order for engineering content. A model asked "which ARXML port
feeds `CanIf_Tx`?" will produce a plausible port name with high probability, and the
verifier can only check whether that name appears in the retrieved text. It cannot
check that the port is *the* port, because the deterministic answer was never
computed.

## Decision

Invert the order for all structured questions:

1. **Intent → tool selection.** The intent router maps the question to a tool family
   (see the table in `target-architecture.md` §5.2).
2. **Deterministic tool runs first** for ARXML structure, diffs, test results,
   requirement records, code symbols, trace links and any calculation.
3. **The model's job is to explain the tool output**, never to produce it. The
   composer receives the tool result as a structured fact and may only add
   interpretation, assumption or recommendation, each labelled as such.
4. **The tool's verdict participates in the answerability status.** A tool that ran
   and agreed with the source can yield `VERIFIED`; a tool that ran and disagreed
   yields `NEEDS_ENGINEER_REVIEW`; a tool that could not run yields
   `EVIDENCE_SUPPORTED` at best and names the missing capability.
5. **Tool results are first-class output.** The UI shows the "Tool results" section
   of the answer card, so the user can see the raw deterministic result alongside the
   prose.

Free-form prose questions ("explain the Com concept flow") legitimately have no
deterministic tool; those are answered from retrieved evidence with
`EVIDENCE_SUPPORTED` as the ceiling.

## Consequences

**Positive**

- Structural answers stop being model-generated approximations.
- The tool section of the answer card is independently checkable and diffable.
- `VERIFIED` becomes reachable for a meaningful class of questions.
- Tools are pure functions over stored state, so they are cheap to test and cheap to
  re-run for a "re-verify" action.

**Negative**

- Every new intent needs tools written for it; the model alone cannot cover new
  question types.
- Tool output must be serialisable into the composer's claim structure — an
  interface constraint on tool authors.
- Latency: a tool call adds a step (in-process, so usually milliseconds).

**Rejected alternatives**

- *Keep the model first, verify after* — the current behaviour; verification cannot
  validate structure it never computed.
- *Model-only with better prompts* — exactly the "generic chatbot" failure mode the
  product must avoid.
- *Deterministic-only, no model* — loses the explanatory value that makes the tool
  usable for learning; the model narrates, the tool decides.
