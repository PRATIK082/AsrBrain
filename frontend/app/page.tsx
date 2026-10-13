"use client";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api";
import type { CodeFinding, DiffItem } from "../lib/types";
import { useAsrBrainStore } from "../store/useAsrBrainStore";
import { useSettings } from "../stores/settings-store";
import { useAsrStream } from "../hooks/useAsrStream";
import { PipelineTelemetry } from "../components/chat/PipelineTelemetry";
import { AsrCitationDrawer } from "../components/chat/AsrCitationDrawer";

type Tab = "chat" | "arxml" | "diff" | "code";

function ChatPane() {
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [convId] = useState("");
  const [processing, setProcessing] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const model = useSettings((s) => s.model || "ollama");
  const sessions = useAsrBrainStore((s) => s.sessions);
  const activeSessionId = useAsrBrainStore((s) => s.activeSessionId);
  const initiateSession = useAsrBrainStore((s) => s.initiateSession);
  const forkWorkspace = useAsrBrainStore((s) => s.forkWorkspace);
  const exportSessionBundle = useAsrBrainStore((s) => s.exportSessionBundle);
  const importSessionBundle = useAsrBrainStore((s) => s.importSessionBundle);
  const {
    executeStream, abortStream, isStreaming,
    currentStages, currentEvidence, streamedResponse, verdict,
  } = useAsrStream();

  useEffect(() => {
    if (!activeSessionId) initiateSession(model);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const session = activeSessionId ? sessions[activeSessionId] : undefined;
  const messages = session?.messages ?? [];

  async function send() {
    if (!input.trim() || !activeSessionId || isStreaming) return;
    const text = input;
    setInput("");
    setStatus("");
    setProcessing("");
    await executeStream(activeSessionId, text, { conversationId: convId || undefined });
  }

  function downloadBundle() {
    if (!activeSessionId) return;
    const blob = new Blob([exportSessionBundle(activeSessionId)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "asrbrain_session.json";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  async function importBundle(f: File) {
    const ok = importSessionBundle(await f.text());
    setStatus(ok ? "Session bundle imported." : "Not a valid session bundle.");
  }

  return (
    <section className="flex flex-1 flex-col bg-[#070A0F] text-[#F1F5F9]">
      <div className="flex flex-wrap items-center gap-2 border-b border-[#222D3F] bg-[#121824] px-4 py-2 text-xs">
        <span className="font-mono text-[#F1F5F9]/60">
          {session?.title ?? "…"} · model {session?.model ?? model}
          {session?.moduleSlot ? ` · ${session.moduleSlot}` : ""}
          {session?.releaseSlot ? ` · ${session.releaseSlot}` : ""}
        </span>
        <span className="flex-1" />
        <button className="rounded border border-[#222D3F] px-2 py-1 hover:border-[#00F5FF]/60"
          onClick={() => initiateSession(model)}>＋ New</button>
        <button className="rounded border border-[#222D3F] px-2 py-1 hover:border-[#00F5FF]/60"
          onClick={() => activeSessionId && forkWorkspace(activeSessionId, model)}>⑂ Fork</button>
        <button className="rounded border border-[#222D3F] px-2 py-1 hover:border-[#00F5FF]/60"
          onClick={downloadBundle}>⬇ Export</button>
        <button className="rounded border border-[#222D3F] px-2 py-1 hover:border-[#00F5FF]/60"
          onClick={() => fileRef.current?.click()}>⬆ Import</button>
        <input ref={fileRef} type="file" accept=".json" className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) void importBundle(f); e.target.value = ""; }} />
      </div>
      {processing && <p className="bg-[#121824] px-4 py-1 font-mono text-xs text-[#00F5FF]">Routing: {processing}</p>}
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {currentStages.length > 0 && <PipelineTelemetry stages={currentStages} />}
        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "text-right" : "text-left"}>
            <div className={`inline-block max-w-3xl rounded border p-3 text-left ${
              m.role === "user" ? "border-[#222D3F] bg-[#121824]" : "border-[#222D3F] bg-[#0D1320]"}`}>
              <ReactMarkdown>{m.content}</ReactMarkdown>
            </div>
          </div>
        ))}
        {isStreaming && streamedResponse && (
          <div className="text-left">
            <div className="inline-block max-w-3xl rounded border border-[#00F5FF]/30 bg-[#0D1320] p-3 text-left">
              <ReactMarkdown>{streamedResponse}</ReactMarkdown>
            </div>
          </div>
        )}
        {currentEvidence.length > 0 && <AsrCitationDrawer sources={currentEvidence} verdict={verdict} />}
        {status && <p className="font-mono text-sm text-[#F59E0B]">{status}</p>}
      </div>
      <div className="flex gap-2 border-t border-[#222D3F] bg-[#121824] p-4">
        <input className="flex-1 rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9] placeholder:text-[#F1F5F9]/30"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void send()}
          placeholder="Ask about AUTOSAR… (release/platform asked back only if missing)" />
        <button className="rounded bg-[#00F5FF] px-4 py-2 font-semibold text-black" onClick={() => void send()}>Send</button>
        {isStreaming && <button className="rounded border border-[#222D3F] px-4 py-2" onClick={abortStream}>Stop</button>}
      </div>
    </section>
  );
}

