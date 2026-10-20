"use client";
import { useState } from "react";
import type { AssistantCapabilities, ProjectOverview } from "../../lib/types";

interface Props {
  capabilities: AssistantCapabilities | null;
  overview: ProjectOverview | null;
  onAsk?: (question: string) => void;
}

function num(n: number): string {
  return n.toLocaleString();
}

/**
 * Right rail: what the assistant actually knows. The numbers come from the
 * canonical store, not from a static config, so the panel always reflects the
 * corpus that is currently indexed.
 */
export function KnowledgePanel({ capabilities, overview, onAsk }: Props) {
  const [tab, setTab] = useState<"corpus" | "flow" | "anchors">("corpus");
  const corpus = overview?.corpus ?? capabilities?.corpus ?? null;
  const flow = overview?.concept_flow ?? [];
  const anchors = overview?.entity_anchors;

  return (
    <aside className="scrollbar-thin flex w-[330px] shrink-0 flex-col overflow-y-auto border-l border-edge/60 bg-ink-850/40">
      <div className="flex border-b border-edge/60 text-xs">
        {(
          [
            ["corpus", "Corpus"],
            ["flow", "Concept flow"],
            ["anchors", "Anchors"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={`flex-1 px-3 py-2 transition-colors ${
              tab === id ? "border-b-2 border-accent text-accent" : "text-muted hover:text-fg"
            }`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "corpus" && (
        <div className="space-y-4 p-3">
          {corpus ? (
            <>
              <div className="grid grid-cols-2 gap-2">
                {(
                  [
                    ["Documents", corpus.documents],
                    ["Chunks", corpus.chunks],
                    ["Requirements", corpus.requirements],
                    ["APIs", corpus.apis],
                    ["Tables", corpus.tables],
                    ["Figures", corpus.figures],
                    ["ECUC params", corpus.ecu_parameters],
                    ["Releases", corpus.releases.length],
                  ] as const
                ).map(([label, value]) => (
                  <div key={label} className="rounded-lg border border-edge/60 bg-ink-900/50 px-2.5 py-2">
                    <p className="font-mono text-lg leading-tight text-fg">{num(Number(value))}</p>
                    <p className="text-2xs uppercase tracking-wide text-faint">{label}</p>
                  </div>
                ))}
              </div>

              {overview && overview.modules.length > 0 && (
                <div>
                  <h3 className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">
                    Modules
                  </h3>
                  <ul className="space-y-1.5">
                    {overview.modules.map((m) => (
                      <li key={m.module} className="rounded-lg border border-edge/60 bg-ink-900/50 px-2.5 py-2">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-fg">{m.module || "unassigned"}</span>
                          <span className="badge">{num(m.chunks)} chunks</span>
                        </div>
                        <p className="mt-1 font-mono text-2xs text-faint">
                          {m.requirements} requirements · {m.apis} api mentions ·{" "}
                          {m.releases.join(", ") || "no release"}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {capabilities?.guarantees?.length ? (
                <div>
                  <h3 className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">
                    Guarantees
                  </h3>
                  <ul className="space-y-1">
                    {capabilities.guarantees.map((g, i) => (
                      <li key={i} className="flex gap-1.5 text-xs leading-relaxed text-muted">
                        <span className="text-good">✓</span>
                        {g}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          ) : (
            <p className="text-xs text-faint">Corpus information is unavailable.</p>
          )}
        </div>
      )}

      {tab === "flow" && (
        <div className="space-y-2 p-3">
          <p className="text-2xs leading-relaxed text-faint">
            Module → requirement → API chains that co-occur in the indexed specification. Each row
            is one passage.
          </p>
          {flow.length === 0 && <p className="text-xs text-faint">No concept flow could be derived.</p>}
          {flow.map((f, i) => (
            <div key={`${f.chunk_id}-${i}`} className="rounded-lg border border-edge/60 bg-ink-900/50 px-2.5 py-2">
              <div className="flex flex-wrap items-center gap-1 text-2xs">
                <span className="badge badge-accent">{f.module || "—"}</span>
                <span className="font-mono text-fg/85">{f.requirement}</span>
                <span className="text-faint">→</span>
                <span className="font-mono text-fg/85">{f.api}</span>
              </div>
              <p className="mt-1 font-mono text-2xs text-faint">
                {f.source_pdf} p.{f.page}
                {f.section ? ` · ${f.section}` : ""}
                {f.release ? ` · ${f.release}` : ""}
              </p>
              {onAsk && (
                <button
                  className="btn btn-ghost btn-xs mt-1"
                  onClick={() => onAsk(`Explain the relation between ${f.requirement} and ${f.api} in ${f.module}`)}
                >
                  Ask about this
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "anchors" && (
        <div className="space-y-4 p-3">
          {anchors?.requirements?.length ? (
            <div>
              <h3 className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">
                Most referenced requirements
              </h3>
              <ul className="space-y-1">
                {anchors.requirements.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2">
                    <button
                      className="truncate font-mono text-xs text-fg/85 hover:text-accent"
                      onClick={() => onAsk?.(`What does ${a.id} require?`)}
                      title={a.id}
                    >
                      {a.id}
                    </button>
                    <span className="badge">{a.mentions}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {anchors?.apis?.length ? (
            <div>
              <h3 className="mb-1.5 text-2xs font-semibold uppercase tracking-wide text-muted">
                Most referenced APIs
              </h3>
              <ul className="space-y-1">
                {anchors.apis.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-2">
                    <button
                      className="truncate font-mono text-xs text-fg/85 hover:text-accent"
                      onClick={() => onAsk?.(`What is the contract of ${a.id}?`)}
                      title={a.id}
                    >
                      {a.id}
                    </button>
                    <span className="badge">{a.mentions}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {!anchors?.requirements?.length && !anchors?.apis?.length && (
            <p className="text-xs text-faint">No entity anchors could be derived.</p>
          )}
        </div>
      )}
    </aside>
  );
}
