"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type {
  FindingRow,
  FailureCluster,
  TestResultRow,
  TestRunRow,
  TraceCoverage,
  TraceMatrix,
  TraceOrphans,
  TraceRequirement,
} from "../../lib/types";

/**
 * The Requirements and Tests explorer (Phase 6).
 *
 * Everything here comes from the deterministic traceability API. The wording
 * is deliberately careful: a requirement that has a test case has **evidence
 * available for review**. It is not "compliant", it is not "ISO 26262
 * verified", and nothing on this screen claims that it is.
 */
export function TraceabilityExplorer({ view }: { view: "requirements" | "tests" }) {
  const [projectId, setProjectId] = useState("");
  const [requirements, setRequirements] = useState<TraceRequirement[]>([]);
  const [matrix, setMatrix] = useState<TraceMatrix | null>(null);
  const [coverage, setCoverage] = useState<TraceCoverage | null>(null);
  const [orphans, setOrphans] = useState<TraceOrphans | null>(null);
  const [runs, setRuns] = useState<TestRunRow[]>([]);
  const [results, setResults] = useState<TestResultRow[]>([]);
  const [clusters, setClusters] = useState<FailureCluster[]>([]);
  const [findings, setFindings] = useState<FindingRow[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setBusy(true);
      setError("");
      try {
        if (view === "requirements") {
          const [reqs, mx, cov, orph] = await Promise.all([
            api.requirementsList(projectId),
            api.traceabilityMatrix(projectId),
            api.traceabilityCoverage(projectId),
            api.traceabilityOrphans(projectId),
          ]);
          if (cancelled) return;
          setRequirements(reqs);
          setMatrix(mx);
          setCoverage(cov);
          setOrphans(orph);
        } else {
          const [runRows, findRows] = await Promise.all([
            api.testRuns(projectId),
            api.findingsList(projectId),
          ]);
          if (cancelled) return;
          setRuns(runRows);
          setFindings(findRows);
          const first = runRows[0];
          if (first) {
            const [res, cl] = await Promise.all([
              api.testResults(first.id),
              api.testClusters(first.id),
            ]);
            if (cancelled) return;
            setResults(res);
            setClusters(cl);
          }
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setBusy(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [view, projectId]);

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto px-4 py-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-semibold text-fg">
          {view === "requirements" ? "Requirement traceability" : "Test & log intelligence"}
        </h2>
        <input
          className="input w-56"
          placeholder="project id (optional)"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        />
        {busy && <span className="badge badge-accent">loading…</span>}
        <span className="text-2xs text-faint">
          Evidence available for review — a qualified human approves the links.
        </span>
      </header>

      {error && <p className="font-mono text-xs text-warn">{error}</p>}

      {view === "requirements" ? (
        <RequirementsView
          requirements={requirements}
          matrix={matrix}
          coverage={coverage}
          orphans={orphans}
        />
      ) : (
        <TestsView runs={runs} results={results} clusters={clusters} findings={findings} />
      )}
    </div>
  );
}

function RequirementsView({
  requirements,
  matrix,
  coverage,
  orphans,
}: {
  requirements: TraceRequirement[];
  matrix: TraceMatrix | null;
  coverage: TraceCoverage | null;
  orphans: TraceOrphans | null;
}) {
  if (requirements.length === 0) {
    return (
      <div className="empty-state">
        <p className="text-sm text-fg">No requirement has been ingested yet.</p>
        <p className="max-w-xl text-xs text-muted">
          Post a CSV or JSON export to <code className="font-mono">/api/v2/requirements/ingest</code>.
          Requirement identifiers that already exist in the specification corpus stay searchable in the
          assistant.
        </p>
      </div>
    );
  }
  const rows = matrix?.rows ?? [];
  return (
    <div className="space-y-4">
      {coverage && (
        <section className="panel px-3 py-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Coverage</h3>
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            <Stat label="requirements" value={coverage.requirements} />
            <Stat label="with accepted link" value={coverage.with_accepted_link} tone="good" />
            <Stat label="proposed only" value={coverage.with_proposed_link_only} tone="warn" />
            <Stat label="without any link" value={coverage.without_any_link} tone="bad" />
          </div>
          <p className="mt-2 text-2xs text-faint">{coverage.statement}</p>
        </section>
      )}

      {orphans && (
        <section className="panel px-3 py-3">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Orphans</h3>
          <p className="text-2xs text-faint">{orphans.statement}</p>
          <ul className="mt-2 space-y-1 font-mono text-xs text-fg">
            {orphans.orphan_requirements.map((r) => (
              <li key={r.id}>
                {r.id} <span className="text-faint">— {r.title || "no title"}</span>
              </li>
            ))}
            {orphans.orphan_test_cases.map((t) => (
              <li key={t.id} className="text-warn">
                {t.name || t.id} <span className="text-faint">— test case without a requirement</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="panel overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-ink-800/60 text-2xs uppercase tracking-wide text-muted">
            <tr>
              <th className="px-3 py-2">Requirement</th>
              <th className="px-3 py-2">Title</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Test cases</th>
              <th className="px-3 py-2">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.requirement_id} className="border-t border-edge/50">
                <td className="px-3 py-1.5 font-mono">{row.requirement_id}</td>
                <td className="px-3 py-1.5">{row.title}</td>
                <td className="px-3 py-1.5 text-muted">{row.status || "—"}</td>
                <td className="px-3 py-1.5 font-mono text-muted">
                  {row.test_cases.length ? row.test_cases.map((t) => t.name).join(", ") : "—"}
                </td>
                <td className="px-3 py-1.5">
                  <span
                    className={
                      row.evidence === "available for review"
                        ? "badge badge-good"
                        : "badge badge-warn"
                    }
                  >
                    {row.evidence}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function TestsView({
  runs,
  results,
  clusters,
  findings,
}: {
  runs: TestRunRow[];
  results: TestResultRow[];
  clusters: FailureCluster[];
  findings: FindingRow[];
}) {
  if (runs.length === 0) {
    return (
      <div className="empty-state">
        <p className="text-sm text-fg">No test run has been ingested yet.</p>
        <p className="max-w-xl text-xs text-muted">
          Post a JUnit XML report or a CSV result file to{" "}
          <code className="font-mono">/api/v2/tests/ingest</code>. Failures are clustered by message
          shape, so the same defect is reported once instead of once per test case.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <section className="panel px-3 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Runs</h3>
        <ul className="space-y-1 font-mono text-xs text-fg">
          {runs.map((r) => (
            <li key={r.id}>
              {r.id} <span className="text-faint">— {r.tool}, {r.suite || "no suite"}</span>
              {r.summary ? (
                <span className="ml-2 text-muted">
                  {r.summary.passed}/{r.summary.total} passed
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel px-3 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
          Failure clusters
        </h3>
        {clusters.length === 0 ? (
          <p className="text-2xs text-faint">No failure clusters in this run.</p>
        ) : (
          <ul className="space-y-2">
            {clusters.map((c) => (
              <li key={c.key} className="rounded border border-edge/60 bg-ink-900/60 px-2.5 py-2">
                <div className="flex items-center gap-2">
                  <span className="badge badge-bad">{c.count}×</span>
                  <span className="font-mono text-xs text-fg">{c.key}</span>
                </div>
                {c.examples.length > 0 && (
                  <p className="mt-1 text-2xs text-muted">{c.examples[0].message}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel px-3 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Results</h3>
        <ul className="space-y-1 font-mono text-xs">
          {results.slice(0, 50).map((r) => (
            <li key={r.id} className="flex items-center gap-2">
              <span
                className={
                  r.status === "passed"
                    ? "badge badge-good"
                    : r.status === "failed" || r.status === "error"
                      ? "badge badge-bad"
                      : "badge badge-warn"
                }
              >
                {r.status}
              </span>
              <span className="text-fg">{r.name}</span>
              {r.message && <span className="text-faint">— {r.message}</span>}
            </li>
          ))}
        </ul>
      </section>

      <section className="panel px-3 py-3">
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Findings</h3>
        {findings.length === 0 ? (
          <p className="text-2xs text-faint">No finding has been raised.</p>
        ) : (
          <ul className="space-y-2">
            {findings.map((f) => (
              <li key={f.id} className="rounded border border-edge/60 bg-ink-900/60 px-2.5 py-2">
                <div className="flex items-center gap-2">
                  <span className="badge badge-warn">{f.severity}</span>
                  <span className="text-xs text-fg">{f.title}</span>
                </div>
                {f.summary && <p className="mt-1 text-2xs text-muted">{f.summary}</p>}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone?: "good" | "warn" | "bad";
}) {
  const cls = tone === "good" ? "text-good" : tone === "warn" ? "text-warn" : tone === "bad" ? "text-bad" : "text-fg";
  return (
    <div className="rounded border border-edge/60 bg-ink-900/50 px-2.5 py-2">
      <div className={`text-lg font-semibold ${cls}`}>{value}</div>
      <div className="text-2xs uppercase tracking-wide text-faint">{label}</div>
    </div>
  );
}
