import type {
  AgentEvent, AgentRunResult, AgentWorkflow, ChatRequest, GraphNode, GraphQueryResult,
  GraphStats, MindmapResult, StreamEvent, ToolListResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) } });
  if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
  return r.json() as Promise<T>;
}

export const api = {
  conversations: () => json("/api/conversations"),
  createConversation: (title = "New conversation") => json("/api/conversations", { method: "POST", body: JSON.stringify({ title }) }),
  chat: (req: ChatRequest) => json("/api/chat", { method: "POST", body: JSON.stringify(req) }),
  stop: (conversation_id: string) => json("/api/chat/stop", { method: "POST", body: JSON.stringify({ conversation_id }) }),
  feedback: (conversation_id: string, message_idx: number, rating: string, note = "") =>
    json("/api/feedback", { method: "POST", body: JSON.stringify({ conversation_id, message_idx, rating, note }) }),
  models: () => json("/api/models"),
  releases: () => json("/api/releases"),
  policies: () => json("/api/policies/effective"),
  arxmlArtifacts: (tenant = "default") => json(`/api/arxml/artifacts?tenant=${tenant}`),
  arxmlTopology: (artifact_id: string, tenant = "default") =>
    json(`/api/arxml/topology?artifact_id=${artifact_id}&tenant=${tenant}`),
  arxmlNeighbors: (node_id: string, artifact_id: string, tenant = "default") =>
    json(`/api/arxml/nodes/${encodeURIComponent(node_id)}/neighbors?artifact_id=${artifact_id}&tenant=${tenant}`),
  diff: (base: object[], target: object[], domain = "api") =>
    json("/api/diff", { method: "POST", body: JSON.stringify({ base, target, domain }) }),
  codeAnalyze: (source: string, path = "input.c", port_names: string[] = []) =>
    json("/api/code/analyze", { method: "POST", body: JSON.stringify({ source, path, port_names }) }),
  sarifUpload: (sarif: object) =>
    json("/api/code/sarif", { method: "POST", body: JSON.stringify({ sarif }) }),
  diagramAnalyze: (image_path: string, caption = "", page = 0, document_id = "") =>
    json("/api/diagrams/analyze", { method: "POST", body: JSON.stringify({ image_path, caption, page, document_id }) }),

  /* --------------------------------------------------- GraphRAG + agent tools */
  tools: () => json<ToolListResponse>("/api/tools"),
  invokeTool: (name: string, args: Record<string, unknown> = {}, allow_mutating = false) =>
    json<{ ok: boolean; tool: string; data?: unknown; error?: string; duration_ms?: number }>(
      `/api/tools/${encodeURIComponent(name)}`,
      { method: "POST", body: JSON.stringify({ args, allow_mutating }) },
    ),
  mindmap: (topic: string, source = "auto", depth = 2, outline?: { label: string; children?: { label: string }[] }[]) =>
    json<MindmapResult>("/api/mindmap", { method: "POST", body: JSON.stringify({ topic, source, depth, outline }) }),
  graphBuild: (canonical_db = "", code_dirs: string[] = [], clear = true) =>
    json<Record<string, unknown>>("/api/graph/build", { method: "POST", body: JSON.stringify({ canonical_db, code_dirs, clear }) }),
  graphStats: () => json<GraphStats>("/api/graph/stats"),
  graphQuery: (query: string, mode = "hybrid", depth = 2, limit = 25) =>
    json<GraphQueryResult>("/api/graph/query", { method: "POST", body: JSON.stringify({ query, mode, depth, limit }) }),
  graphNode: (node_id: string, depth = 1, limit = 120) =>
    json<{ node: GraphNode; nodes: GraphNode[]; edges: Record<string, unknown>[] }>(
      `/api/graph/node/${encodeURIComponent(node_id)}?depth=${depth}&limit=${limit}`,
    ),
  agentWorkflows: () => json<{ workflows: AgentWorkflow[]; count: number }>("/api/agent/workflows"),
  agentRun: (body: {
    query: string; workflow?: string; mode?: string; context?: Record<string, unknown>;
    provider?: string; model?: string; base_url?: string; api_key?: string;
    allow_mutating?: boolean; max_steps?: number;
  }) => json<AgentRunResult>("/api/agent/run", { method: "POST", body: JSON.stringify(body) }),
};

/** SSE reader for POST /api/chat/stream — yields parsed StreamEvents. */
export async function* streamChat(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<StreamEvent> {
  const r = await fetch(`${BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...req, stream: true }),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`stream ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const p of parts) {
      const line = p.split("\n").find((l) => l.startsWith("data:"));
      if (line) yield JSON.parse(line.slice(5)) as StreamEvent;
    }
  }
}

/** SSE reader for POST /api/agent/stream — yields agent loop events. */
export async function* streamAgent(
  body: {
    query: string; workflow?: string; mode?: string; context?: Record<string, unknown>;
    provider?: string; model?: string; base_url?: string; api_key?: string;
    allow_mutating?: boolean; max_steps?: number;
  },
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  const r = await fetch(`${BASE}/api/agent/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) throw new Error(`stream ${r.status}`);
  const reader = r.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop() ?? "";
    for (const p of parts) {
      const line = p.split("\n").find((l) => l.startsWith("data:"));
      if (line) yield JSON.parse(line.slice(5)) as AgentEvent;
    }
  }
}
