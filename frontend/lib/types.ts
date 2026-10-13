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

export interface ArxmlNode { id: string; type: string; label: string; xpath?: string }
export interface ArxmlEdge { src: string; rel: string; dst: string; is_inferred?: boolean }
export interface CodeFinding { rule: string; level: string; location: string; message: string; provenance: string }
export interface DiffItem {
  domain: string; entity_key: string; change_type: string; severity: string;
  base_value?: unknown; target_value?: unknown;
  compatibility_risk: string; migration_action?: string | null;
}
