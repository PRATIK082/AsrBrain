"use client";
import { useState } from "react";
import { api } from "../../lib/api";
import type { CodeFinding, DiffItem } from "../../lib/types";

/**
 * The engineering workbench: deterministic ARXML topology, the structural diff
 * studio and the advisory code reviewer. These stay reachable from the left
 * rail, but the assistant is the default surface.
 */

export function ArxmlPane() {
  const [artifacts, setArtifacts] = useState<{ artifact_id: string; components: number }[]>([]);
  const [artifactId, setArtifactId] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const [nodeId, setNodeId] = useState("");
  const [neighbors, setNeighbors] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setArtifacts((await api.arxmlArtifacts()) as { artifact_id: string; components: number }[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function openTopology() {
    if (!artifactId) return;
    setError("");
    try {
      setDetail(await api.arxmlTopology(artifactId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function showNeighbors() {
    if (!nodeId || !artifactId) return;
    setError("");
    try {
      setNeighbors(await api.arxmlNeighbors(nodeId, artifactId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="space-y-4 p-6">
      <header>
        <h2 className="text-lg font-semibold text-fg">ARXML Explorer</h2>
        <p className="text-xs text-muted">
          Deterministic topology with XPath provenance. Unresolved references are shown as warnings
          — no connection is inferred.
        </p>
      </header>

      <div className="flex flex-wrap gap-2">
        <button className="btn" onClick={load}>
          List artifacts
        </button>
        <input
          className="input max-w-xs"
          placeholder="artifact_id"
          value={artifactId}
          onChange={(e) => setArtifactId(e.target.value)}
        />
        <button className="btn" onClick={openTopology} disabled={!artifactId}>
          Open topology
        </button>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      {artifacts.length > 0 && (
        <ul className="space-y-1 text-sm">
          {artifacts.map((a) => (
            <li key={a.artifact_id}>
              <button className="text-accent underline" onClick={() => setArtifactId(a.artifact_id)}>
                {a.artifact_id}
              </button>{" "}
              <span className="text-faint">— {a.components} SWCs</span>
            </li>
          ))}
        </ul>
      )}

      {detail && (
        <div className="grid gap-4 text-sm md:grid-cols-2">
          <div className="panel-flat p-3">
            <h3 className="mb-1.5 font-semibold text-fg">Components ({detail.components.length})</h3>
            <ul className="scrollbar-thin max-h-64 space-y-1 overflow-y-auto">
              {detail.components.map((c: any) => (
                <li key={c.qualified_name}>
                  <button className="text-accent underline" onClick={() => setNodeId(c.qualified_name)}>
                    {c.short_name}
                  </button>{" "}
                  <span className="text-faint">{c.component_type}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="panel-flat p-3">
            <h3 className="mb-1.5 font-semibold text-fg">Ports ({detail.ports.length})</h3>
            <ul className="scrollbar-thin max-h-64 space-y-1 overflow-y-auto">
              {detail.ports.map((p: any) => (
                <li key={p.qualified_name}>
                  {p.short_name} <b>({p.direction})</b>{" "}
                  <span className="font-mono text-2xs text-faint">{p.source_xpath}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <input
          className="input max-w-md"
          placeholder="node qualified name"
          value={nodeId}
          onChange={(e) => setNodeId(e.target.value)}
        />
        <button className="btn" onClick={showNeighbors} disabled={!nodeId || !artifactId}>
          Neighbors / path
        </button>
      </div>

      {neighbors && (
        <pre className="scrollbar-thin max-h-64 overflow-y-auto rounded-lg border border-edge/60 bg-ink-950/60 p-3 font-mono text-2xs">
          {JSON.stringify(neighbors, null, 2)}
        </pre>
      )}

      {detail?.unresolved_refs?.length > 0 && (
        <p className="text-sm text-warn">
          Unresolved references: {detail.unresolved_refs.length} rendered as warnings (no inferred
          connections).
        </p>
      )}
    </section>
  );
}

export function DiffPane() {
  const [base, setBase] = useState(
    '[{"entity_key":"CanIf_Transmit","normalized":"Std_ReturnType CanIf_Transmit(PduIdType)"}]',
  );
  const [target, setTarget] = useState(
    '[{"entity_key":"CanIf_Transmit","normalized":"Std_ReturnType CanIf_Transmit(PduIdType, const PduInfoType*)"}]',
  );
  const [rows, setRows] = useState<DiffItem[]>([]);
  const [error, setError] = useState("");

  async function run() {
    setError("");
    try {
      setRows((await api.diff(JSON.parse(base), JSON.parse(target), "api")) as DiffItem[]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="space-y-4 p-6">
      <header>
        <h2 className="text-lg font-semibold text-fg">Diff Studio</h2>
        <p className="text-xs text-muted">
          Evidence-aligned: an observed change is reported as such — the compatibility impact is
          never inferred silently.
        </p>
      </header>

      <div className="grid gap-2 md:grid-cols-2">
        <textarea
          className="input h-32 font-mono text-xs"
          value={base}
          onChange={(e) => setBase(e.target.value)}
        />
        <textarea
          className="input h-32 font-mono text-xs"
          value={target}
          onChange={(e) => setTarget(e.target.value)}
        />
      </div>

      <button className="btn btn-primary" onClick={run}>
        Compute structural diff
      </button>

      {error && <p className="text-xs text-bad">{error}</p>}

      {rows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-edge/60">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                {["Entity", "Change", "Risk", "Action"].map((h) => (
                  <th key={h} className="border-b border-edge/60 bg-ink-800/60 px-3 py-2 text-left text-fg">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.entity_key} className="border-b border-edge/40">
                  <td className="px-3 py-2 font-mono text-xs">{r.entity_key}</td>
                  <td className="px-3 py-2">{r.change_type}</td>
                  <td className="px-3 py-2">{r.compatibility_risk}</td>
                  <td className="px-3 py-2">{r.migration_action}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function CodePane() {
  const [source, setSource] = useState("void VCalc(void){ Rte_Read_Speed(&s); }\n");
  const [findings, setFindings] = useState<CodeFinding[]>([]);
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setError("");
    try {
      const res = (await api.codeAnalyze(source, "swc.c", ["Speed"])) as { findings: CodeFinding[] };
      setFindings(res.findings);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="space-y-4 p-6">
      <header>
        <h2 className="text-lg font-semibold text-fg">Code Review</h2>
        <p className="text-xs text-muted">
          Advisory only — every fix is a suggestion and a human approves it.
        </p>
      </header>

      <textarea
        className="input h-40 font-mono text-xs"
        value={source}
        onChange={(e) => setSource(e.target.value)}
      />

      <div className="flex flex-wrap items-center gap-3">
        <button className="btn btn-primary" onClick={run}>
          Analyze
        </button>
        <label className="flex items-center gap-2 text-xs text-muted">
          <input
            type="checkbox"
            checked={approved}
            onChange={(e) => setApproved(e.target.checked)}
          />
          I reviewed the advisories; no auto-fix without approval
        </label>
      </div>

      {error && <p className="text-xs text-bad">{error}</p>}

      <ul className="space-y-2 text-sm">
        {findings.map((f, i) => (
          <li key={i} className="rounded-lg border border-edge/60 bg-ink-900/50 p-2.5">
            <b className="text-fg">{f.rule}</b> <span className="badge">{f.level}</span>{" "}
            <span className="text-faint">{f.location}</span> — {f.message}
          </li>
        ))}
      </ul>

      {!approved && findings.length > 0 && (
        <p className="text-xs text-warn">Fixes are suggestions only until you approve.</p>
      )}
    </section>
  );
}
