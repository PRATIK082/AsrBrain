"use client";

import { useEffect, useState } from "react";
import { api } from "../../lib/api";
import type {
  EvalAggregate, EvalCategoryBlock, EvalCoverage, EvalGate, EvalLatest, EvalRunSummary,
  EvalWorstRow,
} from "../../lib/types";

const HEADLINE: { key: string; label: string; target?: string }[] = [
  { key: "context_recall", label: "Context recall" },
  { key: "citation_precision", label: "Citation precision", target: ">= 0.98 (S3)" },
  { key: "faithfulness", label: "Faithfulness", target: ">= 0.97 (S3)" },
  { key: "answer_correctness", label: "Answer correctness", target: ">= 0.95 (S3)" },
  { key: "abstention_accuracy", label: "Abstention accuracy", target: ">= 0.95 (S3)" },
  { key: "hallucinated_id_rate_mean", label: "Hallucinated-id rate", target: "<= 0.005 (S3)" },
];

function metricValue(block: EvalAggregate | undefined, key: string): number | null {
  if (!block) return null;
  const raw = (block as unknown as Record<string, unknown>)[key];
  if (raw === null || raw === undefined) return null;
  if (typeof raw === "number") return raw;
  const m = raw as { value?: number | null };
  return m.value ?? null;
}

function metricCi(block: EvalAggregate | undefined, key: string): string {
  if (!block) return "";
  const raw = (block as unknown as Record<string, unknown>)[key];
  if (!raw || typeof raw === "number") return "";
  const m = raw as { ci95?: [number, number] | null; n?: number };
  if (!m.ci95) return "";
  return "[" + m.ci95[0] + " - " + m.ci95[1] + "] (n=" + m.n + ")";
}

function Block(props: { label: string; value: number | null; ci: string; target?: string }) {
  return (
    <div className="rounded border p-3">
      <div className="text-xs text-gray-500">{props.label}</div>
      <div className="text-2xl font-semibold">
        {props.value === null ? "not measured" : props.value}
      </div>
      <div className="text-xs text-gray-500">{props.ci || "-"}</div>
      {props.target ? <div className="text-xs text-gray-400">target {props.target}</div> : null}
    </div>
  );
}

