import React, { useState } from 'react';
import type { StreamEvidence, StreamVerdict } from '../../hooks/useAsrStream';

/** Minimal inline glyphs (avoids adding an icon dependency). */
const ChevD: React.FC = () => (
  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 9l6 6 6-6" />
  </svg>
);
const ChevR: React.FC = () => (
  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 6l6 6-6 6" />
  </svg>
);
const Doc: React.FC = () => (
  <svg className="h-4 w-4 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M7 3h7l5 5v13a1 1 0 01-1 1H7a1 1 0 01-1-1V4a1 1 0 011-1z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M14 3v5h5" />
  </svg>
);
const Shield: React.FC = () => (
  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3l7 3v5c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z" />
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4" />
  </svg>
);
const Warn: React.FC = () => (
  <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 3L2 21h20L12 3z" />
    <path strokeLinecap="round" d="M12 10v4M12 17.5v.5" />
  </svg>
);
const CopyIco: React.FC = () => (
  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path strokeLinecap="round" d="M5 15V5a2 2 0 012-2h10" />
  </svg>
);
const DoneIco: React.FC = () => (
  <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
  </svg>
);

export const AsrCitationDrawer: React.FC<{ sources: StreamEvidence[]; verdict: StreamVerdict }> = ({
  sources,
  verdict,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [activePreview, setActivePreview] = useState<StreamEvidence | null>(null);

  if (sources.length === 0) return null;

  const handleCopyReq = (id: string, text: string) => {
    void navigator.clipboard?.writeText(text).then(
      () => {
        setCopiedId(id);
        setTimeout(() => setCopiedId(null), 2000);
      },
      () => undefined,
    );
  };

  const getVerdictStyles = () => {
    if (verdict === 'verified')
      return {
        bg: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400',
        icon: <Shield />,
        label: 'Grounded — Every Claim Cited',
      };
    if (verdict === 'needs_human_validation')
      return {
        bg: 'border-amber-500/30 bg-amber-500/10 text-amber-400',
        icon: <Warn />,
        label: 'Validation Gap Detected — Human Review Needed',
      };
    return {
      bg: 'border-rose-500/30 bg-rose-500/10 text-rose-400',
      icon: <Warn />,
      label: 'Abstained — Insufficient Structural Context',
    };
  };
  const status = getVerdictStyles();

  return (
    <div className="overflow-hidden rounded-lg border border-[#222D3F] bg-[#121824]">
      <div className={`flex items-center gap-2 border-b px-4 py-2.5 text-xs font-medium tracking-wide ${status.bg}`}>
        {status.icon} {status.label}
      </div>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between bg-[#121722] p-4 transition-colors hover:bg-[#161D2B]"
      >
        <span className="text-left">
          <span className="block text-sm font-semibold text-[#F1F5F9]">Grounded Source Evidences</span>
          <span className="block font-mono text-[11px] text-[#F1F5F9]/50">
            {sources.length} matching architectural references fetched
          </span>
        </span>
        <span className="flex items-center gap-2 font-mono text-[11px] text-[#00F5FF]">
          RRF-Fused {isOpen ? <ChevD /> : <ChevR />}
        </span>
      </button>

      {isOpen && (
        <div className="space-y-2 p-3">
          {sources.map((source) => (
            <div key={source.id} className="rounded-lg border border-[#222D3F] bg-[#070A0F] p-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="flex items-center gap-2 text-xs text-[#F1F5F9]">
                  <Doc />
                  <span className="rounded bg-[#182235] px-1.5 py-0.5 font-mono text-[10px] text-[#00F5FF]">
                    {source.layer}
                  </span>
                  <span className="truncate">{source.documentName}</span>
                  <span className="font-mono text-[11px] text-[#F1F5F9]/50">p. {source.pageNumber}</span>
                </span>
                {source.requirementId && (
                  <button
                    onClick={() => handleCopyReq(source.id, source.requirementId!)}
                    className="flex items-center gap-1 rounded border border-slate-700 bg-[#182235] px-2 py-0.5 font-mono text-[11px] text-slate-300 hover:text-white"
                  >
                    {copiedId === source.id ? <DoneIco /> : <CopyIco />}
                    {source.requirementId}
                  </button>
                )}
              </div>
              <p className="font-mono text-[11px] leading-relaxed text-[#F1F5F9]/70">{source.snippet}</p>
              <div className="mt-2 flex items-center gap-2">
                <span className="font-mono text-[10px] uppercase tracking-wider text-[#F1F5F9]/40">
                  Retrieval Confidence:
                </span>
                <div className="h-1.5 flex-1 rounded-full bg-slate-800">
                  <div
                    className="h-full rounded-full bg-cyan-500"
                    style={{ width: `${Math.round(source.confidenceScore * 100)}%` }}
                  />
                </div>
                <span className="font-mono text-[10px] text-[#F1F5F9]/60">
                  {(source.confidenceScore * 100).toFixed(0)}%
                </span>
                <button
                  onClick={() => setActivePreview(source)}
                  className="text-xs text-slate-400 transition-colors hover:text-cyan-400"
                >
                  Inspect Spec Node →
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {activePreview && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={() => setActivePreview(null)}>
          <div
            className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-[#222D3F] bg-[#121824] p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-semibold text-[#F1F5F9]">Specification Metadata Hub</h3>
              <button
                onClick={() => setActivePreview(null)}
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-400 hover:bg-slate-700 hover:text-white"
              >
                Close Portal
              </button>
            </div>
            <dl className="space-y-2 font-mono text-xs text-[#F1F5F9]/80">
              <div>
                <dt className="uppercase tracking-wider text-[#F1F5F9]/40">Target Module Layer</dt>
                <dd>{activePreview.layer} Engine Stack</dd>
              </div>
              <div>
                <dt className="uppercase tracking-wider text-[#F1F5F9]/40">Trace Pointer</dt>
                <dd>{activePreview.requirementId || 'Uncoded Block'}</dd>
              </div>
              <div>
                <dt className="uppercase tracking-wider text-[#F1F5F9]/40">Document / Release / Section</dt>
                <dd>
                  {activePreview.documentName} · {activePreview.release || 'unknown release'} · {activePreview.section || '—'}
                </dd>
              </div>
              <div>
                <dt className="uppercase tracking-wider text-[#F1F5F9]/40">Context Segment Data Stream</dt>
                <dd className="whitespace-pre-wrap rounded border border-[#222D3F] bg-[#070A0F] p-3">
                  {activePreview.snippet}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
};
