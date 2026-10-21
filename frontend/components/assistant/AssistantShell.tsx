"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import { useAssistant, type ScopeState } from "../../hooks/useAssistant";
import type { SourceEvidence } from "../../lib/types";
import { AssistantMessage } from "./AssistantMessage";
import { Composer } from "./Composer";
import { ConversationSidebar } from "./ConversationSidebar";
import { KnowledgePanel } from "./KnowledgePanel";
import { ScopeBar } from "./ScopeBar";
import { StarterPrompts } from "./StarterPrompts";
import { ArxmlPane, CodePane, DiffPane } from "./Workbench";

const SURFACES = [
  {
    id: "assistant",
    title: "Assistant",
    description: "Conversation with cited answers, visible retrieval steps and sources.",
  },
  {
    id: "arxml",
    title: "ARXML Explorer",
    description: "Deterministic component/port topology with XPath provenance.",
  },
  {
    id: "diff",
    title: "Diff Studio",
    description: "Evidence-aligned structural diff between two API snapshots.",
  },
  {
    id: "code",
    title: "Code Review",
    description: "Advisory static checks on a C snippet — a human approves every fix.",
  },
];

const DEFAULT_SCOPE: ScopeState = {
  mode: "auto",
  provider: "ollama",
  releases: [],
  platforms: [],
  modules: [],
};

interface ShellProps {
  /** Controlled surface (the workspace left nav owns navigation when set). */
  surface?: string;
  onSurfaceChange?: (surface: string) => void;
  /** Opens the evidence drawer at the exact source location of a citation. */
  onSelectEvidence?: (evidence: SourceEvidence) => void;
  /** Hides the in-sidebar product header and the surface switcher. */
  hideHeader?: boolean;
  hideSurfaces?: boolean;
}

/**
 * The product shell: conversation rail, working surface and the knowledge
 * rail. Every surface shares one scope (mode, model, release/module filter)
 * so the user always knows what shaped the result.
 */
export function AssistantShell({
  surface: controlledSurface,
  onSurfaceChange,
  onSelectEvidence,
  hideHeader = false,
  hideSurfaces = false,
}: ShellProps = {}) {
  const a = useAssistant();
  const [localSurface, setLocalSurface] = useState("assistant");
  const surface = controlledSurface ?? localSurface;
  const setSurface = (id: string) => {
    if (onSurfaceChange) onSurfaceChange(id);
    else setLocalSurface(id);
  };
  const [scope, setScope] = useState<ScopeState>(DEFAULT_SCOPE);
  const [input, setInput] = useState("");
  const [composerMode, setComposerMode] = useState<"ask" | "diagnose">("ask");
  const [showKnowledge, setShowKnowledge] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);

  const surfaces = useMemo(() => {
    const backend = a.capabilities?.surfaces ?? [];
    return SURFACES.map((s) => ({
      ...s,
      description: backend.find((b) => b.id === s.id)?.description ?? s.description,
    }));
  }, [a.capabilities]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [a.turns, a.liveSteps]);

  async function send(text: string) {
    const body = text.trim();
    if (!body) return;
    setInput("");
    if (composerMode === "diagnose") {
      await a.diagnose(body, {
        module: scope.modules[0] ?? "",
        release: scope.releases[0] ?? "",
        provider: scope.provider,
      });
      return;
    }
    await a.send(body, {
      mode: scope.mode,
      provider: scope.provider,
      release_filter: scope.releases,
      platform_filter: scope.platforms,
      module_filter: scope.modules,
    });
  }

  const isAssistant = surface === "assistant";

  return (
    <div className="flex h-screen overflow-hidden bg-ink-900 text-fg">
      <ConversationSidebar
        conversations={a.conversations}
        activeId={a.activeId}
        onSelect={(id) => void a.selectConversation(id)}
        onNew={() => void a.newConversation()}
        onDelete={(id) => void a.deleteConversation(id)}
        onRename={(id, t) => void a.renameConversation(id, t)}
        surface={surface}
        surfaces={surfaces}
        onSurface={setSurface}
        hideHeader={hideHeader}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <ScopeBar
          capabilities={a.capabilities}
          scope={scope}
          onScope={setScope}
          surface={surface}
          onSurface={setSurface}
          surfaces={surfaces}
          showKnowledge={showKnowledge}
          onToggleKnowledge={() => setShowKnowledge((v) => !v)}
          hideSurfaces={hideSurfaces}
        />

        {isAssistant ? (
          <>
            <div className="scrollbar-thin flex-1 overflow-y-auto px-4">
              <div className="mx-auto max-w-3xl space-y-7 py-6">
                {a.turns.length === 0 ? (
                  <StarterPrompts
                    groups={a.prompts}
                    onPick={(p) => void send(p)}
                    assistantName={a.capabilities?.assistant}
                    kind={a.capabilities?.kind}
                    ready={a.capabilities?.ready}
                  />
                ) : (
                  a.turns.map((t) => (
                    <AssistantMessage
                      key={t.id}
                      turn={t}
                      stageLabel={a.stageLabel}
                      onFollowup={(q) => void send(q)}
                      onSelectEvidence={onSelectEvidence}
                    />
                  ))
                )}

                {a.streaming && a.liveSteps.length > 0 && a.turns.length > 0 && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <span className="h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent" />
                      Retrieving…
                    </div>
                    <ol className="space-y-1">
                      {a.liveSteps
                        .filter((s) => s.kind === "status")
                        .map((s, i) => (
                          <li key={i} className="font-mono text-2xs text-faint">
                            {a.stageLabel(s.stage)} — {s.message}
                          </li>
                        ))}
                    </ol>
                  </div>
                )}

                <div ref={bottomRef} />
              </div>
            </div>

            <Composer
              value={input}
              onChange={setInput}
              onSend={() => void send(input)}
              onStop={() => void a.stop()}
              streaming={a.streaming}
              mode={composerMode}
              onMode={setComposerMode}
            />
          </>
        ) : (
          <div className="scrollbar-thin flex-1 overflow-y-auto">
            {surface === "arxml" ? (
              <ArxmlPane />
            ) : surface === "diff" ? (
              <DiffPane />
            ) : (
              <CodePane />
            )}
          </div>
        )}

        {a.error && (
          <div className="border-t border-bad/30 bg-bad/10 px-4 py-2 text-xs text-bad">
            {a.error}
          </div>
        )}
      </main>

      {isAssistant && showKnowledge && (
        <KnowledgePanel
          capabilities={a.capabilities}
          overview={a.overview}
          onAsk={(q) => void send(q)}
        />
      )}
    </div>
  );
}
