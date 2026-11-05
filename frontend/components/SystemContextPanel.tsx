"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Ctx = {
  profile?: string;
  health?: Record<string, string>;
  recommended_actions?: string[];
  features?: { id: string; name: string; status: string; category?: string }[];
  data?: { counts?: Record<string, number> };
  models?: { llm_model?: string; ollama?: { status?: string } };
};

export function SystemContextPanel() {
  const [ctx, setCtx] = useState<Ctx | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .context()
      .then((d) => {
        if (!cancelled) setCtx(d as Ctx);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "Failed to load context");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const healthOk = ctx?.health && Object.values(ctx.health).every((v) => v === "ok");
  return (
    <div className="border-b border-[#222D3F] bg-[#121824] px-4 py-2 text-xs">
      <button
        className="flex w-full items-center justify-between font-mono text-[#F1F5F9]/70 hover:text-[#00F5FF]"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>
          System: {ctx?.profile ?? "…"} · {healthOk ? "healthy" : "check setup"} · {ctx?.models?.llm_model ?? ""}
        </span>
        <span>{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <div className="mt-2 grid gap-2 md:grid-cols-3">
          <div className="rounded border border-[#222D3F] bg-[#0D1320] p-2">
            <div className="mb-1 font-mono text-[#00F5FF]">Health</div>
            {ctx?.health &&
              Object.entries(ctx.health).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span>{k}</span>
                  <span className={v === "ok" ? "text-green-400" : "text-amber-400"}>{v}</span>
                </div>
              ))}
            {err && <div className="text-red-400">{err}</div>}
          </div>
          <div className="rounded border border-[#222D3F] bg-[#0D1320] p-2">
            <div className="mb-1 font-mono text-[#00F5FF]">Recommended</div>
            <ul className="list-disc pl-4">
              {(ctx?.recommended_actions ?? []).map((a, i) => (
                <li key={i}>{a}</li>
              ))}
              {!ctx?.recommended_actions?.length && <li>Nothing to do — looks good.</li>}
            </ul>
          </div>
          <div className="rounded border border-[#222D3F] bg-[#0D1320] p-2">
            <div className="mb-1 font-mono text-[#00F5FF]">Features</div>
            <ul className="space-y-1">
              {(ctx?.features ?? []).map((f) => (
                <li key={f.id} className="flex justify-between">
                  <span>{f.name}</span>
                  <span
                    className={
                      f.status === "available"
                        ? "text-green-400"
                        : f.status === "needs_setup"
                        ? "text-amber-400"
                        : "text-[#F1F5F9]/40"
                    }
                  >
                    {f.status}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}