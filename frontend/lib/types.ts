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

/* ----------------------------------------------------------- GraphRAG + tools */

export interface ToolSpec {
  name: string;
  description: string;
  parameters: Record<string, unknown>;
  tags: string[];
  mutating: boolean;
}

export interface ToolListResponse {
  tools: ToolSpec[];
  count: number;
  names: string[];
}

export interface GraphNode {
  node_id: string;
  type: string;
  label: string;
  properties?: Record<string, unknown>;
  degree?: number;
  community?: string | null;
  source?: string | null;
  score?: number;
  channels?: string[];
}

export interface GraphEdge {
  src: string;
  dst: string;
  rel: string;
  weight?: number;
  confidence?: number;
  is_inferred?: number | boolean;
  provenance?: string;
}

export interface GraphCommunity {
  community_id: string;
  title: string;
  summary?: string;
  member_count?: number;
  level?: number;
  members?: string[];
  score?: number;
}

export interface GraphStats {
  path?: string;
  nodes: number;
  edges: number;
  communities: number;
  trace_links: number;
  inferred_edges?: number;
  nodes_by_type?: Record<string, number>;
  edges_by_rel?: Record<string, number>;
}

export interface GraphQueryResult {
  mode: string;
  query: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  communities: GraphCommunity[];
  seeds?: string[];
  seed_nodes?: GraphNode[];
  node_count?: number;
  edge_count?: number;
  community_count?: number;
  stats?: GraphStats;
}

export interface MindmapResult {
  topic: string;
  source: string;
  mermaid: string;
  tree?: { label: string; children?: MindmapNode[] };
  nodes?: GraphNode[];
  seeds?: string[];
  citations?: Record<string, unknown>;
  node_count?: number;
  empty?: boolean;
}

export interface MindmapNode {
  label: string;
  children?: MindmapNode[];
}

export interface AgentWorkflowStep {
  tool: string;
  args?: Record<string, unknown>;
  purpose?: string;
}

export interface AgentWorkflow {
  name: string;
  title: string;
  description: string;
  intent: string;
  tools: string[];
  context_keys: string[];
  steps: AgentWorkflowStep[];
}

export interface AgentObservation {
  tool: string;
  summary: string;
  ok?: boolean;
  data?: unknown;
}

export type AgentEvent =
  | { event: "workflow"; workflow: string; title?: string; intent?: string; steps?: AgentWorkflowStep[] }
  | { event: "plan"; plan?: { steps?: AgentWorkflowStep[]; rationale?: string; mode?: string } }
  | { event: "tool_call"; tool: string; args?: Record<string, unknown>; purpose?: string }
  | { event: "tool_result"; tool: string; ok?: boolean; summary?: string; data?: unknown; error?: string; duration_ms?: number }
  | { event: "tool_skipped"; tool: string; reason?: string }
  | { event: "complete"; answer: string; workflow?: string; intent?: string; citations?: unknown[]; observations?: AgentObservation[]; trace?: unknown[]; plan?: unknown }
  | { event: "error"; error: string };

export interface AgentRunResult {
  routed_workflow: string;
  workflow: string;
  intent: string;
  answer: string;
  citations: unknown[];
  observations: AgentObservation[];
  trace: unknown[];
  plan: unknown;
}
