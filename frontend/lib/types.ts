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
  | {
      event: "evidence";
      source_id: string;
      source_pdf: string;
      page: number;
      page_end?: number;
      section: string;
      release: string;
      platform?: string;
      module?: string;
      requirement_ids?: string[];
      snippet: string;
      relevance: number;
      label: string;
    }
  | { event: "token"; text: string }
  | { event: "complete"; answer: string; confidence: number; level: string; citation_coverage: number; followups?: string[]; trace: Record<string, unknown>; graph: unknown[]; llm?: string; answerability?: Answerability };

export interface Conversation { id: string; title: string; updated_at: number }

export interface ArxmlNode { id: string; type: string; label: string; xpath?: string }
export interface ArxmlEdge { src: string; rel: string; dst: string; is_inferred?: boolean }
export interface CodeFinding { rule: string; level: string; location: string; message: string; provenance: string }
export interface DiffItem {
  domain: string; entity_key: string; change_type: string; severity: string;
  base_value?: unknown; target_value?: unknown;
  compatibility_risk: string; migration_action?: string | null;
}

/* ------------------------------------------------------------------ *
 * Institutional assistant (/api/assistant/*)
 * ------------------------------------------------------------------ */

export type ChatMode =
  | "auto" | "exact_lookup" | "comparison" | "troubleshooting" | "deep_explanation";

export interface CorpusManifest {
  available: boolean;
  canonical_db: string;
  documents: number;
  chunks: number;
  tables: number;
  figures: number;
  requirements: number;
  apis: number;
  ecu_parameters: number;
  releases: string[];
  platforms: string[];
  modules: string[];
  document_types: string[];
}

export interface AssistantMode { id: ChatMode; title: string; description: string }
export interface AssistantSurface { id: string; title: string; route: string; description: string }

export interface AssistantCapabilities {
  assistant: string;
  kind: string;
  corpus: CorpusManifest;
  modes: AssistantMode[];
  surfaces: AssistantSurface[];
  guarantees: string[];
  ready: boolean;
}

export interface ModuleOverview {
  module: string;
  chunks: number;
  releases: string[];
  platforms: string[];
  requirements: number;
  apis: number;
  document_types: string[];
}

export interface ConceptFlowTriple {
  module: string;
  requirement: string;
  api: string;
  source_pdf: string;
  page: number;
  section: string;
  release: string;
  chunk_id: string;
}

export interface EntityAnchor { id: string; mentions: number }

export interface OverviewDocument {
  document_id: string;
  source_pdf: string;
  title: string;
  release: string;
  platform: string;
  module: string;
  document_type: string;
  pages: number;
  quality: number;
}

export interface ProjectOverview {
  available: boolean;
  corpus: CorpusManifest;
  modules: ModuleOverview[];
  releases: { release: string; platform: string; chunks: number }[];
  documents: OverviewDocument[];
  concept_flow: ConceptFlowTriple[];
  entity_anchors: { requirements: EntityAnchor[]; apis: EntityAnchor[] };
}

export interface StarterPrompt { title: string; prompt: string }
export interface StarterPromptGroup { group: string; icon: string; prompts: StarterPrompt[] }

export interface SourceEvidence {
  label: string;
  source_id: string;
  source_pdf: string;
  page: number;
  page_end?: number;
  section: string;
  release: string;
  platform: string;
  module: string;
  requirement_ids: string[];
  snippet: string;
  relevance: number;
}

export interface TriageCheck { question: string; how: string }

export interface TriageCategory {
  id: string;
  title: string;
  keywords: string[];
  checks: TriageCheck[];
  matched?: string[];
  confidence?: number;
}

/** A cause / fix / check that carries a citation into the evidence list. */
export interface TriageFinding {
  cause?: string;
  suggestion?: string;
  question?: string;
  how?: string;
  label?: string;
  source_id?: string;
  source_pdf?: string;
  page?: number;
  section?: string;
  release?: string;
  module?: string;
  normative?: boolean;
  relevance?: number;
}

export interface DiagnoseResult {
  ok: boolean;
  abstained: boolean;
  symptom: string;
  category: TriageCategory;
  likely_causes: TriageFinding[];
  checks: TriageFinding[];
  fix_candidates: TriageFinding[];
  summary: string;
  confidence: number;
  level: string;
  llm: string;
  followups: string[];
  evidence: SourceEvidence[];
}

