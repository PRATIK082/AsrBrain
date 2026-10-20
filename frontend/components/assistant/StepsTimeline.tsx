"use client";
import { useState } from "react";
import type { AssistantStep } from "../../lib/types";

interface Props {
  steps: AssistantStep[];
  stageLabel: (stage: string) => string;
  running?: boolean;
}

const STATUS_STAGES = [
  "query_understanding",
  "retrieval_planning",
  "text_retrieval",
  "table_retrieval",
  "graph_retrieval",
  "fusion_rerank",
  "expansion_compression",
  "answer_drafting",
  "citation_validation",
  "confidence",
];

/**
 * "How this answer was built" timeline. It shows the retrieval stages the
 * backend actually reported — nothing is simulated on the client.
 */
export function StepsTimeline({ steps, stageLabel, running }: Props) {
  const [open, setOpen] = useState(false);
  if (steps.length === 0) return null;

  const seen = new Set<string>();
  const stages = steps.filter((s) => {
    if (s.kind !== "status") return false;
    if (seen.has(s.stage)) return false;
    seen.add(s.stage);
    return true;
  });
  const evidenceSteps = steps.filter((s) => s.kind === "evidence");
  const errors = steps.filter((s) => s.kind === "error");
  const done = new Set(stages.map((s) => s.stage));
  const active = running ? stages[stages.length - 1]?.stage : undefined;

  return (
    <div className="rounded-lg border border-edge/60 bg-ink-900/50">
      <button
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted hover:text-fg"
        onClick={() => setOpen((o) => !o)}
      >
        <span className={`h-1.5 w-1.5 rounded-full ${running ? "animate-pulse-dot bg-accent" : "bg-good"}`} />
        <span className="font-medium text-fg/90">
          {running ? "Working…" : `${stages.length} stages · ${evidenceSteps.length} sources`}
        </span>
        <span className="flex-1" />
        <span className="text-faint">{open ? "hide" : "show"}</span>
      </button>

      {open && (
        <ol className="space-y-1.5 border-t border-edge/60 px-3 py-2.5">
          {STATUS_STAGES.map((stage) => {
            const isDone = done.has(stage);
            const isActive = active === stage;
            return (
              <li key={stage} className="flex items-start gap-2 text-xs">
                <span
                  className={`mt-1 h-1.5 w-1.5 shrink-0 rounded-full ${
                    isActive ? "animate-pulse-dot bg-accent" : isDone ? "bg-good" : "bg-edge"
                  }`}
                />
                <span className={isDone ? "text-fg/80" : "text-faint"}>{stageLabel(stage)}</span>
              </li>
            );
          })}
          {errors.map((e, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-bad">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-bad" />
              <span>{e.message}</span>
            </li>
          ))}
          {evidenceSteps.length > 0 && (
            <li className="pt-1 text-2xs uppercase tracking-wide text-faint">
              {evidenceSteps.length} passage{evidenceSteps.length === 1 ? "" : "s"} retrieved
            </li>
          )}
        </ol>
      )}
    </div>
  );
}
