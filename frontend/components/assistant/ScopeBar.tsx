"use client";
import { useEffect, useState } from "react";
import type { ScopeState } from "../../hooks/useAssistant";
import type { AssistantCapabilities, ChatMode } from "../../lib/types";

interface Props {
  capabilities: AssistantCapabilities | null;
  scope: ScopeState;
  onScope: (next: ScopeState) => void;
  surface: string;
  onSurface: (surface: string) => void;
  surfaces: { id: string; title: string; description: string }[];
  showKnowledge?: boolean;
  onToggleKnowledge?: () => void;
}

const MODES: { id: ChatMode; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "exact_lookup", label: "Exact lookup" },
  { id: "comparison", label: "Comparison" },
  { id: "troubleshooting", label: "Troubleshooting" },
  { id: "deep_explanation", label: "Deep explanation" },
];

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState("dark");
  useEffect(() => {
    const current = document.documentElement.getAttribute("data-theme") ?? "dark";
    setTheme(current);
  }, []);
  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    try {
      localStorage.setItem("asrbrain-theme", next);
    } catch {
      /* private mode */
    }
    setTheme(next);
  }
  return [theme, toggle];
}

/**
 * Top bar: surface switch, retrieval mode, model provider, corpus scope and
 * the theme switch. Everything shown here maps 1:1 to a backend request field,
 * so the user can always see what shaped the answer.
 */
export function ScopeBar({
  capabilities,
  scope,
  onScope,
  surface,
  onSurface,
  surfaces,
  showKnowledge,
  onToggleKnowledge,
}: Props) {
  const [theme, toggleTheme] = useTheme();
  const corpus = capabilities?.corpus;

  function toggleIn(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-edge/60 bg-ink-850/70 px-4 py-2 backdrop-blur">
      {surface === "assistant" && (
        <>
          <label className="flex items-center gap-1.5 text-xs text-muted">
            <span className="hidden sm:inline">Mode</span>
            <select
              className="select"
              value={scope.mode}
              onChange={(e) => onScope({ ...scope, mode: e.target.value as ChatMode })}
              title="Retrieval strategy"
            >
              {MODES.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex items-center gap-1.5 text-xs text-muted">
            <span className="hidden sm:inline">Model</span>
            <select
              className="select"
              value={scope.provider}
              onChange={(e) =>
                onScope({ ...scope, provider: e.target.value as "ollama" | "openai_compat" })
              }
              title="Local model provider. When the model is unavailable the assistant falls back to a deterministic extractive answer."
            >
              <option value="ollama">ollama (local)</option>
              <option value="openai_compat">openai-compatible</option>
            </select>
          </label>

          {corpus && corpus.releases.length > 0 && (
            <div className="flex items-center gap-1">
              {corpus.releases.map((r) => (
                <button
                  key={r}
                  className={`chip ${scope.releases.includes(r) ? "chip-active" : ""}`}
                  onClick={() => onScope({ ...scope, releases: toggleIn(scope.releases, r) })}
                  title={`Restrict retrieval to ${r}`}
                >
                  {r}
                </button>
              ))}
            </div>
          )}

          {corpus && corpus.modules.length > 0 && (
            <div className="flex items-center gap-1">
              {corpus.modules.map((m) => (
                <button
                  key={m}
                  className={`chip ${scope.modules.includes(m) ? "chip-active" : ""}`}
                  onClick={() => onScope({ ...scope, modules: toggleIn(scope.modules, m) })}
                  title={`Restrict retrieval to ${m}`}
                >
                  {m}
                </button>
              ))}
            </div>
          )}

          {(scope.releases.length > 0 || scope.modules.length > 0) && (
            <button
              className="btn btn-ghost btn-xs"
              onClick={() => onScope({ ...scope, releases: [], modules: [], platforms: [] })}
            >
              Clear scope
            </button>
          )}
        </>
      )}

      <div className="flex-1" />

      {surface !== "assistant" &&
        surfaces.map((s) => (
          <button
            key={s.id}
            className={`chip ${surface === s.id ? "chip-active" : ""}`}
            onClick={() => onSurface(s.id)}
            title={s.description}
          >
            {s.title}
          </button>
        ))}

      {capabilities && (
        <span
          className={`badge ${capabilities.ready ? "badge-good" : "badge-warn"}`}
          title={`${corpus?.chunks ?? 0} chunks · ${corpus?.requirements ?? 0} requirements · ${corpus?.apis ?? 0} APIs · ${corpus?.documents ?? 0} documents`}
        >
          {capabilities.ready
            ? `${corpus?.chunks ?? 0} chunks · ${corpus?.requirements ?? 0} req`
            : "corpus offline"}
        </span>
      )}

      {onToggleKnowledge && (
        <button
          className="btn btn-ghost btn-icon"
          onClick={onToggleKnowledge}
          title={showKnowledge ? "Hide the knowledge panel" : "Show the knowledge panel"}
        >
          {showKnowledge ? "◨" : "◧"}
        </button>
      )}

      <button className="btn btn-ghost btn-icon" onClick={toggleTheme} title="Toggle theme">
        {theme === "dark" ? "☾" : "☀"}
      </button>
    </header>
  );
}
