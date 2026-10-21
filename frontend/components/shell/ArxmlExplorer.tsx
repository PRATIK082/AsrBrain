"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { ArxmlToolSpec, ArxmlV2Artifact, ArxmlV2Tree, ArxmlValidationResult } from "../../lib/types";

/**
 * The ARXML Explorer (Phase 4, ADR-0005).
 *
 * ARXML is structured data, not RAG text. Everything shown here comes from a
 * deterministic tool: the tree, the validation findings and the reference
 * resolution. When a fact is not in the file, the panel says so and names the
 * scope that was searched — it never fills the gap.
 */
export function ArxmlExplorer() {
  const [tools, setTools] = useState<ArxmlToolSpec[]>([]);
  const [artifacts, setArtifacts] = useState<ArxmlV2Artifact[]>([]);
  const [artifactId, setArtifactId] = useState("");
  const [tree, setTree] = useState<ArxmlV2Tree | null>(null);
  const [validation, setValidation] = useState<ArxmlValidationResult | null>(null);
  const [references, setReferences] = useState<{ resolved: unknown[]; unresolved: unknown[]; summary?: string } | null>(null);
  const [query, setQuery] = useState("");
  const [pathResult, setPathResult] = useState<{ status: string; error?: string; summary?: string; element?: Record<string, unknown> } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.arxmlTools().then((r) => setTools(r.tools)).catch(() => setTools([]));
    refreshArtifacts();
  }, []);

  async function refreshArtifacts() {
    setError("");
    try {
      const r = await api.arxmlV2Artifacts();
      setArtifacts(r.artifacts ?? []);
      if (!artifactId && r.artifacts?.length) setArtifactId(r.artifacts[0].artifact_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function open() {
    if (!artifactId) return;
    setBusy(true);
    setError("");
    setPathResult(null);
    try {
      setTree(await api.arxmlV2Tree(artifactId));
      setValidation(await api.arxmlV2Validate(artifactId));
      setReferences(await api.arxmlV2References(artifactId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setTree(null);
    } finally {
      setBusy(false);
    }
  }

  async function lookup() {
    if (!artifactId || !query.trim()) return;
    setBusy(true);
    setError("");
    try {
      setPathResult(await api.arxmlV2Path(artifactId, query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="border-b border-edge/70 px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="mr-2 text-lg font-semibold text-fg">ARXML Explorer</h2>
          <select
            className="select max-w-xs"
            value={artifactId}
            onChange={(e) => setArtifactId(e.target.value)}
            aria-label="ARXML artifact"
          >
            <option value="">select artifact…</option>
            {artifacts.map((a) => (
              <option key={a.artifact_id} value={a.artifact_id}>
                {a.artifact_id} · {a.counts?.components ?? 0} components
              </option>
            ))}
          </select>
          <button className="btn" onClick={() => void refreshArtifacts()}>
            Reload
          </button>
          <button className="btn btn-primary" onClick={() => void open()} disabled={!artifactId || busy}>
            {busy ? "Working…" : "Open artifact"}
          </button>
        </div>
        <p className="mt-1.5 text-xs text-muted">
          Structural facts come from deterministic tools — every element carries the file and line it
          was observed at. Nothing here is inferred.
        </p>
      </header>

      <div className="drawer-body space-y-4 px-5 py-4">
        {error && <p className="text-xs text-bad">{error}</p>}

        {artifacts.length === 0 && !error && (
          <div className="empty-state">
            <p className="text-sm text-fg">No ARXML artifact is registered yet</p>
            <p className="max-w-md text-xs text-muted">
              Upload an ARXML file to <code className="font-mono text-accent">POST /api/v2/arxml/upload</code>.
              It is parsed structurally, validated, and stored with its content hash — the
              explanation layer never sees the raw file.
            </p>
          </div>
        )}

        {tools.length > 0 && (
          <section className="panel-flat px-4 py-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Deterministic tools
            </h3>
            <ul className="space-y-1">
              {tools.map((t) => (
                <li key={t.name} className="text-xs">
                  <span className="font-mono text-accent">{t.name}</span>
                  <span className="ml-2 text-muted">{t.description}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {validation && (
          <section className="panel-flat px-4 py-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">Validation</h3>
              <span
                className={
                  validation.status === "passed"
                    ? "status-verified"
                    : validation.status === "failed"
                      ? "status-insufficient"
                      : "status-review"
                }
              >
                {validation.status}
              </span>
              <span className="text-xs text-faint">
                {validation.findings.length} finding(s) ·{" "}
                {validation.checks.filter((c) => c.passed).length}/{validation.checks.length} checks
                passed
              </span>
            </div>
            {validation.findings.length === 0 ? (
              <p className="text-xs text-muted">No findings.</p>
            ) : (
              <ul className="space-y-1">
                {validation.findings.map((f, i) => (
                  <li key={i} className="flex items-start gap-2 text-xs">
                    <span
                      className={
                        f.severity === "error"
                          ? "status-insufficient"
                          : f.severity === "warning"
                            ? "status-review"
                            : "badge"
                      }
                    >
                      {f.severity}
                    </span>
                    <span className="text-fg">
                      {f.message}
                      {f.line_start ? (
                        <span className="ml-1 font-mono text-faint">line {f.line_start}</span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        {references && (
          <section className="panel-flat px-4 py-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">References</h3>
            <p className="text-xs text-fg">{references.summary}</p>
          </section>
        )}

        {tree && (
          <section className="panel-flat px-4 py-3">
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
              Structure · {tree.counts?.components ?? 0} components
            </h3>
            {tree.components.length === 0 ? (
              <p className="text-xs text-muted">
                The document parsed, but it contains no software components.
              </p>
            ) : (
              <ul className="space-y-2">
                {tree.components.map((c) => (
                  <li key={c.qualified_name} className="rounded border border-edge/60 px-2.5 py-2">
                    <div className="flex flex-wrap items-baseline gap-2">
                      <span className="font-mono text-sm text-fg">{c.qualified_name}</span>
                      <span className="badge">{c.component_type}</span>
                      {c.line_start ? (
                        <span className="text-2xs text-faint">line {c.line_start}</span>
                      ) : null}
                    </div>
                    {c.ports.length > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {c.ports.map((p) => (
                          <li key={p.qualified_name} className="text-xs text-muted">
                            <span className="font-mono">{p.short_name}</span>
                            <span className="ml-1 badge">{p.direction}</span>
                            {p.interface_type ? (
                              <span className="ml-1">{p.interface_type}</span>
                            ) : null}
                            {p.line_start ? (
                              <span className="ml-1 text-faint">line {p.line_start}</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}

        <section className="panel-flat px-4 py-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Query an element
          </h3>
          <div className="flex flex-wrap gap-2">
            <input
              className="input flex-1"
              placeholder="qualified path or short name"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void lookup()}
            />
            <button className="btn" onClick={() => void lookup()} disabled={!query.trim() || busy}>
              Look up
            </button>
          </div>
          {pathResult && (
            <div className="mt-2 text-xs">
              {pathResult.status === "ok" ? (
                <p className="text-fg">
                  <span className="font-mono text-accent">
                    {String(pathResult.element?.qualified_name ?? "")}
                  </span>
                  <span className="ml-2 text-muted">{String(pathResult.element?.kind ?? "")}</span>
                  {pathResult.element?.line_start ? (
                    <span className="ml-2 text-faint">line {String(pathResult.element?.line_start)}</span>
                  ) : null}
                </p>
              ) : (
                <p className="text-warn">
                  {pathResult.error ?? "not found"} — {pathResult.summary ?? ""}
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