function ArxmlPane() {
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const [artifactId, setArtifactId] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const [nodeId, setNodeId] = useState("");
  const [neighbors, setNeighbors] = useState<any>(null);

  async function load() {
    setArtifacts(await api.arxmlArtifacts() as any[]);
  }
  async function openTopology() {
    if (!artifactId) return;
    setDetail(await api.arxmlTopology(artifactId));
  }
  async function showNeighbors() {
    if (!nodeId || !artifactId) return;
    setNeighbors(await api.arxmlNeighbors(nodeId, artifactId));
  }

  return (
    <section className="flex-1 space-y-4 overflow-y-auto p-6">
      <h2 className="font-bold">ARXML Explorer (deterministic topology, XPath provenance)</h2>
      <div className="flex gap-2">
        <button className="rounded border px-3 py-1" onClick={load}>List artifacts</button>
        <input className="rounded border p-1" placeholder="artifact_id" value={artifactId} onChange={(e) => setArtifactId(e.target.value)} />
        <button className="rounded border px-3 py-1" onClick={openTopology}>Open topology</button>
      </div>
      {artifacts.length > 0 && (
        <ul className="list-disc pl-6 text-sm">
          {artifacts.map((a: any) => (
            <li key={a.artifact_id}><button className="underline" onClick={() => { setArtifactId(a.artifact_id); }}>{a.artifact_id}</button> — {a.components} SWCs</li>
          ))}
        </ul>
      )}
      {detail && (
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div><h3 className="font-semibold">Components ({detail.components.length})</h3>
            <ul className="max-h-64 overflow-y-auto">{detail.components.map((c: any) => (
              <li key={c.qualified_name}><button className="underline" onClick={() => setNodeId(c.qualified_name)}>{c.short_name}</button> <span className="text-gray-500">{c.component_type}</span></li>))}</ul></div>
          <div><h3 className="font-semibold">Ports ({detail.ports.length})</h3>
            <ul className="max-h-64 overflow-y-auto">{detail.ports.map((p: any) => (
              <li key={p.qualified_name}>{p.short_name} <b>({p.direction})</b> <span className="text-gray-500">{p.source_xpath}</span></li>))}</ul></div>
        </div>
      )}
      <div className="flex gap-2">
        <input className="flex-1 rounded border p-1" placeholder="node qualified name" value={nodeId} onChange={(e) => setNodeId(e.target.value)} />
        <button className="rounded border px-3 py-1" onClick={showNeighbors}>Neighbors / path</button>
      </div>
      {neighbors && <pre className="max-h-64 overflow-y-auto rounded bg-gray-50 p-2 text-xs">{JSON.stringify(neighbors, null, 2)}</pre>}
      {detail?.unresolved_refs?.length > 0 && (
        <p className="text-sm text-amber-700">Unresolved references: {detail.unresolved_refs.length} rendered as warnings (no inferred connections).</p>)}
    </section>
  );
}

