"use client";
import { useEffect, useId, useState } from "react";

let mermaidInit: Promise<typeof import("mermaid")> | null = null;

function loadMermaid() {
  if (!mermaidInit) {
    mermaidInit = import("mermaid").then((mod) => {
      const mermaid = mod.default;
      mermaid.initialize({
        startOnLoad: false,
        theme: "dark",
        themeVariables: {
          background: "#0D1320",
          primaryColor: "#00F5FF",
          primaryTextColor: "#F1F5F9",
          lineColor: "#64748B",
        },
        flowchart: { useMaxWidth: true },
        securityLevel: "strict",
      });
      return mod;
    });
  }
  return mermaidInit;
}

export function MermaidDiagram({ chart }: { chart: string }) {
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setError(null);
    const code = chart.trim();
    if (!code) {
      setError("Empty diagram.");
      return;
    }
    loadMermaid()
      .then(({ default: mermaid }) => mermaid.render(`asr-mmd-${id}`, code))
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Diagram failed to render.");
      });
    return () => {
      cancelled = true;
    };
  }, [chart, id]);

  if (error) {
    return (
      <div className="overflow-hidden rounded border border-[#F59E0B]/40 bg-[#121824]">
        <div className="flex items-center justify-between border-b border-[#F59E0B]/30 px-3 py-1.5">
          <span className="font-mono text-xs text-[#F59E0B]">
            Diagram could not be rendered — showing source
          </span>
          <button
            className="rounded border border-[#222D3F] px-2 py-0.5 font-mono text-xs hover:border-[#00F5FF]/60"
            onClick={() => {
              void navigator.clipboard?.writeText(chart).then(() => {
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              });
            }}
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
        <pre className="max-h-72 overflow-auto p-3 font-mono text-xs text-[#F1F5F9]/90">
          <code>{chart}</code>
        </pre>
        <p className="px-3 pb-2 font-mono text-[11px] text-[#F1F5F9]/50">{error}</p>
      </div>
    );
  }

  if (!svg) {
    // Reserved box prevents raw text flash + layout shift while compiling.
    return (
      <div
        className="flex min-h-[120px] items-center justify-center rounded border border-[#222D3F] bg-[#0D1320]"
        aria-label="Rendering diagram"
        role="status"
      >
        <span className="animate-pulse font-mono text-xs text-[#00F5FF]">
          Rendering diagram…
        </span>
      </div>
    );
  }

  return (
    <div
      className="overflow-x-auto rounded border border-[#222D3F] bg-[#0D1320] p-3 [&>svg]:h-auto [&>svg]:max-w-full"
      // mermaid emits sanitized SVG (securityLevel strict); required for vector rendering.
      dangerouslySetInnerHTML={{ __html: svg }}
      role="img"
      aria-label="Mermaid diagram"
    />
  );
}
