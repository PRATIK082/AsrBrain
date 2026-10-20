"use client";
import { useState } from "react";
import type { SourceEvidence } from "../../lib/types";

interface Props {
  evidence: SourceEvidence[];
  title?: string;
  emptyHint?: string;
  onSelect?: (label: string) => void;
}

function basename(p: string): string {
  if (!p) return "unknown source";
  const parts = p.split(/[\\/]/);
  return parts[parts.length - 1] || p;
}

/**
 * Source list for one answer. Every entry points at a real indexed passage —
 * the document, the page range, the section and the requirement identifiers
 * that the passage carries.
 */
export function SourceViewer({ evidence, title = "Sources", emptyHint, onSelect }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  if (!evidence || evidence.length === 0) {
    return emptyHint ? (
      <p className="rounded-lg border border-edge/60 bg-ink-900/50 px-3 py-2 text-xs text-faint">
        {emptyHint}
      </p>
    ) : null;
  }

  const shown = expanded ? evidence : evidence.slice(0, 4);

  return (
    <div className="rounded-lg border border-edge/60 bg-ink-900/50">
      <div className="flex items-center gap-2 border-b border-edge/60 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">{title}</span>
        <span className="badge">{evidence.length}</span>
      </div>
      <ul className="divide-y divide-edge/50">
        {shown.map((e) => {
          const key = `${e.label}-${e.source_id}-${e.page}`;
          const isOpen = open === key;
          return (
            <li key={key}>
              <button
                className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-ink-800/50"
                onClick={() => {
                  setOpen(isOpen ? null : key);
                  if (!isOpen && onSelect) onSelect(e.label);
                }}
              >
                <span className="badge badge-accent mt-0.5 shrink-0">{e.label || "·"}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-fg/90">
                    {basename(e.source_pdf)}
                  </span>
                  <span className="block truncate font-mono text-2xs text-faint">
                    p.{e.page}
                    {e.page_end && e.page_end !== e.page ? `–${e.page_end}` : ""}
                    {e.section ? ` · ${e.section}` : ""}
                    {e.release ? ` · ${e.release}` : ""}
                    {e.module ? ` · ${e.module}` : ""}
                  </span>
                </span>
                <span className="shrink-0 text-2xs text-faint">{isOpen ? "−" : "+"}</span>
              </button>
              {isOpen && (
                <div className="space-y-2 border-t border-edge/50 bg-ink-950/40 px-3 py-2.5">
                  <pre className="scrollbar-thin max-h-56 overflow-y-auto whitespace-pre-wrap font-mono text-2xs leading-relaxed text-muted">
                    {e.snippet || "(no text stored for this passage)"}
                  </pre>
                  <div className="flex flex-wrap gap-1">
                    {e.requirement_ids.map((r) => (
                      <span key={r} className="badge">
                        {r}
                      </span>
                    ))}
                    {e.source_id && (
                      <span className="badge" title="chunk identifier">
                        {e.source_id}
                      </span>
                    )}
                    {e.relevance > 0 && (
                      <span className="badge" title="relevance score">
                        rel {e.relevance.toFixed(2)}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {evidence.length > 4 && (
        <button
          className="w-full border-t border-edge/60 px-3 py-1.5 text-2xs text-faint hover:text-fg"
          onClick={() => setExpanded((x) => !x)}
        >
          {expanded ? "Show fewer" : `Show all ${evidence.length} sources`}
        </button>
      )}
    </div>
  );
}
