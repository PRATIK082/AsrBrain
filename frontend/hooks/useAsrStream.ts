import { useState, useCallback, useRef } from 'react';
import { useAsrBrainStore } from '../store/useAsrBrainStore';
import { api, streamChat } from '../lib/api';

/**
 * Runtime streaming controller.
 *
 * Consumes the REAL backend contract (GET/POST /api/chat/stream events:
 * status | clarify | evidence | token | complete — see lib/types.ts) and
 * projects it onto the telemetry/evidence state the chat UI renders.
 * Thread cancellation aborts the reader AND notifies the server via
 * POST /api/chat/stop so CPU-bound generation actually halts.
 */

export type StageStatus = 'active' | 'completed' | 'failed';

export interface PipelineStageEvent {
  /** Backend stage key (STAGES in src/workflows/stages.py) plus policy/routing. */
  stage: string;
  status: StageStatus;
  message: string;
}

export type EvidenceLayer = 'Application' | 'RTE' | 'BSW' | 'MCAL';

export interface StreamEvidence {
  id: string;
  documentName: string;
  pageNumber: number;
  requirementId?: string;
  snippet: string;
  confidenceScore: number;
  layer: EvidenceLayer;
  release: string;
  section: string;
}

export type StreamVerdict = 'verified' | 'needs_human_validation' | 'abstained';

export interface StreamOptions {
  conversationId?: string;
  onConversationId?: (id: string) => void;
}

const SWS_RE = /\bSWS_[A-Za-z]+_\d+\b/;

function inferLayer(sourcePdf: string, section: string): EvidenceLayer {
  const hay = `${sourcePdf} ${section}`;
  if (/\bRte\b|RTE/i.test(hay)) return 'RTE';
  if (/\b(Mcu|Port|Dio|Adc|Gpt|Spi|Icu|Pwm|Ocu|Mcl|Fls|Fee|Wdg|Eep)\b|MCAL/i.test(hay)) return 'MCAL';
  if (/\b(CanIf|CanDrv|CanSM|PduR|Com|ComM|Nm|Dcm|Dem|DoIP|SOME-?IP|BSW|EcuM|Os|MemIf|NvM)\b/i.test(hay))
    return 'BSW';
  return 'Application';
}

export const useAsrStream = () => {
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [currentStages, setCurrentStages] = useState<PipelineStageEvent[]>([]);
  const [currentEvidence, setCurrentEvidence] = useState<StreamEvidence[]>([]);
  const [streamedResponse, setStreamedResponse] = useState<string>('');
  const [verdict, setVerdict] = useState<StreamVerdict>('verified');

  const abortControllerRef = useRef<AbortController | null>(null);
  const convIdRef = useRef<string>('');
  const appendMessage = useAsrBrainStore((state) => state.appendMessage);
  const updateSlots = useAsrBrainStore((state) => state.updateSlots);

  const markStage = useCallback((stage: string, message: string, terminal = false) => {
    setCurrentStages((prev) => {
      const mapped = prev.map((s) =>
        s.stage === stage ? { ...s, status: (terminal ? 'completed' : 'active') as StageStatus, message } : s,
      );
      if (mapped.some((s) => s.stage === stage)) return mapped;
      return [...prev.map((s) => ({ ...s, status: 'completed' as StageStatus })), { stage, status: 'active' as StageStatus, message }];
    });
  }, []);

  const abortStream = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsStreaming(false);
    if (convIdRef.current) api.stop(convIdRef.current).catch(() => undefined);
  }, []);

  const executeStream = useCallback(
    async (sessionId: string, userPrompt: string, options: StreamOptions = {}) => {
      setIsStreaming(true);
      setStreamedResponse('');
      setCurrentStages([]);
      setCurrentEvidence([]);
      setVerdict('verified');
      appendMessage(sessionId, 'user', userPrompt);
      const ac = new AbortController();
      abortControllerRef.current = ac;
      convIdRef.current = options.conversationId ?? '';
      let acc = '';

      try {
        const gen = streamChat(
          { conversation_id: options.conversationId || undefined, message: userPrompt },
          ac.signal,
        );
        for await (const packet of gen) {
          switch (packet.event) {
            case 'status':
              if (packet.stage === 'cancelled') {
                setCurrentStages((prev) => prev.map((s) => ({ ...s, status: 'completed' as StageStatus })));
                setIsStreaming(false);
                return;
              }
              markStage(packet.stage, packet.message);
              break;
            case 'clarify':
              // Slot-filling loop: persist what the engine detected, surface the question.
              updateSlots(sessionId, {
                moduleSlot: packet.detected_modules?.[0] ?? null,
              });
              markStage('clarify_check', packet.question, true);
              acc = packet.question;
              setStreamedResponse(acc);
              break;
            case 'evidence':
              setCurrentEvidence((prev) => [
                ...prev,
                {
                  id: packet.source_id,
                  documentName: packet.source_pdf,
                  pageNumber: packet.page,
                  requirementId: SWS_RE.exec(packet.snippet)?.[0],
                  snippet: packet.snippet,
                  confidenceScore: Math.max(0, Math.min(1, packet.relevance ?? 0)),
                  layer: inferLayer(packet.source_pdf, packet.section),
                  release: packet.release,
                  section: packet.section,
                },
              ]);
              markStage('retrieval_fusion', `Evidence ${packet.label} · ${packet.source_pdf}`);
              break;
            case 'token':
              acc += packet.text;
              setStreamedResponse(acc);
              break;
            case 'complete': {
              if (acc && packet.answer && !packet.answer.startsWith(acc.slice(0, 64))) acc = packet.answer;
              else if (!acc) acc = packet.answer;
              setStreamedResponse(acc);
              const abstained = /could not verify/i.test(packet.answer);
              setVerdict(abstained ? 'abstained' : packet.level === 'High' ? 'verified' : 'needs_human_validation');
              setCurrentStages((prev) => prev.map((s) => ({ ...s, status: 'completed' as StageStatus })));
              appendMessage(sessionId, 'assistant', packet.answer);
              setIsStreaming(false);
              return;
            }
          }
        }
        // Stream ended without a complete frame (e.g. clarify-only turn).
        if (acc) appendMessage(sessionId, 'assistant', acc);
        setIsStreaming(false);
      } catch (error: unknown) {
        if ((error as Error)?.name !== 'AbortError') {
          setStreamedResponse((prev) => `${prev}\n\n[System Error: ${(error as Error)?.message ?? error}]`);
          setCurrentStages((prev) => prev.map((s) => ({ ...s, status: 'failed' as StageStatus })));
          setIsStreaming(false);
        }
      }
    },
    [appendMessage, markStage, updateSlots],
  );

  return { executeStream, abortStream, isStreaming, currentStages, currentEvidence, streamedResponse, verdict };
};
