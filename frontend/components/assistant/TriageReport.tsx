"use client";
import { useState } from "react";
import type { DiagnoseResult, TriageFinding } from "../../lib/types";
import { Markdown } from "./Markdown";
import { SourceViewer } from "./SourceViewer";

interface Props {
  result: DiagnoseResult;
}

function FindingRow({
  f,
  kind,
  onOpen,
}: {
  f: TriageFinding;
  kind: "cause" | "fix" | "check";
  onOpen?: (label: string) => void;
}) {
  const body = kind === "fix" ? f.suggestion || f.cause : kind === "cause" ? f.cause : f.question;
  const detail = kind === "check" ? f.how : f.section ? `${f.source_pdf} p.${f.page} · ${f.section}` : f.source_pdf;
  return (
    <li className="space-y-1 rounded-lg border border-edge/60 bg-ink-900/40 px-3 py-2">
      <div className="flex items-start gap-2">
        {f.label && (
          <button
            className="badge badge-accent mt-0.5 shrink-0"
            onClick={() => onOpen?.(f.label ?? "")}
            title="Jump to the source passage"
          >
            {f.label}
          </button>
        )}
        <p className="min-w-0 flex-1 text-sm leading-relaxed text-fg/90">{body}</p>
      </div>
      {detail && <p className="font-mono text-2xs text-faint">{detail}</p>}
      {kind === "fix" && (
        <p className="text-2xs text-warn">Advisory — review and approve before applying.</p>
      )}
    </li>
  );
}

/**
 * Structured triage output: the classified symptom, the passages that state
 * the governing behaviour, the checks an engineer should run and the candidate
 * fixes. Every cause/fix links back to a numbered source.
 */
export function TriageReport({ result }: Props) {
  const [tab, setTab] = useState<"causes" | "checks" | "fixes">("causes");
  const [selected, setSelected] = useState<string | null>(null);

  const counts = {
    causes: result.likely_causes.length,
    checks: result.checks.length,
    fixes: result.fix_candidates.length,
  };

  const evidence = result.evidence ?? [];
  const shown = selected
    ? evidence.map((e, i) => ({ ...e, label: e.label || `E${i + 1}` })).filter((e) => e.label === selected)
    : evidence;

  return (
    <div className="space-y-3">
      <div className="panel-flat overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-edge/60 bg-ink-800/40 px-4 py-2.5">
          <span className="badge badge-accent">{result.category?.title ?? "Symptom"}</span>
          {result.category?.confidence !== undefined && (
            <span className="badge" title="Classifier confidence">
              class {Math.round(result.category.confidence * 100)}%
            </span>
          )}
          {result.level && <span className="badge">{result.level} confidence</span>}
          {result.llm ? (
            <span className="badge">{result.llm}</span>
          ) : (
            <span className="badge" title="Deterministic triage — no model involved">
              deterministic
            </span>
          )}
        </div>

        <div className="flex border-b border-edge/60 text-xs">
          {(
            [
              ["causes", "Likely causes", counts.causes],
              ["checks", "Checks to run", counts.checks],
              ["fixes", "Candidate fixes", counts.fixes],
            ] as const
          ).map(([id, label, n]) => (
            <button
              key={id}
              className={`px-4 py-2 transition-colors ${
                tab === id ? "border-b-2 border-accent text-accent" : "text-muted hover:text-fg"
              }`}
              onClick={() => setTab(id)}
            >
              {label} <span className="text-faint">({n})</span>
            </button>
          ))}
        </div>

        <div className="p-3">
          {tab === "causes" &&
            (result.likely_causes.length ? (
              <ul className="space-y-2">
                {result.likely_causes.map((c, i) => (
                  <FindingRow key={i} f={c} kind="cause" onOpen={setSelected} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-faint">
                No indexed passage states this behaviour explicitly. Treat the sources below as
                context, not as a confirmed cause.
              </p>
            ))}

          {tab === "checks" && (
            <ol className="space-y-2">
              {result.checks.map((c, i) => (
                <li key={i} className="rounded-lg border border-edge/60 bg-ink-900/40 px-3 py-2">
                  <p className="text-sm font-medium text-fg">{c.question}</p>
                  {c.how && <p className="mt-1 text-xs leading-relaxed text-muted">{c.how}</p>}
                  {c.source_pdf && (
                    <p className="mt-1 font-mono text-2xs text-faint">
                      {c.source_pdf}
                      {c.page ? ` p.${c.page}` : ""}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}

          {tab === "fixes" &&
            (result.fix_candidates.length ? (
              <ul className="space-y-2">
                {result.fix_candidates.map((f, i) => (
                  <FindingRow key={i} f={f} kind="fix" onOpen={setSelected} />
                ))}
              </ul>
            ) : (
              <p className="text-sm text-faint">
                No normative passage yields a candidate fix for this symptom.
              </p>
            ))}
        </div>
      </div>

      {result.summary && (
        <details className="panel-flat px-4 py-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-muted">
            Full triage report
          </summary>
          <div className="mt-3">
            <Markdown content={result.summary} />
          </div>
        </details>
      )}

      {evidence.length > 0 && (
        <SourceViewer
          evidence={shown}
          title={selected ? `Source ${selected}` : "Evidence"}
          onSelect={(l) => setSelected((cur) => (cur === l ? null : l))}
        />
      )}
    </div>
  );
}
