"use client";
import { useEffect, useRef, useState } from "react";
import { api, streamAgent } from "../../lib/api";
import type { AgentEvent, AgentObservation, AgentWorkflow } from "../../lib/types";

interface LogLine {
  kind: "workflow" | "plan" | "tool_call" | "tool_result" | "tool_skipped" | "error" | "answer";
  text: string;
}

/**
 * Agentic workflow runner — routes a question to a deterministic workflow
 * (or the freeform planner) and streams the plan / tool calls / answer.
 */
export function AgentRunner() {
  const [workflows, setWorkflows] = useState<AgentWorkflow[]>([]);
  const [workflow, setWorkflow] = useState("");
  const [mode, setMode] = useState("workflow");
  const [query, setQuery] = useState("");
  const [provider, setProvider] = useState("none");
  const [allowMutating, setAllowMutating] = useState(false);
  const [log, setLog] = useState<LogLine[]>([]);
  const [answer, setAnswer] = useState("");
  const [observations, setObservations] = useState<AgentObservation[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api.agentWorkflows()
      .then((r) => setWorkflows(r.workflows ?? []))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  function push(kind: LogLine["kind"], text: string) {
    setLog((prev) => [...prev, { kind, text }]);
  }

  async function run() {
    if (!query.trim() || busy) return;
    setBusy(true);
    setError("");
    setLog([]);
    setAnswer("");
    setObservations([]);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      for await (const ev of streamAgent({
        query: query.trim(),
        workflow: mode === "workflow" ? workflow : "",
        mode: mode === "freeform" ? "freeform" : mode === "workflow" ? "workflow" : "auto",
        provider,
        allow_mutating: allowMutating,
      }, ctrl.signal)) {
        handleEvent(ev);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function handleEvent(ev: AgentEvent) {
    switch (ev.event) {
      case "workflow":
        push("workflow", `workflow: ${ev.workflow}${ev.title ? ` — ${ev.title}` : ""}`);
        break;
      case "plan": {
        const steps = ev.plan?.steps ?? [];
        push("plan", `plan (${steps.length} steps): ${steps.map((s) => s.tool).join(" → ")}`);
        break;
      }
      case "tool_call":
        push("tool_call", `→ ${ev.tool} ${JSON.stringify(ev.args ?? {})}`);
        break;
      case "tool_result":
        push("tool_result", `← ${ev.tool}: ${ev.summary ?? (ev.ok ? "ok" : "failed")}`);
        break;
      case "tool_skipped":
        push("tool_skipped", `⊘ ${ev.tool} skipped: ${ev.reason ?? "not permitted"}`);
        break;
      case "complete":
        setAnswer(ev.answer ?? "");
        setObservations(ev.observations ?? []);
        break;
      case "error":
        setError(ev.error);
        break;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="workflow">workflow</option>
          <option value="auto">auto (intent routing)</option>
          <option value="freeform">freeform (planner)</option>
        </select>
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9] disabled:opacity-40"
          value={workflow}
          onChange={(e) => setWorkflow(e.target.value)}
          disabled={mode !== "workflow"}
        >
          <option value="">select workflow…</option>
          {workflows.map((w) => (
            <option key={w.name} value={w.name}>{w.title}</option>
          ))}
        </select>
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="ollama">ollama</option>
          <option value="openai_compat">openai_compat</option>
          <option value="none">none (deterministic)</option>
        </select>
        <label className="flex items-center gap-1 text-xs text-[#F1F5F9]/70">
          <input type="checkbox" checked={allowMutating} onChange={(e) => setAllowMutating(e.target.checked)} />
          allow mutating tools
        </label>
      </div>

      <div className="flex gap-2">
        <input
          className="flex-1 rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9] placeholder:text-[#F1F5F9]/30"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void run()}
          placeholder="e.g. Trace SWS_Com_00123 through ARXML to the implementing code and its tests"
        />
        <button
          className="rounded bg-[#00F5FF] px-4 py-2 font-semibold text-black disabled:opacity-50"
          onClick={() => void run()}
          disabled={busy || (mode === "workflow" && !workflow)}
        >
          {busy ? "Running…" : "Run"}
        </button>
        {busy && <button className="rounded border border-[#222D3F] px-4 py-2" onClick={stop}>Stop</button>}
      </div>

      {error && <p className="font-mono text-sm text-[#F59E0B]">{error}</p>}

      {log.length > 0 && (
        <pre className="max-h-64 overflow-y-auto rounded border border-[#222D3F] bg-[#0D1320] p-3 font-mono text-xs text-[#F1F5F9]/80">
          {log.map((l, i) => `${String(i + 1).padStart(2, "0")} ${l.kind.padEnd(12)} ${l.text}`).join("\n")}
        </pre>
      )}

      {answer && (
        <div className="rounded border border-[#222D3F] bg-[#0D1320] p-3">
          <h3 className="mb-2 text-sm font-semibold text-[#00F5FF]">Answer</h3>
          <pre className="whitespace-pre-wrap font-sans text-sm text-[#F1F5F9]">{answer}</pre>
        </div>
      )}

      {observations.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Observations</h3>
          <ul className="space-y-1 text-xs">
            {observations.map((o, i) => (
              <li key={i} className="rounded border border-[#222D3F] px-2 py-1 font-mono">
                <span className="text-[#00F5FF]">{o.tool}</span>{" "}
                <span className="text-[#F1F5F9]/80">{o.summary}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