function DiffPane() {
  const [base, setBase] = useState('[{"entity_key":"CanIf_Transmit","normalized":"Std_ReturnType CanIf_Transmit(PduIdType)"}]');
  const [target, setTarget] = useState('[{"entity_key":"CanIf_Transmit","normalized":"Std_ReturnType CanIf_Transmit(PduIdType, const PduInfoType*)"}]');
  const [rows, setRows] = useState<DiffItem[]>([]);

  async function run() {
    try {
      setRows(await api.diff(JSON.parse(base), JSON.parse(target), "api") as DiffItem[]);
    } catch (e) { alert(String(e)); }
  }

  return (
    <section className="flex-1 space-y-4 overflow-y-auto p-6">
      <h2 className="font-bold">Diff Studio (evidence-aligned: observed change ≠ inferred impact)</h2>
      <div className="grid grid-cols-2 gap-2">
        <textarea className="h-32 rounded border p-2 font-mono text-xs" value={base} onChange={(e) => setBase(e.target.value)} />
        <textarea className="h-32 rounded border p-2 font-mono text-xs" value={target} onChange={(e) => setTarget(e.target.value)} />
      </div>
      <button className="rounded bg-black px-4 py-2 text-white" onClick={run}>Compute structural diff</button>
      <table className="w-full text-sm">
        <thead><tr><th className="text-left">Entity</th><th className="text-left">Change</th><th className="text-left">Risk</th><th className="text-left">Action</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.entity_key} className="border-t"><td>{r.entity_key}</td><td>{r.change_type}</td><td>{r.compatibility_risk}</td><td>{r.migration_action}</td></tr>))}</tbody>
      </table>
    </section>
  );
}

function CodePane() {
  const [source, setSource] = useState("void VCalc(void){ Rte_Read_Speed(&s); }\n");
  const [findings, setFindings] = useState<CodeFinding[]>([]);
  const [approved, setApproved] = useState(false);

  async function run() {
    setFindings(((await api.codeAnalyze(source, "swc.c", ["Speed"])) as any).findings as CodeFinding[]);
  }

  return (
    <section className="flex-1 space-y-4 overflow-y-auto p-6">
      <h2 className="font-bold">Code Review (advisory only — human approval required)</h2>
      <textarea className="h-40 w-full rounded border p-2 font-mono text-xs" value={source} onChange={(e) => setSource(e.target.value)} />
      <div className="flex items-center gap-2">
        <button className="rounded bg-black px-4 py-2 text-white" onClick={run}>Analyze</button>
        <label className="text-sm"><input type="checkbox" checked={approved} onChange={(e) => setApproved(e.target.checked)} /> I reviewed advisories; apply no auto-fix without approval</label>
      </div>
      <ul className="space-y-2 text-sm">{findings.map((f, i) => (
        <li key={i} className="rounded border p-2"><b>{f.rule}</b> [{f.level}] {f.location} — {f.message}</li>))}</ul>
      {!approved && findings.length > 0 && <p className="text-sm text-gray-500">Fixes are suggestions only until you approve.</p>}
    </section>
  );
}

export default function EngineeringPage() {
  const [tab, setTab] = useState<Tab>("chat");
  return (
    <main className="flex h-screen">
      <aside className="w-64 border-r p-4">
        <h1 className="font-bold">AsrBrain</h1>
        {(["chat", "arxml", "diff", "code"] as Tab[]).map((t) => (
          <button key={t} className={`mt-2 w-full rounded border p-2 text-left ${tab === t ? "bg-black text-white" : ""}`} onClick={() => setTab(t)}>
            {t === "chat" ? "💬 Chat" : t === "arxml" ? "🧩 ARXML Explorer" : t === "diff" ? "🔀 Diff Studio" : "🔍 Code Review"}
          </button>
        ))}
        <p className="mt-4 text-xs text-gray-500">Processed locally unless approved policy shows otherwise. No chain-of-thought displayed.</p>
      </aside>
      {tab === "chat" ? <ChatPane /> : tab === "arxml" ? <ArxmlPane /> : tab === "diff" ? <DiffPane /> : <CodePane />}
    </main>
  );
}