/** One retrieval step shown in the "how the answer was built" timeline. */
export interface AssistantStep {
  stage: string;
  message: string;
  kind: "status" | "clarify" | "evidence" | "token" | "complete" | "error";
  evidence?: SourceEvidence;
}

/** A rendered conversation turn (user or assistant). */
export interface AssistantTurn {
  id: string;
  role: "user" | "assistant";
  content: string;
  evidence: SourceEvidence[];
  steps: AssistantStep[];
  confidence?: number;
  level?: string;
  followups?: string[];
  citation_coverage?: number;
  llm?: string;
  diagnose?: DiagnoseResult;
  clarify?: { missing: string[]; question: string };
  pending?: boolean;
  answerability?: Answerability;
}

/* ------------------------------------------------------------------ *
 * Evidence-first answerability contract
 * ------------------------------------------------------------------ */

/**
 * The user-facing answer contract. A numeric confidence is NOT a correctness
 * claim and is never rendered as one — it stays inside the audit section.
 */
export type AnswerabilityStatus =
  | "VERIFIED"
  | "EVIDENCE_SUPPORTED"
  | "NEEDS_ENGINEER_REVIEW"
  | "INSUFFICIENT_EVIDENCE";

export interface Answerability {
  status: AnswerabilityStatus;
  /** Plain-language reason for the status. Never empty. */
  reason: string;
  /** Artifacts / metadata that would be required to lift the status. */
  missing: string[];
  /** Conflicting evidence that must be reviewed by a human. */
  conflicts: string[];
  /** Which deterministic checks ran (e.g. "citation validity", "version match"). */
  checked: string[];
}

/** The expandable sections of an answer card. */
export type AnswerSectionId =
  | "answer"
  | "evidence"
  | "reasoning"
  | "assumptions"
  | "tools"
  | "exclusions"
  | "audit";

export interface EvidenceDrawerTarget {
  label: string;
  source_pdf: string;
  page?: number;
  page_end?: number;
  section: string;
  release: string;
  platform: string;
  module: string;
  requirement_ids: string[];
  snippet: string;
  source_id: string;
  relevance: number;
}

/* ------------------------------------------------------------------ *
 * Workspace modules (/api/v2/modules)
 * ------------------------------------------------------------------ */

export type ModuleStatus = "available" | "partial" | "planned";

export interface WorkspaceModule {
  id: string;
  title: string;
  /** Target route inside the workspace. */
  href: string;
  status: ModuleStatus;
  description: string;
  /** What the module can do today, in one sentence. */
  capability: string;
  /** What is missing, when the module is not yet complete. */
  missing: string;
  /** Phase of the target architecture that completes the module. */
  phase: string;
}

export interface ModuleCatalogue {
  workspace: { id: string; title: string; project: string; scope: string };
  modules: WorkspaceModule[];
}

/* ------------------------------------------------------------------ *
 * ARXML Explorer (/api/v2/arxml)
 * ------------------------------------------------------------------ */

export interface ArxmlToolSpec {
  name: string;
  description: string;
  mutating: boolean;
  inputs: string[];
}

export interface ArxmlV2Artifact {
  artifact_id: string;
  source_path: string;
  source_sha256: string;
  autosar_release: string;
  schema_version: string;
  parse_status: string;
  tenant_id: string;
  project_scope: string;
  counts: {
    components: number;
    ports: number;
    interfaces: number;
    connectors: number;
    runnables: number;
    ecuc_parameters: number;
  };
}

export interface ArxmlV2Port {
  short_name: string;
  qualified_name: string;
  direction: string;
  interface_type?: string | null;
  interface_ref?: string | null;
  line_start?: number;
}

export interface ArxmlV2Component {
  short_name: string;
  qualified_name: string;
  component_type: string;
  line_start?: number;
  ports: ArxmlV2Port[];
}

export interface ArxmlV2Tree {
  artifact_id: string;
  source_path: string;
  autosar_release: string;
  components: ArxmlV2Component[];
  counts: Record<string, number>;
}

export interface ArxmlFinding {
  check: string;
  severity: string;
  message: string;
  line_start?: number | null;
  qualified_name?: string;
  ref?: string;
  reason?: string;
}

export interface ArxmlValidationResult {
  tool: string;
  status: string;
  severity: string;
  message: string;
  artifact_id: string;
  source_path: string;
  checks: { check: string; passed: boolean; detail: string }[];
  findings: ArxmlFinding[];
  scope: Record<string, number>;
  summary?: string;
}
