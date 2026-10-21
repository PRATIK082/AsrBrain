"use client";
import { useEffect, useMemo, useState } from "react";
import { api } from "../../lib/api";
import type { EvidenceDrawerTarget, ModuleCatalogue, SourceEvidence } from "../../lib/types";
import { AssistantShell } from "../assistant/AssistantShell";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { EmptyModule } from "./EmptyModule";
import { ModuleNav } from "./ModuleNav";
import { ArxmlExplorer } from "./ArxmlExplorer";

/**
 * Modules that are backed by a working surface today. Everything else renders
 * an honest empty state that says what exists and what is still planned.
 */
const SURFACE_BY_MODULE: Record<string, string> = {
  chat: "assistant",
  diffs: "diff",
  code: "code",
};

/** Modules with a dedicated explorer instead of the assistant surface. */
const EXPLORER_BY_MODULE: Record<string, string> = {
  arxml: "arxml",
};

/** Offline fallback so the workspace still renders without the API. */
const FALLBACK: ModuleCatalogue = {
  workspace: {
    id: "default",
    title: "AsrBrain Engineering Workspace",
    project: "local",
    scope: "default workspace",
  },
  modules: [
    {
      id: "chat",
      title: "Evidence Chat",
      href: "#/chat",
      status: "available",
      description:
        "Ask the indexed AUTOSAR corpus. Every claim is cited to a document, page and section.",
      capability:
        "Cited answers, the retrieval steps that produced them and the sources behind them.",
      missing: "",
      phase: "Phase 1 — shipping now",
    },
    {
      id: "knowledge",
      title: "Knowledge Ingestion",
      href: "#/knowledge",
      status: "partial",
      description:
        "Import specifications, ARXML and project sources and keep every version traceable.",
      capability:
        "PDF ingestion into the canonical store with page-level provenance, plus an ARXML upload endpoint.",
      missing:
        "Artifact registry, version history, access policy and background ingestion jobs (Phase 2–3).",
      phase: "Phase 2–3",
    },
    {
      id: "arxml",
      title: "ARXML Explorer",
      href: "#/arxml",
      status: "available",
      description:
        "Deterministic component, port, interface and ECUC topology parsed from the uploaded ARXML.",
      capability:
        "Topology, neighbour traversal and unresolved-reference reporting straight from the parser.",
      missing:
        "Line-level locations, UUIDs, schema validation results and a typed graph projection (Phase 4).",
      phase: "Phase 4",
    },
    {
      id: "graph",
      title: "Knowledge Graph Explorer",
      href: "#/graph",
      status: "planned",
      description:
        "Typed nodes and edges across requirements, ARXML elements, code symbols and test cases.",
      capability: "Nothing yet — the current graph is derived per request and is not persisted.",
      missing:
        "Typed graph store with provenance, traversal API and the graph explorer UI (Phase 2 and 4).",
      phase: "Phase 2, 4, 5",
    },
    {
      id: "requirements",
      title: "Requirement Traceability",
      href: "#/requirements",
      status: "partial",
      description:
        "Normalise requirements, link them to code and tests, and show coverage and orphans.",
      capability:
        "Requirement identifiers are extracted from the specification corpus and are searchable.",
      missing:
        "Requirement ingestion, revision status, reviewed trace links and the traceability matrix (Phase 6).",
      phase: "Phase 6",
    },
    {
      id: "tests",
      title: "Test & Log Intelligence",
      href: "#/tests",
      status: "planned",
      description: "Ingest test results and logs, cluster failures and link them to changes.",
      capability: "Nothing yet.",
      missing: "Test adapters, failure clustering and the test timeline (Phase 6).",
      phase: "Phase 6",
    },
    {
      id: "diffs",
      title: "Diffs & Impact",
      href: "#/diffs",
      status: "available",
      description: "Structural diff between two entity sets with compatibility risk per change.",
      capability:
        "Entity-keyed diff with added/removed/modified classification and canned migration guidance.",
      missing:
        "ChangeSet model, dependency-aware impact analysis and ARXML version diffing (Phase 7).",
      phase: "Phase 7",
    },
    {
      id: "diagrams",
      title: "Mermaid & Report Studio",
      href: "#/diagrams",
      status: "partial",
      description: "Recreate diagrams from specification figures and export evidence packages.",
      capability:
        "Server-side Mermaid recreation from page images and PDF figure analysis through the local vision model.",
      missing:
        "No studio UI in the React app yet, no diagram evidence binding and no PDF evidence package (Phase 7).",
      phase: "Phase 7",
    },
    {
      id: "code",
      title: "Code Review",
      href: "#/code",
      status: "available",
      description: "Advisory static checks on a C snippet. A human approves every change.",
      capability: "Deterministic findings and SARIF export.",
      missing: "Code symbol graph, commit anchoring and change approval workflow (Phase 3, 6).",
      phase: "Phase 3, 6",
    },
    {
      id: "evaluation",
      title: "Evaluation & Audit",
      href: "#/evaluation",
      status: "partial",
      description: "Measure answer quality, citation validity and abstention quality over a golden set.",
      capability: "A benchmark runner over the seeded AUTOSAR question set.",
      missing:
        "Answerability ground truth, per-route latency and cost metrics and a full audit trail (Phase 5, 8).",
      phase: "Phase 5, 8",
    },
  ],
};

