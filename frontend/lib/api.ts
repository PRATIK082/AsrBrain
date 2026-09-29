import type { ChatRequest, StreamEvent } from "./types";

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