export default function EvaluationView() {
  const [latest, setLatest] = useState<EvalLatest | null>(null);
  const [runs, setRuns] = useState<EvalRunSummary[]>([]);
  const [gate, setGate] = useState<EvalGate | null>(null);
  const [coverage, setCoverage] = useState<EvalCoverage | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const [l, r, g, c] = await Promise.all([
          api.evaluationLatest() as Promise<EvalLatest>,
          api.evaluationRuns() as Promise<{ runs: EvalRunSummary[] }>,
          api.evaluationGate() as Promise<{ gate: EvalGate | null }>,
          api.evaluationGolden() as Promise<{ available: boolean; coverage?: EvalCoverage }>,
        ]);
        if (!alive) return;
        setLatest(l);
        setRuns(r.runs ?? []);
        setGate(g.gate);
        setCoverage(c.coverage ?? null);
      } catch (e) {
        if (alive) setError(String(e));
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  if (error) {
    return (
      <section className="flex-1 space-y-3 overflow-y-auto p-6">
        <h2 className="font-bold">Evaluation</h2>
        <p className="rounded border border-red-400 p-3 text-sm">
          The evaluation API is unreachable: {error}
        </p>
      </section>
    );
  }

  if (!latest || !latest.available) {
    return (
      <section className="flex-1 space-y-3 overflow-y-auto p-6">
        <h2 className="font-bold">Evaluation</h2>
        <p className="rounded border p-3 text-sm text-gray-500">
          No evaluation run has been recorded yet. {latest ? latest.hint : ""}
        </p>
        <pre className="rounded border p-3 text-xs">
          {"python -m src.evaluation.build --canonical data/canonical/canonical.db\npython -m src.evaluation.cli run --mode retrieval --label baseline"}
        </pre>
      </section>
    );
  }

  const agg = latest.aggregate;
  const worst: EvalWorstRow[] = latest.worst ?? [];

  return (
    <section className="flex-1 space-y-6 overflow-y-auto p-6">
      <header className="space-y-1">
        <h2 className="font-bold">Evaluation</h2>
        <p className="text-xs text-gray-500">
          run <b>{latest.label}</b> | {latest.generated_at} | mode {latest.mode} | split {latest.split} | llm{" "}
          {latest.llm_model ?? "none"} | golden {latest.golden_sha256 ? latest.golden_sha256.slice(0, 12) : "-"}
        </p>
        {latest.split_drift && latest.split_drift.length ? (
          <p className="rounded border border-amber-400 p-2 text-xs">
            Split drift: {latest.split_drift.join("; ")}
          </p>
        ) : null}
      </header>

      <div className="grid grid-cols-3 gap-3">
        {HEADLINE.map((h) => (
          <Block
            key={h.key}
            label={h.label}
            value={metricValue(agg, h.key)}
            ci={metricCi(agg, h.key)}
            target={h.target}
          />
        ))}
      </div>

      {gate ? (
        <section className="space-y-2">
          <h3 className="font-semibold">CI gate - {gate.passed ? "PASSED" : "FAILED"}</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left">
                <th className="border-t p-1">metric</th>
                <th className="border-t p-1">measured</th>
                <th className="border-t p-1">threshold</th>
                <th className="border-t p-1">status</th>
              </tr>
            </thead>
            <tbody>
              {gate.checks.map((c) => (
                <tr key={c.metric}>
                  <td className="border-t p-1">{c.metric}</td>
                  <td className="border-t p-1">{c.measured === undefined ? "-" : c.measured}</td>
                  <td className="border-t p-1">
                    {c.threshold === undefined ? "-" : c.threshold}{" "}
                    {c.direction ? "(" + c.direction + ")" : ""} +-{c.tolerance === undefined ? 0 : c.tolerance}
                  </td>
                  <td className="border-t p-1">{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}

      {coverage ? (
        <section className="space-y-2">
          <h3 className="font-semibold">Golden set coverage (S9 targets)</h3>
          <p className="text-xs text-gray-500">
            n={coverage.n} | answerable {coverage.answerable} | unanswerable {coverage.unanswerable} | awaiting
            expert review {coverage.needs_expert_review} |{" "}
            {coverage.meets_coverage_targets ? "all targets met" : "targets not met"}
          </p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(coverage.mix).map(([slice, share]) => (
              <span key={slice} className="rounded border px-2 py-1 text-xs">
                {slice}: {(share * 100).toFixed(1)}%
              </span>
            ))}
          </div>
        </section>
      ) : null}

      {agg ? (
        <section className="space-y-2">
          <h3 className="font-semibold">Per category</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left">
                <th className="border-t p-1">category</th>
                <th className="border-t p-1">n</th>
                <th className="border-t p-1">ctx recall</th>
                <th className="border-t p-1">citation prec</th>
                <th className="border-t p-1">faithfulness</th>
                <th className="border-t p-1">abstention acc</th>
                <th className="border-t p-1">failures</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(agg.by_category).map(([cat, block]) => {
                const b = block as EvalCategoryBlock;
                return (
                  <tr key={cat}>
                    <td className="border-t p-1">{cat}</td>
                    <td className="border-t p-1">{b.n}</td>
                    <td className="border-t p-1">{b.context_recall.value === null ? "-" : b.context_recall.value}</td>
                    <td className="border-t p-1">{b.citation_precision.value === null ? "-" : b.citation_precision.value}</td>
                    <td className="border-t p-1">{b.faithfulness.value === null ? "-" : b.faithfulness.value}</td>
                    <td className="border-t p-1">
                      {b.abstention_accuracy.value === null ? "-" : b.abstention_accuracy.value}
                    </td>
                    <td className="border-t p-1">
                      {Object.entries(b.failures)
                        .filter(([k]) => k !== "ok")
                        .map(([k, v]) => k + "=" + v)
                        .join(", ") || "-"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}

      <section className="space-y-2">
        <h3 className="font-semibold">20 worst failures</h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left">
              <th className="border-t p-1">query</th>
              <th className="border-t p-1">category</th>
              <th className="border-t p-1">failure</th>
              <th className="border-t p-1">ctx recall</th>
              <th className="border-t p-1">latency</th>
              <th className="border-t p-1">question</th>
            </tr>
          </thead>
          <tbody>
            {worst.map((w) => (
              <tr key={w.query_id}>
                <td className="border-t p-1">{w.query_id}</td>
                <td className="border-t p-1">{w.category}</td>
                <td className="border-t p-1">{w.failure}</td>
                <td className="border-t p-1">{w.context_recall}</td>
                <td className="border-t p-1">{w.latency_s}s</td>
                <td className="border-t p-1">{w.question.slice(0, 80)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {runs.length ? (
        <section className="space-y-2">
          <h3 className="font-semibold">Run history</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left">
                <th className="border-t p-1">label</th>
                <th className="border-t p-1">when</th>
                <th className="border-t p-1">mode</th>
                <th className="border-t p-1">n</th>
                <th className="border-t p-1">ctx recall</th>
                <th className="border-t p-1">citation prec</th>
                <th className="border-t p-1">p95</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.label + r.generated_at}>
                  <td className="border-t p-1">{r.label}</td>
                  <td className="border-t p-1">{r.generated_at}</td>
                  <td className="border-t p-1">{r.mode}</td>
                  <td className="border-t p-1">{r.n}</td>
                  <td className="border-t p-1">{r.context_recall === null ? "-" : r.context_recall}</td>
                  <td className="border-t p-1">{r.citation_precision === null ? "-" : r.citation_precision}</td>
                  <td className="border-t p-1">{r.latency_p95_s}s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
    </section>
  );
}