function toDrawerTarget(evidence: SourceEvidence): EvidenceDrawerTarget {
  return {
    label: evidence.label,
    source_pdf: evidence.source_pdf,
    page: evidence.page,
    page_end: evidence.page_end,
    section: evidence.section,
    release: evidence.release,
    platform: evidence.platform,
    module: evidence.module,
    requirement_ids: evidence.requirement_ids ?? [],
    snippet: evidence.snippet,
    source_id: evidence.source_id,
    relevance: evidence.relevance,
  };
}

/**
 * The engineering workbench shell.
 *
 * Left: workspace + module navigation. Centre: the active module.
 * Right: the evidence drawer, opened from any citation in an answer.
 */
export function WorkspaceShell() {
  const [catalogue, setCatalogue] = useState<ModuleCatalogue>(FALLBACK);
  const [moduleId, setModuleId] = useState("chat");
  const [surface, setSurface] = useState("assistant");
  const [drawer, setDrawer] = useState<EvidenceDrawerTarget | null>(null);
  const [catalogueError, setCatalogueError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .listModules()
      .then((d) => {
        if (!cancelled && d?.modules?.length) setCatalogue(d);
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setCatalogueError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const active = useMemo(
    () => catalogue.modules.find((m) => m.id === moduleId) ?? catalogue.modules[0],
    [catalogue, moduleId],
  );

  const selectModule = (id: string) => {
    setModuleId(id);
    const target = SURFACE_BY_MODULE[id];
    if (target) setSurface(target);
    setDrawer(null);
  };

  const surfaceModule = active ? SURFACE_BY_MODULE[active.id] : undefined;
  const explorerModule = active ? EXPLORER_BY_MODULE[active.id] : undefined;

  return (
    <div className="flex h-screen overflow-hidden bg-ink-900 text-fg">
      <ModuleNav
        catalogue={catalogue}
        activeId={active?.id ?? "chat"}
        onSelect={selectModule}
      />

      <div className="relative flex min-w-0 flex-1">
        {explorerModule ? (
          <ArxmlExplorer />
        ) : surfaceModule ? (
          <AssistantShell
            surface={surface}
            onSurfaceChange={setSurface}
            hideHeader
            hideSurfaces
            onSelectEvidence={(e) => setDrawer(toDrawerTarget(e))}
          />
        ) : (
          <EmptyModule module={active} onNavigate={selectModule} />
        )}

        {catalogueError && (
          <div className="absolute left-1/2 top-3 -translate-x-1/2 rounded border border-warn/40 bg-warn/10 px-3 py-1.5 text-2xs text-warn">
            Module catalogue unavailable — showing the built-in list ({catalogueError})
          </div>
        )}

        <EvidenceDrawer target={drawer} onClose={() => setDrawer(null)} />
      </div>
    </div>
  );
}
