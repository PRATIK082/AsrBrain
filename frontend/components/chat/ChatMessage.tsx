"use client";
import { memo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { MermaidDiagram } from "./MermaidDiagram";

function CopyableCode({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="overflow-hidden rounded border border-[#222D3F] bg-[#070A0F]">
      <div className="flex items-center justify-between border-b border-[#222D3F] px-3 py-1.5">
        <span className="font-mono text-[11px] uppercase tracking-wide text-[#F1F5F9]/50">
          {language || "code"}
        </span>
        <button
          className="rounded border border-[#222D3F] px-2 py-0.5 font-mono text-xs hover:border-[#00F5FF]/60"
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
      <pre className="max-h-96 overflow-auto p-3 font-mono text-xs leading-relaxed text-[#F1F5F9]/90">
        <code>{code}</code>
      </pre>
    </div>
  );
}

/**
 * Stable chat markdown: GFM tables/lists, mermaid -> SVG, streaming-safe.
 * The outer wrapper pins min-height + break-words so token streaming
 * does not cause choppy layout shifts.
 */
export const ChatMessage = memo(function ChatMessage({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
}) {
  return (
    <div
      className={`min-h-[48px] break-words text-sm leading-relaxed text-[#F1F5F9] ${
        streaming ? "asr-streaming" : ""
      } prose prose-invert max-w-none prose-pre:bg-transparent prose-pre:p-0 prose-table:block prose-table:overflow-x-auto`}
    >
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
              // Suppress incomplete fence while streaming to avoid partial-parse flash.
              if (streaming && !/```/.test(content) && raw.split("\n").length < 2) {
                return (
                  <span className="font-mono text-xs text-[#00F5FF]">
                    Preparing diagram…
                  </span>
                );
              }
              return <MermaidDiagram chart={raw} />;
            }
            if (raw.includes("\n")) {
              return <CopyableCode code={raw} language={lang} />;
            }
            return (
              <code className="rounded bg-[#121824] px-1 py-0.5 font-mono text-[13px] text-[#00F5FF]">
                {raw}
              </code>
            );
          },
          // Keep tables/lists inside scroll-stable containers.
          table(props) {
            return (
              <div className="overflow-x-auto rounded border border-[#222D3F]">
                <table className="w-full border-collapse text-sm" {...props} />
              </div>
            );
          },
          a(props) {
            return (
              <a
                {...props}
                target="_blank"
                rel="noreferrer"
                className="text-[#00F5FF] underline underline-offset-2"
              />
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
});
