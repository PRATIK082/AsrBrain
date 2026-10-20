"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { ToolSpec } from "../../lib/types";

/**
 * Tool catalogue — lists every registered tool with its JSON-Schema and lets
 * the operator invoke one directly (same surface the agent loop uses).
 */
export function ToolCatalogue() {
  const [tools, setTools] = useState<ToolSpec[]>([]);
  const [selected, setSelected] = useState<ToolSpec | null>(null);
  const [args, setArgs] = useState("{}");
  const [result, setResult] = useState<string>("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.tools()
      .then((r) => {
        setTools(r.tools ?? []);
        if (r.tools?.length) setSelected(r.tools[0]);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  async function invoke() {
    if (!selected) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(args || "{}");
    } catch {
      setError("Arguments must be valid JSON.");
      return;
    }
    setBusy(true);
    setError("");
    setResult("");
    try {
      const r = await api.invokeTool(selected.name, parsed, selected.mutating);
      setResult(JSON.stringify(r, null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">
          {tools.map((t) => (
            <li key={t.name}>
              <button
                className={`w-full rounded border px-2 py-1 text-left ${
                  selected?.name === t.name
                    ? "border-[#00F5FF]/60 bg-[#0D1320]"
                    : "border-transparent hover:border-[#222D3F]"
                }`}
                onClick={() => { setSelected(t); setResult(""); }}
              >
                <span className="font-mono text-[#00F5FF]">{t.name}</span>
                {t.mutating && <span className="ml-2 text-[11px] text-[#F59E0B]">mutating</span>}
                <div className="truncate text-xs text-[#F1F5F9]/60">{t.description}</div>
              </button>
            </li>
          ))}
          {tools.length === 0 && <li className="text-sm text-[#F1F5F9]/50">No tools registered.</li>}
        </ul>

        <div className="space-y-2">
          {selected && (
            <>
              <div className="font-mono text-xs text-[#F1F5F9]/60">
                tags: {selected.tags?.join(", ") || "—"} · schema:{" "}
                {Object.keys(selected.parameters?.properties ?? {}).join(", ") || "—"}
              </div>
              <textarea
                className="h-28 w-full rounded border border-[#222D3F] bg-[#070A0F] p-2 font-mono text-xs text-[#F1F5F9]"
                value={args}
                onChange={(e) => setArgs(e.target.value)}
              />
              <button
                className="rounded bg-[#00F5FF] px-4 py-1.5 font-semibold text-black disabled:opacity-50"
                onClick={() => void invoke()}
                disabled={busy}
              >
                {busy ? "Invoking…" : "Invoke"}
              </button>
            </>
          )}
          {error && <p className="font-mono text-xs text-[#F59E0B]">{error}</p>}
          {result && (
            <pre className="max-h-64 overflow-auto rounded border border-[#222D3F] bg-[#0D1320] p-2 font-mono text-xs">
              {result}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
