"use client";
import { useEffect, useState } from "react";
import { api } from "../lib/api";

export function AdminView() {
  const [ctx, setCtx] = useState<any>(null);
  const [metrics, setMetrics] = useState<any>(null);

  useEffect(() => {
    api.context().then(setCtx).catch(() => setCtx(null));
    api.adminMetrics().then(setMetrics).catch(() => setMetrics(null));
  }, []);

  return (
    <div className="space-y-4 p-6">
      <h2 className="font-mono text-lg text-[#00F5FF]">Admin</h2>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded border border-[#1F2937] p-3">
          <h3 className="mb-2 text-sm font-semibold">Profile</h3>
          <p className="text-xs">{ctx?.profile ?? "unknown"}</p>
          <p className="text-xs text-[#A0A0A0]">Health: {ctx?.health?.canonical_db}</p>
        </div>
        <div className="rounded border border-[#1F2937] p-3">
          <h3 className="mb-2 text-sm font-semibold">Metrics</h3>
          <p className="text-xs">Requests: {metrics?.requests ?? 0}</p>
          <p className="text-xs">Errors: {metrics?.errors ?? 0}</p>
          <p className="text-xs">Avg latency: {metrics?.avg_latency_ms ?? 0} ms</p>
        </div>
      </div>
      <div className="rounded border border-[#1F2937] p-3">
        <h3 className="mb-2 text-sm font-semibold">Backup</h3>
        <p className="text-xs text-[#A0A0A0]">POST/GET /api/admin/backup creates a zip in data/backups.</p>
      </div>
    </div>
  );
}