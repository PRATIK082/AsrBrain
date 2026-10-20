"use client";
import { useMemo, useState } from "react";
import type { ConversationSummary } from "../../hooks/useAssistant";

interface Props {
  conversations: ConversationSummary[];
  activeId: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRename: (id: string, title: string) => void;
  surface: string;
  surfaces: { id: string; title: string; description: string }[];
  onSurface: (id: string) => void;
}

function when(ts?: number): string {
  if (!ts) return "";
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Left rail: product switcher, new conversation and the stored threads. */
export function ConversationSidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
  onRename,
  surface,
  surfaces,
  onSurface,
}: Props) {
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, query]);

  return (
    <aside className="flex w-[268px] shrink-0 flex-col border-r border-edge/60 bg-ink-850/40">
      <div className="flex items-center gap-2 border-b border-edge/60 px-3 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/15 text-sm font-bold text-accent">
          AB
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-fg">AsrBrain</p>
          <p className="truncate text-2xs uppercase tracking-wide text-faint">
            Institutional AUTOSAR knowledge
          </p>
        </div>
      </div>

      <div className="space-y-1 border-b border-edge/60 p-2">
        {surfaces.map((s) => (
          <button
            key={s.id}
            onClick={() => onSurface(s.id)}
            title={s.description}
            className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors ${
              surface === s.id
                ? "bg-accent/10 text-accent"
                : "text-muted hover:bg-ink-800/70 hover:text-fg"
            }`}
          >
            <span className="text-xs opacity-70">{s.id === "assistant" ? "◆" : "◇"}</span>
            <span className="truncate">{s.title}</span>
          </button>
        ))}
      </div>

      {surface === "assistant" && (
        <>
          <div className="space-y-2 p-2">
            <button className="btn btn-primary w-full" onClick={onNew}>
              <span>＋</span> New conversation
            </button>
            <input
              className="input"
              placeholder="Search conversations…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>

          <div className="scrollbar-thin flex-1 overflow-y-auto px-2 pb-2">
            {filtered.length === 0 && (
              <p className="px-2 py-6 text-center text-xs text-faint">
                No conversations yet. Ask a question to start one.
              </p>
            )}
            <ul className="space-y-0.5">
              {filtered.map((c) => (
                <li key={c.id}>
                  <div
                    className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 transition-colors ${
                      c.id === activeId ? "bg-ink-700/80" : "hover:bg-ink-800/60"
                    }`}
                  >
                    {editing === c.id ? (
                      <input
                        className="input px-1.5 py-1 text-xs"
                        defaultValue={c.title}
                        autoFocus
                        onBlur={(e) => {
                          const v = e.target.value.trim();
                          if (v && v !== c.title) onRename(c.id, v);
                          setEditing("");
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") e.currentTarget.blur();
                          if (e.key === "Escape") setEditing("");
                        }}
                      />
                    ) : (
                      <button
                        className="min-w-0 flex-1 text-left"
                        onClick={() => onSelect(c.id)}
                        title={c.title}
                      >
                        <span className="block truncate text-sm text-fg/90">{c.title}</span>
                        <span className="block text-2xs text-faint">{when(c.updated_at)}</span>
                      </button>
                    )}
                    <button
                      className="btn btn-ghost btn-xs opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={() => setEditing(c.id)}
                      title="Rename"
                    >
                      ✎
                    </button>
                    <button
                      className="btn btn-ghost btn-xs opacity-0 transition-opacity group-hover:opacity-100"
                      onClick={() => onDelete(c.id)}
                      title="Delete"
                    >
                      🗑
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <p className="border-t border-edge/60 px-3 py-2 text-2xs leading-relaxed text-faint">
            Answers are grounded in the indexed AUTOSAR corpus. Model output is advisory and every
            claim carries a source. Code changes are suggestions — a human approves them.
          </p>
        </>
      )}
    </aside>
  );
}
