/** API contract types (mirror Part D). No retrieval logic lives here. */
export interface ChatRequest {
  conversation_id?: string;
  message: string;
  release_filter?: string[];
  platform_filter?: string[];
  module_filter?: string[];
  mode?: "auto" | "exact_lookup" | "comparison" | "troubleshooting" | "deep_explanation";
  include_graph?: boolean;
  include_tables?: boolean;
  include_figures?: boolean;
  stream?: boolean;
  provider?: "ollama" | "openai_compat";
  model?: string;
  base_url?: string;
  api_key?: string;
}

export type StreamEvent =
  | { event: "status"; stage: string; message: string }
  | { event: "clarify"; missing: string[]; detected_modules: string[]; question: string }
  | { event: "evidence"; source_id: string; source_pdf: string; page: number; section: string; release: string; snippet: string; relevance: number; label: string }
  | { event: "token"; text: string }
  | { event: "complete"; answer: string; confidence: number; level: string; citation_coverage: number; followups?: string[]; trace: Record<string, unknown>; graph: unknown[] };

export interface Conversation { id: string; title: string; updated_at: number }
