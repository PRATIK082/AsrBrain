import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';

export interface SessionMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export interface ConversationSession {
  id: string;
  title: string;
  model: string;
  platformSlot: 'Classic' | 'Adaptive' | 'Foundation' | null;
  releaseSlot: string | null;
  moduleSlot: string | null;
  messages: SessionMessage[];
}

interface AsrBrainState {
  sessions: Record<string, ConversationSession>;
  activeSessionId: string | null;
  initiateSession: (providerModel: string) => string;
  updateSlots: (
    sessionId: string,
    slots: Partial<Pick<ConversationSession, 'platformSlot' | 'releaseSlot' | 'moduleSlot'>>,
  ) => void;
  appendMessage: (sessionId: string, role: 'user' | 'assistant', content: string) => void;
  forkWorkspace: (sourceSessionId: string, secondaryModel: string) => string;
  exportSessionBundle: (sessionId: string) => string;
  importSessionBundle: (jsonString: string) => boolean;
}

function newId(prefix: string): string {
  try {
    return `${prefix}_${crypto.randomUUID()}`;
  } catch {
    return `${prefix}_${Date.now().toString(36)}_${Math.floor(Math.random() * 1e9).toString(36)}`;
  }
}

export const useAsrBrainStore = create<AsrBrainState>()(
  persist(
    (set, get) => ({
      sessions: {},
      activeSessionId: null,

      initiateSession: (providerModel) => {
        const id = newId('session');
        const newSession: ConversationSession = {
          id,
          title: 'Uninitialized Execution Stream',
          model: providerModel,
          platformSlot: null,
          releaseSlot: null,
          moduleSlot: null,
          messages: [],
        };
        set((state) => ({
          sessions: { ...state.sessions, [id]: newSession },
          activeSessionId: id,
        }));
        return id;
      },

      updateSlots: (sessionId, slots) => {
        set((state) => {
          const current = state.sessions[sessionId];
          if (!current) return state;
          let title = current.title;
          if (slots.moduleSlot && current.title === 'Uninitialized Execution Stream') {
            title = `${slots.moduleSlot} Architecture Analysis`;
          }
          return {
            sessions: {
              ...state.sessions,
              [sessionId]: { ...current, ...slots, title },
            },
          };
        });
      },

      appendMessage: (sessionId, role, content) => {
        set((state) => {
          const current = state.sessions[sessionId];
          if (!current) return state;
          return {
            sessions: {
              ...state.sessions,
              [sessionId]: {
                ...current,
                messages: [...current.messages, { id: newId('msg'), role, content, timestamp: Date.now() }],
              },
            },
          };
        });
      },

      forkWorkspace: (sourceSessionId, secondaryModel) => {
        const state = get();
        const src = state.sessions[sourceSessionId];
        if (!src) throw new Error('Source context missing for system replication');
        const newSessionId = newId('session');
        const clonedSession: ConversationSession = {
          ...src,
          id: newSessionId,
          title: `${src.title} (⑂ Fork - ${secondaryModel})`,
          model: secondaryModel,
          messages: [...src.messages],
        };
        set((state) => ({
          sessions: { ...state.sessions, [newSessionId]: clonedSession },
          activeSessionId: newSessionId,
        }));
        return newSessionId;
      },

      exportSessionBundle: (sessionId) => {
        const target = get().sessions[sessionId];
        if (!target) throw new Error('Cannot run backup routine on null reference target');
        return JSON.stringify(
          {
            signature: 'ASRBRAIN_SESSION_METADATA_BUNDLE',
            version: '2.0.0',
            payload: target,
          },
          null,
          2,
        );
      },

      importSessionBundle: (jsonString) => {
        try {
          const envelope = JSON.parse(jsonString);
          if (envelope.signature !== 'ASRBRAIN_SESSION_METADATA_BUNDLE') return false;
          const targetSession = envelope.payload as ConversationSession;
          if (!targetSession || typeof targetSession.id !== 'string') return false;
          set((state) => ({
            sessions: { ...state.sessions, [targetSession.id]: targetSession },
            activeSessionId: targetSession.id,
          }));
          return true;
        } catch {
          return false;
        }
      },
    }),
    {
      name: 'asrbrain-orchestrator-storage',
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
