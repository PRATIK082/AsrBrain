"use client";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { api, streamChat, type StreamEvent } from "../lib/api";

interface Msg { role: "user" | "assistant"; content: string }

export default function ChatPage() {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [status, setStatus] = useState("");
  const [convId, setConvId] = useState("");
  const [ctrl, setCtrl] = useState<AbortController | null>(null);

  async function send() {
    if (!input.trim()) return;
    const text = input;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    const ac = new AbortController();
    setCtrl(ac);
    let acc = "";
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    try {
      const gen = streamChat({ conversation_id: convId || undefined, message: text }, ac.signal);
      for await (const ev: StreamEvent of gen) {
        if (ev.event === "status") setStatus(`${ev.stage}: ${ev.message}`);
        else if (ev.event === "token") {
          acc += ev.text;
          setMessages((m) => { const c = [...m]; c[c.length - 1] = { role: "assistant", content: acc }; return c; });
        } else if (ev.event === "clarify") {
          setMessages((m) => { const c = [...m]; c[c.length - 1] = { role: "assistant", content: ev.question }; return c; });
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setStatus(String(e));
    } finally {
      setStatus("");
      setCtrl(null);
    }
  }

  return (
    <main className="flex h-screen">
      <aside className="w-64 border-r p-4">
        <h1 className="font-bold">AUTOSAR Copilot</h1>
        <button className="mt-4 w-full rounded border p-2" onClick={() => { setMessages([]); setConvId(""); }}>
          ＋ New conversation
        </button>
        <p className="mt-4 text-sm text-gray-500">Conversations persist in the backend (/api/conversations).</p>
      </aside>
      <section className="flex flex-1 flex-col">
        <div className="flex-1 space-y-4 overflow-y-auto p-6">
          {messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
              <div className="inline-block max-w-3xl rounded border p-3 text-left">
                <ReactMarkdown>{m.content}</ReactMarkdown>
              </div>
            </div>
          ))}
          {status && <p className="text-sm text-gray-500">{status}</p>}
        </div>
        <div className="flex gap-2 border-t p-4">
          <input className="flex-1 rounded border p-2" value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
            placeholder="Ask about AUTOSAR…" />
          <button className="rounded bg-black px-4 py-2 text-white" onClick={send}>Send</button>
          {ctrl && <button className="rounded border px-4 py-2" onClick={() => { ctrl.abort(); api.stop(convId); }}>Stop</button>}
        </div>
      </section>
    </main>
  );
}
