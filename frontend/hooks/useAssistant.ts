"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, streamChat } from "../lib/api";
import type {
  AssistantCapabilities,
  AssistantStep,
  AssistantTurn,
  ChatMode,
  DiagnoseResult,
  ProjectOverview,
  SourceEvidence,
  StarterPromptGroup,
} from "../lib/types";

export interface ConversationSummary {
  id: string;
  title: string;
  created_at?: number;
  updated_at?: number;
  archived?: number;
}

export interface SendOptions {
  mode?: ChatMode;
  provider?: "ollama" | "openai_compat";
  model?: string;
  base_url?: string;
  api_key?: string;
  release_filter?: string[];
  platform_filter?: string[];
  module_filter?: string[];
}

/** What the user pinned in the scope bar; sent verbatim with every request. */
export interface ScopeState {
  mode: ChatMode;
  provider: "ollama" | "openai_compat";
  releases: string[];
  platforms: string[];
  modules: string[];
}

export interface DiagnoseOptions {
  code?: string;
  module?: string;
  release?: string;
  provider?: "ollama" | "openai_compat";
  model?: string;
  base_url?: string;
  api_key?: string;
}

function toEvidence(raw: unknown): SourceEvidence {
  const e = (raw ?? {}) as Record<string, unknown>;
  return {
    label: String(e.label ?? ""),
    source_id: String(e.source_id ?? ""),
    source_pdf: String(e.source_pdf ?? ""),
    page: Number(e.page ?? 0),
    page_end: e.page_end === undefined || e.page_end === null ? undefined : Number(e.page_end),
    section: String(e.section ?? ""),
    release: String(e.release ?? ""),
    platform: String(e.platform ?? ""),
    module: String(e.module ?? ""),
    requirement_ids: Array.isArray(e.requirement_ids) ? e.requirement_ids.map(String) : [],
    snippet: String(e.snippet ?? ""),
    relevance: Number(e.relevance ?? 0),
  };
}

let turnSeq = 0;
function nextId(prefix: string): string {
  turnSeq += 1;
  return `${prefix}-${turnSeq}-${Date.now().toString(36)}`;
}

const STAGE_ORDER = [
  "query_understanding",
  "retrieval_planning",
  "text_retrieval",
  "table_retrieval",
  "graph_retrieval",
  "fusion_rerank",
  "expansion_compression",
  "answer_drafting",
  "citation_validation",
  "confidence",
];

function stageLabel(stage: string): string {
  return (
    {
      query_understanding: "Understanding the question",
      retrieval_planning: "Planning retrieval",
      text_retrieval: "Searching the corpus",
      table_retrieval: "Searching tables",
      graph_retrieval: "Walking the knowledge graph",
      fusion_rerank: "Re-ranking passages",
      expansion_compression: "Compressing context",
      answer_drafting: "Drafting the answer",
      citation_validation: "Validating citations",
      confidence: "Scoring confidence",
      cancelled: "Stopped",
    }[stage] ?? stage
  );
}

/**
 * Server-backed assistant session.
 *
 * The conversation lives in the backend chat store, so a reload restores the
 * thread, its slots and the per-turn sources. Everything the UI shows is
 * derived from backend events — the client never invents evidence.
 */
