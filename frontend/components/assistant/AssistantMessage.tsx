"use client";
import type { AssistantTurn } from "../../lib/types";
import { Markdown } from "./Markdown";
import { SourceViewer } from "./SourceViewer";
import { StepsTimeline } from "./StepsTimeline";
import { TriageReport } from "./TriageReport";

interface Props {
  turn: AssistantTurn;
  stageLabel: (stage: string) => string;
  onFollowup?: (question: string) => void;
  onSelectEvidence?: (label: string) => void;
}

function confidenceBadge(level?: string, confidence?: number): { cls: string; text: string } {
  const v = confidence ?? 0;
  if (level === "High" || v >= 0.75) return { cls: "badge-good", text: `confidence ${(v * 100).toFixed(0)}%` };
  if (level === "Medium" || v >= 0.45) return { cls: "badge-warn", text: `confidence ${(v * 100).toFixed(0)}%` };
  return { cls: "badge-bad", text: `confidence ${(v * 100).toFixed(0)}%` };
}

/** One conversation turn: the question, the grounded answer and its audit trail. */
export function AssistantMessage({ turn, stageLabel, onFollowup, onSelectEvidence }: Props) {
  if (turn.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-2xl rounded-2xl rounded-br-sm border border-edge/70 bg-ink-700/60 px-4 py-2.5 text-sm leading-relaxed text-fg">
          {turn.content}
        </div>
      </div>
    );
  }

  const badge = confidenceBadge(turn.level, turn.confidence);
  const isFallback = turn.llm === "fallback" || (!turn.llm && !turn.diagnose);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/15 text-2xs font-bold text-accent">
          AB
        </span>
        <span className="text-sm font-semibold text-fg">AsrBrain</span>
        {turn.pending ? (
          <span className="badge badge-accent">working…</span>
        ) : (
          <span className={`badge ${badge.cls}`}>{badge.text}</span>
        )}
        {turn.level && <span className="badge">{turn.level} confidence</span>}
        {turn.llm && turn.llm !== "fallback" && (
          <span className="badge" title="Model that phrased the answer">
            {turn.llm}
          </span>
        )}
        {isFallback && !turn.pending && (
          <span className="badge" title="No model was needed — the answer is the extracted evidence itself.">
            extractive
          </span>
        )}
        {turn.citation_coverage !== undefined && turn.citation_coverage > 0 && (
          <span className="badge" title="Share of sentences that carry a citation">
            citations {(turn.citation_coverage * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {turn.diagnose ? (
        <TriageReport result={turn.diagnose} />
      ) : (
        <div className="panel-flat px-4 py-3">
          {turn.content ? (
            <Markdown content={turn.content} streaming={turn.pending} />
          ) : (
            <div className="flex items-center gap-2 text-sm text-faint">
              <span className="h-2 w-2 animate-pulse-dot rounded-full bg-accent" />
              Searching the corpus…
            </div>
          )}
        </div>
      )}

      {turn.clarify && turn.clarify.missing.length > 0 && (
        <p className="text-xs text-warn">
          Needs more context: {turn.clarify.missing.join(", ")}
        </p>
      )}

      {turn.steps.length > 0 && (
        <StepsTimeline steps={turn.steps} stageLabel={stageLabel} running={turn.pending} />
      )}

      {turn.evidence.length > 0 && (
        <SourceViewer
          evidence={turn.evidence}
          onSelect={onSelectEvidence}
          emptyHint=""
        />
      )}

      {turn.followups && turn.followups.length > 0 && onFollowup && (
        <div className="flex flex-wrap gap-1.5">
          {turn.followups.map((f, i) => (
            <button key={i} className="chip" onClick={() => onFollowup(f)}>
              {f}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
