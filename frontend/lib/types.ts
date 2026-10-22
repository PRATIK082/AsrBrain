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

/* Evaluation screen (master prompt §7 screen 7, §9) */

export interface EvalMetric {
  value: number | null;
  n: number;
  ci95: [number, number] | null;
}

export interface EvalFailureCounts { [failure: string]: number }

export interface EvalCategoryBlock {
  n: number;
  answerable: number;
  unanswerable: number;
  abstention_rate: number | null;
  abstention_accuracy: EvalMetric;
  context_recall: EvalMetric;
  context_precision: EvalMetric;
  requirement_recall: EvalMetric;
  citation_precision: EvalMetric;
  citation_recall: EvalMetric;
  faithfulness: EvalMetric;
  answer_relevance: number | null;
  answer_correctness: number | null;
  exact_id_match: number | null;
  hallucinated_id_rate_mean: number | null;
  hallucinated_ids_total: number;
  recall_at_10: number | null;
  hit_rate: EvalMetric;
  latency_p50_s: number;
  latency_p95_s: number;
  failures: EvalFailureCounts;
}

export interface EvalAggregate {
  n: number;
  answerable: number;
  unanswerable: number;
  abstention_rate: number | null;
  abstention_accuracy: EvalMetric;
  context_recall: EvalMetric;
  context_precision: EvalMetric;
  requirement_recall: EvalMetric;
  citation_precision: EvalMetric;
  citation_recall: EvalMetric;
  faithfulness: EvalMetric;
  answer_relevance: number | null;
  answer_correctness: number | null;
  exact_id_match: number | null;
  hallucinated_id_rate_mean: number | null;
  hallucinated_ids_total: number;
  latency_p50_s: number;
  latency_p95_s: number;
  failures: EvalFailureCounts;
  by_category: { [category: string]: EvalCategoryBlock };
  by_difficulty: { [difficulty: string]: EvalCategoryBlock };
}

export interface EvalWorstRow {
  query_id: string;
  category: string;
  difficulty: string;
  failure: string;
  context_recall: number;
  faithfulness: number | null;
  hallucinated_id_rate: number | null;
  latency_s: number;
  question: string;
}

export interface EvalCoverage {
  n: number;
  by_category: { [category: string]: number };
  mix: { [slice: string]: number };
  answerable: number;
  unanswerable: number;
  needs_expert_review: number;
  difficulty: { [difficulty: string]: number };
  coverage_gaps: { slice: string; target: number; actual: number }[];
  meets_coverage_targets: boolean;
}

export interface EvalLatest {
  available: boolean;
  label?: string;
  generated_at?: string;
  mode?: string;
  split?: string;
  llm_model?: string | null;
  golden_sha256?: string;
  coverage?: EvalCoverage;
  metrics_methods?: { [metric: string]: string };
  aggregate?: EvalAggregate;
  worst?: EvalWorstRow[];
  split_drift?: string[];
  hint?: string;
}

export interface EvalRunSummary {
  label: string;
  generated_at: string;
  mode: string;
  split: string;
  llm_model: string | null;
  n: number;
  context_recall: number | null;
  citation_precision: number | null;
  faithfulness: number | null;
  answer_correctness: number | null;
  abstention_accuracy: number | null;
  hallucinated_id_rate_mean: number | null;
  latency_p50_s: number;
  latency_p95_s: number;
}

export interface EvalGateCheck {
  metric: string;
  measured?: number;
  threshold?: number;
  tolerance?: number;
  direction?: string;
  status: "pass" | "fail" | "skipped";
  reason?: string;
}

export interface EvalGate { passed: boolean; label?: string; generated_at?: string; checks: EvalGateCheck[] }
