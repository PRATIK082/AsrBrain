"use client";
import type { EvidenceDrawerTarget } from "../../lib/types";

interface Props {
  target: EvidenceDrawerTarget | null;
  onClose: () => void;
}

function basename(path: string): string {
  const parts = (path || "").split(/[\\/]/);
  return parts[parts.length - 1] || path || "unknown source";
}

/**
 * The evidence drawer: opens at the exact source location of a citation.
 * It shows what was cited and what was not — never a paraphrase of the source.
 */
export function EvidenceDrawer({ target, onClose }: Props) {
  if (!target) return null;
  return (
    <aside
      aria-label="Evidence"
      className="drawer absolute inset-y-0 right-0 z-30 w-[min(440px,92vw)] shadow-lift"
    >
      <div className="drawer-header">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-fg">
            <span className="badge badge-accent mr-2">{target.label}</span>
            {basename(target.source_pdf)}
          </p>
          <p className="truncate text-2xs text-faint" title={target.source_pdf}>
            {target.source_pdf}
          </p>
        </div>
        <button type="button" className="btn-icon" onClick={onClose} aria-label="Close evidence">
          ✕
        </button>
      </div>

      <div className="drawer-body space-y-4">
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-2xs">
          <dt className="text-faint">pages</dt>
          <dd className="font-mono text-fg">
            {target.page ?? "—"}
            {target.page_end && target.page_end !== target.page
              ? `–${target.page_end}`
              : ""}
          </dd>
          <dt className="text-faint">section</dt>
          <dd className="text-fg">{target.section || "—"}</dd>
          <dt className="text-faint">release</dt>
          <dd className="text-fg">{target.release || "unknown"}</dd>
          <dt className="text-faint">platform</dt>
          <dd className="text-fg">{target.platform || "unknown"}</dd>
          <dt className="text-faint">module</dt>
          <dd className="text-fg">{target.module || "unassigned"}</dd>
          <dt className="text-faint">chunk id</dt>
          <dd className="break-all font-mono text-fg">{target.source_id || "—"}</dd>
          <dt className="text-faint">relevance</dt>
          <dd className="font-mono text-fg">
            {typeof target.relevance === "number" ? target.relevance.toFixed(3) : "—"}
          </dd>
        </dl>

        {target.requirement_ids.length > 0 && (
          <div>
            <p className="mb-1 text-2xs uppercase tracking-wide text-faint">requirement ids</p>
            <div className="flex flex-wrap gap-1">
              {target.requirement_ids.map((r) => (
                <span key={r} className="badge badge-accent">
                  {r}
                </span>
              ))}
            </div>
          </div>
        )}

        <div>
          <p className="mb-1 text-2xs uppercase tracking-wide text-faint">cited passage</p>
          <pre className="scrollbar-thin max-h-72 overflow-y-auto whitespace-pre-wrap rounded border border-edge/70 bg-ink-950/60 p-3 font-mono text-2xs leading-relaxed text-fg">
            {target.snippet || "no passage text was stored for this citation"}
          </pre>
        </div>

        <p className="text-2xs text-faint">
          The passage above is the indexed text of the cited location. A page preview of the
          source PDF is available from the Sources API.
        </p>
      </div>
    </aside>
  );
}