export function useAssistant() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [activeId, setActiveId] = useState("");
  const [turns, setTurns] = useState<AssistantTurn[]>([]);
  const [liveSteps, setLiveSteps] = useState<AssistantStep[]>([]);
  const [liveEvidence, setLiveEvidence] = useState<SourceEvidence[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [capabilities, setCapabilities] = useState<AssistantCapabilities | null>(null);
  const [overview, setOverview] = useState<ProjectOverview | null>(null);
  const [prompts, setPrompts] = useState<StarterPromptGroup[]>([]);

  const abortRef = useRef<AbortController | null>(null);
  const activeRef = useRef("");
  activeRef.current = activeId;

  const loadConversations = useCallback(async () => {
    try {
      const rows = (await api.conversations()) as ConversationSummary[];
      setConversations(rows);
      return rows;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return [];
    }
  }, []);

  const loadContext = useCallback(async () => {
    const [caps, ov, pr] = await Promise.allSettled([
      api.assistantCapabilities(),
      api.assistantOverview(),
      api.assistantPrompts(),
    ]);
    if (caps.status === "fulfilled") setCapabilities(caps.value);
    if (ov.status === "fulfilled") setOverview(ov.value);
    if (pr.status === "fulfilled") setPrompts(pr.value.groups ?? []);
  }, []);

  useEffect(() => {
    void loadContext();
    void loadConversations();
  }, [loadContext, loadConversations]);

  const selectConversation = useCallback(async (cid: string) => {
    setError("");
    try {
      const conv = (await json_get(`/api/conversations/${cid}`)) as {
        id: string;
        title: string;
        messages: { role: string; content: string; meta: Record<string, unknown> }[];
      };
      setActiveId(conv.id);
      const restored: AssistantTurn[] = conv.messages.map((m) => {
        const meta = m.meta ?? {};
        const evidence = Array.isArray(meta.evidence)
          ? (meta.evidence as unknown[]).map(toEvidence)
          : [];
        return {
          id: nextId(m.role === "user" ? "u" : "a"),
          role: m.role === "user" ? "user" : "assistant",
          content: m.content,
          evidence,
          steps: [],
          followups: Array.isArray(meta.followups) ? (meta.followups as string[]) : undefined,
          llm: typeof meta.llm === "string" ? meta.llm : undefined,
        };
      });
      setTurns(restored);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const newConversation = useCallback(async () => {
    setError("");
    try {
      const conv = (await api.createConversation()) as { id: string; title: string };
      setActiveId(conv.id);
      setTurns([]);
      setLiveSteps([]);
      setLiveEvidence([]);
      await loadConversations();
      return conv.id;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return "";
    }
  }, [loadConversations]);

  const deleteConversation = useCallback(
    async (cid: string) => {
      try {
        await api.deleteConversation(cid);
        if (cid === activeRef.current) {
          setActiveId("");
          setTurns([]);
        }
        await loadConversations();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [loadConversations],
  );

  const renameConversation = useCallback(
    async (cid: string, title: string) => {
      try {
        await api.renameConversation(cid, title);
        await loadConversations();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [loadConversations],
  );

  const send = useCallback(
    async (text: string, opts: SendOptions = {}) => {
      const body = text.trim();
      if (!body || streaming) return;
      setError("");

      let cid = activeRef.current;
      if (!cid) {
        cid = await newConversation();
        if (!cid) return;
      }

      const userTurn: AssistantTurn = {
        id: nextId("u"),
        role: "user",
        content: body,
        evidence: [],
        steps: [],
      };
      const assistantTurn: AssistantTurn = {
        id: nextId("a"),
        role: "assistant",
        content: "",
        evidence: [],
        steps: [],
        pending: true,
      };
      setTurns((prev) => [...prev, userTurn, assistantTurn]);
      setLiveSteps([]);
      setLiveEvidence([]);
      setStreaming(true);

      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const steps: AssistantStep[] = [];
      const evidence: SourceEvidence[] = [];
      let answer = "";
      let followups: string[] = [];
      let confidence = 0;
      let level = "";
      let citationCoverage = 0;
      let llm = "";
      let clarify: AssistantTurn["clarify"];

      try {
        for await (const ev of streamChat(
          {
            conversation_id: cid,
            message: body,
            mode: opts.mode ?? "auto",
            provider: opts.provider ?? "ollama",
            model: opts.model,
            base_url: opts.base_url,
            api_key: opts.api_key,
            release_filter: opts.release_filter ?? [],
            platform_filter: opts.platform_filter ?? [],
            module_filter: opts.module_filter ?? [],
            include_graph: true,
            include_tables: true,
            include_figures: true,
          },
          ctrl.signal,
        )) {
          if (ev.event === "status") {
            const step: AssistantStep = {
              stage: ev.stage,
              message: ev.message,
              kind: "status",
            };
            steps.push(step);
            setLiveSteps([...steps]);
          } else if (ev.event === "evidence") {
            const src = toEvidence(ev);
            evidence.push(src);
            steps.push({ stage: "evidence", message: src.source_pdf, kind: "evidence", evidence: src });
            setLiveEvidence([...evidence]);
            setLiveSteps([...steps]);
          } else if (ev.event === "token") {
            answer += ev.text;
            setTurns((prev) =>
              prev.map((t) => (t.id === assistantTurn.id ? { ...t, content: answer } : t)),
            );
          } else if (ev.event === "clarify") {
            clarify = { missing: ev.missing, question: ev.question };
            answer = ev.question;
            setTurns((prev) =>
              prev.map((t) =>
                t.id === assistantTurn.id
                  ? { ...t, content: ev.question, clarify: { missing: ev.missing, question: ev.question } }
                  : t,
              ),
            );
          } else if (ev.event === "complete") {
            answer = ev.answer || answer;
            followups = ev.followups ?? [];
            confidence = ev.confidence ?? 0;
            level = ev.level ?? "";
            citationCoverage = ev.citation_coverage ?? 0;
            llm = ev.llm ?? "";
          }
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        if (msg.toLowerCase().includes("abort")) {
          setError("Stopped.");
        } else {
          setError(msg);
          steps.push({ stage: "error", message: msg, kind: "error" });
        }
      } finally {
        setStreaming(false);
        abortRef.current = null;
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantTurn.id
              ? {
                  ...t,
                  content: t.content || answer,
                  evidence: evidence.length ? evidence : t.evidence,
                  steps,
                  followups: followups.length ? followups : t.followups,
                  confidence,
                  level,
                  citation_coverage: citationCoverage,
                  llm,
                  clarify,
                  pending: false,
                }
              : t,
          ),
        );
        setLiveSteps([]);
        setLiveEvidence([]);
        void loadConversations();
      }
    },
    [loadConversations, newConversation, streaming],
  );

  const diagnose = useCallback(
    async (symptom: string, opts: DiagnoseOptions = {}) => {
      const body = symptom.trim();
      if (!body || streaming) return;
      setError("");

      let cid = activeRef.current;
      if (!cid) {
        cid = await newConversation();
        if (!cid) return;
      }

      const userTurn: AssistantTurn = {
        id: nextId("u"),
        role: "user",
        content: body,
        evidence: [],
        steps: [],
      };
      const assistantTurn: AssistantTurn = {
        id: nextId("a"),
        role: "assistant",
        content: "",
        evidence: [],
        steps: [],
        pending: true,
      };
      setTurns((prev) => [...prev, userTurn, assistantTurn]);
      setStreaming(true);

      try {
        const result = (await api.assistantDiagnose({
          symptom: body,
          code: opts.code,
          module: opts.module,
          release: opts.release,
          provider: opts.provider,
          model: opts.model,
          base_url: opts.base_url,
          api_key: opts.api_key,
        })) as DiagnoseResult;
        setTurns((prev) =>
          prev.map((t) =>
            t.id === assistantTurn.id
              ? {
                  ...t,
                  content: result.summary,
                  evidence: result.evidence ?? [],
                  steps: [],
                  confidence: result.confidence,
                  level: result.level,
                  followups: result.followups,
                  llm: result.llm,
                  diagnose: result,
                  pending: false,
                }
              : t,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setTurns((prev) =>
          prev.map((t) => (t.id === assistantTurn.id ? { ...t, pending: false } : t)),
        );
      } finally {
        setStreaming(false);
        void loadConversations();
      }
    },
    [loadConversations, newConversation, streaming],
  );

  const stop = useCallback(async () => {
    abortRef.current?.abort();
    if (activeRef.current) {
      try {
        await api.stop(activeRef.current);
      } catch {
        /* best effort */
      }
    }
  }, []);

  return {
    conversations,
    activeId,
    turns,
    liveSteps,
    liveEvidence,
    streaming,
    error,
    capabilities,
    overview,
    prompts,
    loadConversations,
    newConversation,
    selectConversation,
    deleteConversation,
    renameConversation,
    send,
    diagnose,
    stop,
    stageLabel,
    stageOrder: STAGE_ORDER,
  };
}

async function json_get<T>(path: string): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
  const r = await fetch(`${base}${path}`);
  if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
  return r.json() as Promise<T>;
}
