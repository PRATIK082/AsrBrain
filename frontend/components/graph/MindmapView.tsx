"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import type { MindmapResult } from "../../lib/types";
import { MermaidDiagram } from "../chat/MermaidDiagram";

/**
 * Mindmap builder — renders a Mermaid mindmap for a topic.
 * Source "auto" prefers the knowledge graph, then falls back to an outline.
 */
export function MindmapView({ topic, source = "auto", depth = 2 }: {
  topic: string;
  source?: string;
  depth?: number;
}) {
  const [query, setQuery] = useState(topic);
  const [mode, setMode] = useState(source);
  const [levels, setLevels] = useState(depth);
  const [result, setResult] = useState<MindmapResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function build() {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.mindmap(query.trim(), mode, levels));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <input
          className="flex-1 rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9] placeholder:text-[#F1F5F9]/30"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void build()}
          placeholder="Topic, e.g. CanIf transmit requirements"
        />
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="auto">auto</option>
          <option value="graph">graph</option>
          <option value="outline">outline</option>
        </select>
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={levels}
          onChange={(e) => setLevels(Number(e.target.value))}
        >
          {[1, 2, 3].map((d) => (
            <option key={d} value={d}>depth {d}</option>
          ))}
        </select>
        <button
          className="rounded bg-[#00F5FF] px-4 py-2 font-semibold text-black disabled:opacity-50"
          onClick={() => void build()}
          disabled={busy}
        >
          {busy ? "Building…" : "Build mindmap"}
        </button>
      </div>

      {error && <p className="font-mono text-sm text-[#F59E0B]">{error}</p>}

      {result && (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-3 font-mono text-xs text-[#F1F5F9]/60">
            <span>source: {result.source}</span>
            {result.node_count !== undefined && <span>nodes: {result.node_count}</span>}
            {result.seeds && result.seeds.length > 0 && (
              <span>seeds: {result.seeds.slice(0, 6).join(", ")}</span>
            )}
          </div>
          {result.empty ? (
            <p className="text-sm text-[#F1F5F9]/60">
              No graph neighbourhood found for this topic. Build the knowledge graph first or lower the depth.
            </p>
          ) : (
            <MermaidDiagram chart={result.mermaid} />
          )}
        </div>
      )}
    </div>
  );
}
