"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { GraphNode, GraphQueryResult, GraphStats } from "../../lib/types";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded border border-[#222D3F] bg-[#0D1320] px-3 py-2">
      <div className="font-mono text-[11px] uppercase tracking-wide text-[#F1F5F9]/50">{label}</div>
      <div className="font-mono text-lg text-[#00F5FF]">{value}</div>
    </div>
  );
}

/**
 * GraphRAG explorer — local / global / hybrid retrieval over the knowledge graph
 * plus community summaries and per-node neighbourhoods.
 */
export function GraphExplorer() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("hybrid");
  const [depth, setDepth] = useState(2);
  const [limit, setLimit] = useState(25);
  const [result, setResult] = useState<GraphQueryResult | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [neighbors, setNeighbors] = useState<{ nodes: GraphNode[]; edges: Record<string, unknown>[] } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [building, setBuilding] = useState(false);
  const [buildMsg, setBuildMsg] = useState("");

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.graphStats());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadStats();
  }, [loadStats]);

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.graphQuery(query.trim(), mode, depth, limit));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  async function openNode(node: GraphNode) {
    setSelected(node);
    setNeighbors(null);
    try {
      setNeighbors(await api.graphNode(node.node_id, 1, 80));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function rebuild() {
    setBuilding(true);
    setBuildMsg("");
    setError("");
    try {
      const r = await api.graphBuild("", [], true);
      setBuildMsg(`Graph rebuilt: ${JSON.stringify(r)}`);
      await loadStats();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="space-y-4">
      {stats && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-6">
          <Stat label="nodes" value={stats.nodes ?? 0} />
          <Stat label="edges" value={stats.edges ?? 0} />
          <Stat label="communities" value={stats.communities ?? 0} />
          <Stat label="trace links" value={stats.trace_links ?? 0} />
          <Stat label="inferred edges" value={stats.inferred_edges ?? 0} />
          <Stat label="store" value={stats.path ?? ""} />
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          className="flex-1 rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9] placeholder:text-[#F1F5F9]/30"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void search()}
          placeholder="Search the knowledge graph…"
        />
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={mode}
          onChange={(e) => setMode(e.target.value)}
        >
          <option value="hybrid">hybrid</option>
          <option value="local">local</option>
          <option value="global">global</option>
        </select>
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={depth}
          onChange={(e) => setDepth(Number(e.target.value))}
        >
          {[1, 2, 3].map((d) => (
            <option key={d} value={d}>depth {d}</option>
          ))}
        </select>
        <select
          className="rounded border border-[#222D3F] bg-[#070A0F] p-2 text-[#F1F5F9]"
          value={limit}
          onChange={(e) => setLimit(Number(e.target.value))}
        >
          {[10, 25, 50, 100].map((n) => (
            <option key={n} value={n}>limit {n}</option>
          ))}
        </select>
        <button
          className="rounded bg-[#00F5FF] px-4 py-2 font-semibold text-black disabled:opacity-50"
          onClick={() => void search()}
          disabled={busy}
        >
          {busy ? "Searching…" : "Search"}
        </button>
        <button
          className="rounded border border-[#222D3F] px-4 py-2 text-sm disabled:opacity-50"
          onClick={() => void rebuild()}
          disabled={building}
          title="Rebuild the knowledge graph from the canonical store (mutating)"
        >
          {building ? "Rebuilding…" : "Rebuild graph"}
        </button>
      </div>

      {buildMsg && <p className="font-mono text-xs text-[#00F5FF]">{buildMsg}</p>}
      {error && <p className="font-mono text-sm text-[#F59E0B]">{error}</p>}

      {result && (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="space-y-2">
            <h3 className="font-semibold">
              Entities <span className="font-mono text-xs text-[#F1F5F9]/50">({result.nodes.length})</span>
            </h3>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">
              {result.nodes.map((n) => (
                <li key={n.node_id}>
                  <button
                    className={`w-full truncate rounded border px-2 py-1 text-left ${
                      selected?.node_id === n.node_id
                        ? "border-[#00F5FF]/60 bg-[#0D1320]"
                        : "border-transparent hover:border-[#222D3F]"
                    }`}
                    onClick={() => void openNode(n)}
                  >
                    <span className="font-mono text-[11px] text-[#00F5FF]">{n.type}</span>{" "}
                    <span className="text-[#F1F5F9]">{n.label}</span>
                    {n.score !== undefined && (
                      <span className="float-right font-mono text-[11px] text-[#F1F5F9]/50">{n.score}</span>
                    )}
                  </button>
                </li>
              ))}
              {result.nodes.length === 0 && <li className="text-sm text-[#F1F5F9]/50">No entities matched.</li>}
            </ul>
          </div>

          <div className="space-y-2">
            <h3 className="font-semibold">
              Communities <span className="font-mono text-xs text-[#F1F5F9]/50">({result.communities.length})</span>
            </h3>
            <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">
              {result.communities.map((c) => (
                <li key={c.community_id} className="rounded border border-[#222D3F] p-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">{c.title}</span>
                    <span className="font-mono text-[11px] text-[#F1F5F9]/50">
                      {c.community_id} · {c.member_count ?? c.members?.length ?? 0}
                    </span>
                  </div>
                  {c.summary && <p className="mt-1 text-xs text-[#F1F5F9]/70">{c.summary}</p>}
                </li>
              ))}
              {result.communities.length === 0 && <li className="text-sm text-[#F1F5F9]/50">No communities matched.</li>}
            </ul>

            <h3 className="pt-2 font-semibold">
              Relations <span className="font-mono text-xs text-[#F1F5F9]/50">({result.edges.length})</span>
            </h3>
            <ul className="max-h-48 space-y-1 overflow-y-auto font-mono text-xs">
              {result.edges.slice(0, 120).map((e, i) => (
                <li key={`${e.src}-${e.rel}-${e.dst}-${i}`} className="truncate text-[#F1F5F9]/70">
                  {e.src} <span className="text-[#00F5FF]">{e.rel}</span> {e.dst}
                  {e.is_inferred ? <span className="text-[#F59E0B]"> (inferred)</span> : null}
                </li>
              ))}
              {result.edges.length === 0 && <li className="text-sm text-[#F1F5F9]/50">No relations.</li>}
            </ul>
          </div>
        </div>
      )}

      {selected && (
        <div className="rounded border border-[#222D3F] bg-[#0D1320] p-3">
          <div className="flex items-center gap-2">
            <span className="font-mono text-xs text-[#00F5FF]">{selected.type}</span>
            <span className="font-semibold">{selected.label}</span>
            <span className="font-mono text-[11px] text-[#F1F5F9]/50">{selected.node_id}</span>
          </div>
          {neighbors ? (
            <ul className="mt-2 max-h-56 space-y-1 overflow-y-auto font-mono text-xs">
              {neighbors.edges.map((e, i) => (
                <li key={i} className="truncate text-[#F1F5F9]/70">
                  {String(e.src)} <span className="text-[#00F5FF]">{String(e.rel)}</span> {String(e.dst)}
                </li>
              ))}
              {neighbors.edges.length === 0 && <li className="text-[#F1F5F9]/50">No direct relations.</li>}
            </ul>
          ) : (
            <p className="mt-2 font-mono text-xs text-[#F1F5F9]/50">Loading neighbourhood…</p>
          )}
        </div>
      )}
    </div>
  );
}
