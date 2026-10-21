"use client";
import type { ModuleCatalogue, WorkspaceModule } from "../../lib/types";

interface Props {
  catalogue: ModuleCatalogue;
  activeId: string;
  onSelect: (id: string) => void;
}

/** Modules that are reachable today are grouped above the ones still planned. */
function group(modules: WorkspaceModule[]) {
  const live = modules.filter((m) => m.status !== "planned");
  const planned = modules.filter((m) => m.status === "planned");
  return [
    { label: "Workspace", items: live },
    { label: "Planned", items: planned },
  ].filter((g) => g.items.length > 0);
}

const STATUS_DOT: Record<WorkspaceModule["status"], string> = {
  available: "bg-status-verified",
  partial: "bg-status-review",
  planned: "bg-status-insufficient",
};

export function ModuleNav({ catalogue, activeId, onSelect }: Props) {
  return (
    <nav
      aria-label="Workspace modules"
      className="flex h-full w-60 shrink-0 flex-col border-r border-edge/70 bg-ink-900"
    >
      <div className="border-b border-edge/70 px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent/15 text-2xs font-bold text-accent">
            AB
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-fg">
              {catalogue.workspace.title}
            </p>
            <p className="truncate text-2xs text-faint">{catalogue.workspace.project}</p>
          </div>
        </div>
        <p className="mt-2 truncate text-2xs text-muted" title={catalogue.workspace.scope}>
          {catalogue.workspace.scope}
        </p>
      </div>

      <div className="scrollbar-thin flex-1 overflow-y-auto px-1.5 py-1">
        {group(catalogue.modules).map((g) => (
          <div key={g.label}>
            <p className="nav-group-label">{g.label}</p>
            <ul>
              {g.items.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className={`nav-item ${m.id === activeId ? "nav-item-active" : ""}`}
                    aria-current={m.id === activeId ? "page" : undefined}
                    onClick={() => onSelect(m.id)}
                    title={m.description}
                  >
                    <span
                      aria-hidden="true"
                      className={`h-1.5 w-1.5 shrink-0 rounded-full ${STATUS_DOT[m.status]}`}
                    />
                    <span className="truncate">{m.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="border-t border-edge/70 px-3 py-2 text-2xs text-faint">
        <p>Evidence-first. Every claim cites a source.</p>
        <p className="mt-0.5">Code changes are suggestions — a human approves them.</p>
      </div>
    </nav>
  );
}
