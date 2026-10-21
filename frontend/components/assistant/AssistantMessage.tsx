"use client";
import { useState, type ReactNode } from "react";
import type { AssistantTurn, Answerability, SourceEvidence } from "../../lib/types";
import { Markdown } from "./Markdown";
import { SourceViewer } from "./SourceViewer";
import { StepsTimeline } from "./StepsTimeline";
import { TriageReport } from "./TriageReport";
import { StatusBadge, UNCOMPUTED } from "./StatusBadge";

interface Props {
  turn: AssistantTurn;
  stageLabel: (stage: string) => string;
  onFollowup?: (question: string) => void;
  /** Opens the evidence drawer at the exact source location of a citation. */
  onSelectEvidence?: (evidence: SourceEvidence) => void;
}

/** One collapsible band of the answer card. */
function Section({
  id,
  title,
  count,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  count?: number;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="answer-section" data-section={id}>
      <button
        type="button"
        className="section-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true" className="text-faint">
          {open ? "▾" : "▸"}
        </span>
        <span>{title}</span>
        {count !== undefined && count > 0 && (
          <span className="badge">{count}</span>
        )}
      </button>
      {open && <div className="px-1 pb-3 pt-1">{children}</div>}
    </section>
  );
}

function answerabilityOf(turn: AssistantTurn): Answerability {
  return turn.answerability ?? UNCOMPUTED;
}

export function AssistantMessage({ turn, stageLabel, onFollowup, onSelectEvidence }: Props) {
  const [showAudit, setShowAudit] = useState(false);
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl rounded-2xl rounded-br-sm border border-edge/70 bg-ink-700/60 px-4 py-2.5 text-sm leading-relaxed text-fg">
          {turn.content}
        </div>
      </div>
    );
  }

  const answerability = answerabilityOf(turn);
  const isFallback = turn.llm === "fallback" || (!turn.llm && !turn.diagnose);
  const evidenceCount = turn.evidence.length;

  return (
    <article className="panel overflow-hidden">
      <header className="flex flex-wrap items-center gap-2 border-b border-edge/60 px-4 py-2.5">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15 text-2xs font-bold text-accent">
          AB
        </span>
        <span className="text-sm font-semibold text-fg">AsrBrain</span>
        {turn.pending ? (
          <span className="badge badge-accent">working…</span>
        ) : (
          <StatusBadge status={answerability.status} reason={answerability.reason} />
        )}
        {turn.llm && turn.llm !== "fallback" && (
          <span className="badge">{turn.llm}</span>
        )}
        {isFallback && !turn.pending && (
          <span className="badge" title="Extractive fallback — no model was used">
            extractive
          </span>
        )}
      </header>

      <div className="px-4 py-3">
        <div className="flex flex-col gap-2">
          <p className="text-xs text-muted">{answerability.reason}</p>
          {answerability.missing.length > 0 && (
            <p className="text-xs text-warn">
              Missing: {answerability.missing.join(", ")}
            </p>
          )}
          {answerability.conflicts.length > 0 && (
            <p className="text-xs text-warn">
              Conflicting evidence: {answerability.conflicts.join("; ")}
            </p>
          )}
        </div>

        <div className="mt-3">
          {turn.diagnose ? (
            <TriageReport result={turn.diagnose} />
          ) : (
            <div className="panel-flat px-4 py-3">
              {turn.content ? (
                <Markdown content={turn.content} streaming={turn.pending} />
              ) : (
                <p className="text-sm text-muted">Searching the corpus…</p>
              )}
            </div>
          )}
        </div>

        {turn.evidence.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-2xs uppercase tracking-wide text-faint">Citations</span>
            {turn.evidence.map((e) => (
              <button
                key={e.label}
                type="button"
                className="evidence-ref"
                title={`${e.source_pdf} — p.${e.page ?? "?"}${e.section ? ` · ${e.section}` : ""}`}
                onClick={() => onSelectEvidence?.(e)}
              >
                [{e.label}] p.{e.page ?? "?"}
              </button>
            ))}
          </div>
        )}

        {turn.clarify && turn.clarify.missing.length > 0 && (
          <p className="mt-2 text-xs text-warn">
            Needs more context: {turn.clarify.missing.join(", ")}
          </p>
        )}
      </div>

      <Section id="evidence" title="Evidence" count={evidenceCount} defaultOpen={evidenceCount > 0}>
        {evidenceCount > 0 ? (
          <SourceViewer
            evidence={turn.evidence}
            onSelect={(label) => {
              const hit = turn.evidence.find((e) => e.label === label);
              if (hit) onSelectEvidence?.(hit);
            }}
            emptyHint=""
          />
        ) : (
          <p className="text-xs text-muted">
            No passages were cited for this answer. Treat every statement as unverified.
          </p>
        )}
      </Section>

      <Section id="reasoning" title="Reasoning summary" count={turn.steps.length}>
        {turn.steps.length > 0 ? (
          <StepsTimeline steps={turn.steps} stageLabel={stageLabel} running={turn.pending} />
        ) : (
          <p className="text-xs text-muted">
            The retrieval steps of this turn were not recorded in the conversation store.
          </p>
        )}
      </Section>

      <Section id="assumptions" title="Assumptions">
        <p className="text-xs text-muted">
          No assumption was recorded for this answer. Only the cited passages were used.
        </p>
      </Section>

      <Section id="tools" title="Tool results">
        {turn.diagnose ? (
          <p className="text-xs text-muted">
            Deterministic triage ran over the indexed corpus: {turn.diagnose.likely_causes.length}{" "}
            cited cause(s), {turn.diagnose.checks.length} check(s),{" "}
            {turn.diagnose.fix_candidates.length} advisory fix candidate(s).
          </p>
        ) : (
          <p className="text-xs text-muted">
            No deterministic tool result was recorded for this answer.
          </p>
        )}
      </Section>

      <Section id="exclusions" title="Exclusions">
        <p className="text-xs text-muted">
          {evidenceCount === 0
            ? "Nothing was retrieved from the indexed corpus for this answer."
            : `${evidenceCount} passage(s) were retrieved and are listed under Evidence. The answer above only uses the passages it cites.`}
        </p>
      </Section>

      <Section id="audit" title="Audit">
        <button
          type="button"
          className="mb-2 text-xs text-accent hover:underline"
          onClick={() => setShowAudit((v) => !v)}
        >
          {showAudit ? "Hide" : "Show"} internal metrics
        </button>
        {showAudit && (
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-2xs text-muted">
            <dt>internal confidence</dt>
            <dd className="font-mono text-fg">
              {turn.confidence !== undefined ? turn.confidence.toFixed(3) : "—"}
              <span className="ml-1 text-faint">(heuristic, not a correctness rate)</span>
            </dd>
            <dt>confidence level</dt>
            <dd className="font-mono text-fg">{turn.level || "—"}</dd>
            <dt>citation coverage</dt>
            <dd className="font-mono text-fg">
              {turn.citation_coverage !== undefined
                ? turn.citation_coverage.toFixed(3)
                : "—"}
            </dd>
            <dt>model</dt>
            <dd className="font-mono text-fg">{turn.llm || "none (extractive)"}</dd>
            <dt>checks run</dt>
            <dd className="font-mono text-fg">
              {answerability.checked.length ? answerability.checked.join(", ") : "none recorded"}
            </dd>
          </dl>
        )}
      </Section>

      {turn.followups && turn.followups.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-edge/50 px-4 py-3">
          {turn.followups.map((f, i) => (
            <button key={i} className="chip" onClick={() => onFollowup?.(f)}>
              {f}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}
