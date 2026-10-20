"use client";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MermaidDiagram } from "../chat/MermaidDiagram";

function CopyableCode({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="overflow-hidden rounded-lg border border-edge/70 bg-ink-950/70">
      <div className="flex items-center justify-between border-b border-edge/60 px-3 py-1.5">
        <span className="font-mono text-2xs uppercase tracking-wide text-faint">
          {language || "code"}
        </span>
        <button
          className="btn btn-ghost btn-xs"
          onClick={() => {
            void navigator.clipboard?.writeText(code).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="scrollbar-thin max-h-96 overflow-auto p-3 font-mono text-xs leading-relaxed text-fg/80">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Answer body: GFM markdown rendered with the product's own typography scope
 * (`.md`), mermaid fences become diagrams, code blocks are copyable.
 */
export const Markdown = memo(function Markdown({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  return (
    <div className="md break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code(props) {
            const { className, children } = props as {
              className?: string;
              children?: React.ReactNode;
            };
            const raw = String(children ?? "").replace(/\n$/, "");
            const match = /language-([\w-]+)/.exec(className || "");
            const lang = (match?.[1] || "").toLowerCase();
            if (lang === "mermaid") {
              if (streaming && !/```/.test(content) && raw.split("\n").length < 2) {
                return <span className="font-mono text-xs text-accent">Preparing diagram…</span>;
              }
              return <MermaidDiagram chart={raw} />;
            }
            if (raw.includes("\n")) {
              return <CopyableCode code={raw} language={lang} />;
            }
            return <code className="rounded bg-ink-700/70 px-1.5 py-0.5 font-mono text-[13px] text-accent">{raw}</code>;
          },
          table(props) {
            return (
              <div className="overflow-x-auto rounded-lg border border-edge/60">
                <table className="w-full border-collapse text-sm" {...props} />
              </div>
            );
          },
          a(props) {
            return <a {...props} target="_blank" rel="noreferrer" className="text-accent underline underline-offset-2" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
