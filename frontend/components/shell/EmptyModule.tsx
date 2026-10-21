"use client";
import type { WorkspaceModule } from "../../lib/types";

interface Props {
  module: WorkspaceModule;
  onNavigate?: (id: string) => void;
}

/**
 * An honest empty state.
 *
 * A module that is not built yet says so, says what exists today and which
 * phase delivers it — instead of faking a working screen.
 */
export function EmptyModule({ module, onNavigate }: Props) {
  return (
    <div className="flex h-full items-center justify-center overflow-y-auto px-6 py-10">
      <div className="empty-state w-full max-w-xl">
        <span
          className={
            module.status === "planned" ? "status-insufficient" : "status-review"
          }
        >
          {module.status === "planned" ? "planned" : "partial"}
        </span>
        <h2 className="text-base font-semibold text-fg">{module.title}</h2>
        <p className="max-w-md text-sm text-muted">{module.description}</p>

        <div className="w-full max-w-md space-y-2 text-left text-xs">
          <div className="rounded border border-edge/70 bg-ink-850/60 px-3 py-2">
            <p className="text-2xs uppercase tracking-wide text-faint">available today</p>
            <p className="mt-0.5 text-muted">{module.capability}</p>
          </div>
          {module.missing && (
            <div className="rounded border border-warn/30 bg-warn/5 px-3 py-2">
              <p className="text-2xs uppercase tracking-wide text-warn">not available yet</p>
              <p className="mt-0.5 text-muted">{module.missing}</p>
            </div>
          )}
          <div className="rounded border border-edge/70 bg-ink-850/60 px-3 py-2">
            <p className="text-2xs uppercase tracking-wide text-faint">delivery</p>
            <p className="mt-0.5 text-muted">{module.phase}</p>
          </div>
        </div>

        {module.status !== "planned" && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => onNavigate?.("chat")}
          >
            Ask the assistant
          </button>
        )}
      </div>
    </div>
  );
}
