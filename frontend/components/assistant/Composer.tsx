"use client";
import { useEffect, useRef } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  streaming: boolean;
  mode: "ask" | "diagnose";
  onMode: (m: "ask" | "diagnose") => void;
  disabled?: boolean;
  placeholder?: string;
}

/**
 * Chat composer. Enter sends, Shift+Enter inserts a newline. The textarea
 * grows with the content so long questions stay readable.
 */
export function Composer({
  value,
  onChange,
  onSend,
  onStop,
  streaming,
  mode,
  onMode,
  disabled,
  placeholder,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  function keyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!streaming && !disabled) onSend();
    }
  }

  return (
    <div className="border-t border-edge/60 bg-ink-850/50 px-4 py-3 backdrop-blur">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2">
          <div className="relative flex-1">
            <textarea
              ref={ref}
              className="input min-h-[46px] resize-none pr-16 leading-6"
              rows={1}
              value={value}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={keyDown}
              placeholder={
                placeholder ??
                (mode === "diagnose"
                  ? "Describe the symptom — e.g. “a periodic signal times out intermittently”…"
                  : "Ask about the AUTOSAR corpus — e.g. “which requirements govern Com signal transmission?”…")
              }
            />
            <div className="absolute bottom-2 right-2 flex gap-1">
              <button
                className={`chip ${mode === "ask" ? "chip-active" : ""}`}
                onClick={() => onMode("ask")}
                title="Ask the corpus a question"
              >
                Ask
              </button>
              <button
                className={`chip ${mode === "diagnose" ? "chip-active" : ""}`}
                onClick={() => onMode("diagnose")}
                title="Triage a reported symptom against the specification"
              >
                Diagnose
              </button>
            </div>
          </div>

          {streaming ? (
            <button className="btn btn-icon h-11 w-11" onClick={onStop} title="Stop generating">
              ■
            </button>
          ) : (
            <button
              className="btn btn-primary h-11 w-11"
              onClick={onSend}
              disabled={disabled || !value.trim()}
              title="Send"
            >
              ↑
            </button>
          )}
        </div>
        <p className="mt-1.5 text-2xs text-faint">
          {mode === "diagnose"
            ? "Diagnose mode classifies the symptom, retrieves the governing passages and proposes checks and candidate fixes."
            : "Enter to send · Shift+Enter for a new line · every claim is cited to a document and page."}
        </p>
      </div>
    </div>
  );
}
