import React from 'react';
import type { PipelineStageEvent } from '../../hooks/useAsrStream';

/** Minimal inline status glyphs (avoids adding an icon dependency). */
const Spin: React.FC = () => (
  <svg className="h-3.5 w-3.5 animate-spin text-[#00F5FF]" viewBox="0 0 24 24" fill="none" aria-hidden>
    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
    <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
  </svg>
);
const Check: React.FC = () => (
  <svg className="h-3.5 w-3.5 text-[#10B981]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);
const Fail: React.FC = () => (
  <svg className="h-3.5 w-3.5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
  </svg>
);
const Pulse: React.FC = () => (
  <svg className="h-3.5 w-3.5 text-[#00F5FF]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h4l3-8 4 16 3-8h4" />
  </svg>
);

const STAGE_META: Record<string, string> = {
  query_understanding: 'Normalizing Intent Matrix',
  retrieval_planning: 'Profiling Query Intent & Version Slots',
  text_retrieval: 'Dense + BM25 Candidate Sweep',
  table_retrieval: 'Parameter Table / Figure Store Check',
  graph_retrieval: 'Module / API Relationship Traversal',
  fusion_rerank: 'Executing RRF Hybrid Core Search',
  expansion_compression: 'Hydrating Architecture Block Tree',
  parent_expansion: 'Hydrating Architecture Block Tree',
  clarify_check: 'Evaluating Core Parameter Slots',
  answer_drafting: 'Synthesizing Cited Draft',
  citation_validation: 'Validating Claims Against Evidence',
  verification: 'Applying Safety Guardrails',
  confidence: 'Scoring Confidence / Abstain Gate',
  generation: 'Synthesizing Solution Suite',
  policy: 'Evaluating Routing & Data Policy',
  routing: 'Evaluating Routing & Data Policy',
};

export const PipelineTelemetry: React.FC<{ stages: PipelineStageEvent[] }> = ({ stages }) => {
  if (stages.length === 0) return null;
  return (
    <div className="rounded-lg border border-[#222D3F] bg-[#121824] p-3">
      <div className="mb-2 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-widest text-[#F1F5F9]/70">
        <Pulse />
        AsrBrain Multi-Agent Processing Trace
      </div>
      <div className="space-y-1.5">
        {stages.map((item) => (
          <div
            key={item.stage}
            className={`flex items-center justify-between rounded-lg border p-2 font-mono text-xs transition-all duration-300 ${
              item.status === 'active'
                ? 'border-cyan-500/30 bg-cyan-950/20 text-[#F1F5F9]'
                : item.status === 'completed'
                  ? 'border-slate-800/60 bg-slate-900/40 text-[#F1F5F9]/70'
                  : 'border-rose-500/20 bg-rose-950/10 text-rose-300'
            }`}
          >
            <span className="flex items-center gap-2">
              {item.status === 'active' ? <Spin /> : item.status === 'completed' ? <Check /> : <Fail />}
              <span>
                <span className="text-[#F1F5F9]">{STAGE_META[item.stage] || item.stage}</span>
                <span className="ml-2 text-[#F1F5F9]/50">{item.message}</span>
              </span>
            </span>
            <span className="text-[10px] uppercase tracking-wider text-[#F1F5F9]/40">{item.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
