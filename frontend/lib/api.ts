import type {
  Answerability,
  AssistantCapabilities,
  ChatRequest,
  DiagnoseResult,
  ModuleCatalogue,
  ProjectOverview,
  StarterPromptGroup,
  StreamEvent,
  TriageCategory,
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
  deleteConversation: (id: string) => json(`/api/conversations/${id}`, { method: "DELETE" }),
  renameConversation: (id: string, title: string) =>
    json(`/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
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

  /* ---------------- institutional assistant ---------------- */

  assistantCapabilities: () => json<AssistantCapabilities>("/api/assistant/capabilities"),
  assistantOverview: () => json<ProjectOverview>("/api/assistant/overview"),
  assistantPrompts: () => json<{ groups: StarterPromptGroup[] }>("/api/assistant/prompts"),
  assistantTriageCategories: () => json<{ categories: TriageCategory[] }>("/api/assistant/triage/categories"),
  assistantDiagnose: (body: {
    symptom: string;
    code?: string;
    module?: string;
    release?: string;
    provider?: string;
    model?: string;
    base_url?: string;
    api_key?: string;
  }) => json<DiagnoseResult>("/api/assistant/diagnose", { method: "POST", body: JSON.stringify(body) }),

  /* ---------------- workspace shell (v2) ---------------- */

  /** The workspace module catalogue (Chat, Knowledge, ARXML Explorer, …). */
  listModules: () => json<ModuleCatalogue>("/api/v2/modules"),

  /**
   * The evidence-first answerability contract for one stored answer.
   * Rejects with an `AnswerabilityUnavailableError` until the gate exists
   * (Phase 5) — the UI must never invent a status.
   */
  getAnswerability: async (conversationId: string, messageIndex: number): Promise<Answerability> => {
    const r = await fetch(`${BASE}/api/v2/answerability/${encodeURIComponent(conversationId)}/${messageIndex}`);
    if (r.status === 501) {
      const body = (await r.json().catch(() => ({}))) as { reason?: string };
      throw new AnswerabilityUnavailableError(body.reason ?? "answerability gate not implemented yet");
    }
    if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
    return (await r.json()) as Answerability;
  },
};

/** Thrown when the answerability gate is not available yet (HTTP 501). */
export class AnswerabilityUnavailableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AnswerabilityUnavailableError";
  }
}

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
