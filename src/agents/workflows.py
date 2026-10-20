"""Deterministic agent workflows for the automotive domain.

A workflow is a *fixed* plan (not a model-decided one) over the shared tool
registry.  Each workflow states up-front which tools it calls, in which order and
with which arguments, so the result is reproducible and auditable.  The model is
only used for the final phrasing of the answer; the facts always come from tool
observations.

The four workflows map onto the four questions engineers ask most often:

``arxml_requirement_trace``
    Which ARXML artefacts, ports, runnables and ECUC values implement a requirement?
``code_requirement_trace``
    Which C functions implement a requirement and which test cases cover it?
``impact_analysis``
    What breaks if a symbol / module / requirement changes?
``deep_explanation``
    Give me the full picture (graph + communities + traceability + mindmap).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .planner import Plan, PlanStep, extract_identifiers

# --------------------------------------------------------------------- context
DEFAULT_CONTEXT = {
    "query": "",
    "requirement": "",
    "symbol": "",
    "module": "",
    "node": "",
    "artifact_id": "",
    "tenant": "default",
    "path": "",
    "parameter": "",
    "topic": "",
}


def base_context(query: str, extra: dict | None = None) -> dict:
    """Context pre-filled from the query (identifiers, topic, module guesses)."""
    ctx = dict(DEFAULT_CONTEXT)
    ctx["query"] = query or ""
    ctx["topic"] = query or ""
    ids = extract_identifiers(query or "")
    if ids["requirements"]:
        ctx["requirement"] = ids["requirements"][0]
        ctx["parameter"] = ids["requirements"][0]
    if ids["symbols"]:
        ctx["symbol"] = ids["symbols"][0]
    for module in _KNOWN_MODULES:
        if module.lower() in (query or "").lower():
            ctx["module"] = module
            break
    # best identifier for a graph node: requirement > symbol > module
    ctx["node"] = ctx["requirement"] or ctx["symbol"] or ctx["module"]
    ctx.update({k: v for k, v in (extra or {}).items() if v not in (None, "")})
    return ctx


_KNOWN_MODULES = (
    "CanIf", "Com", "PduR", "Dem", "Dcm", "EcuC", "NvM", "MemIf", "Fee", "Flsm",
    "Ea", "Eep", "Wdg", "Gpt", "I2C", "Spi", "CanTp", "Tpms", "Uds", "SecOc",
    "Csm", "CrypIf", "SchM", "Rte", "BswM", "ComM", "Nm", "EcuM", "Det",
)


@dataclass
class Workflow:
    """A named, deterministic sequence of tool calls."""

    name: str
    title: str
    description: str
    intent: str
    tools: list[str]
    steps: list[PlanStep]
    context_keys: list[str] = field(default_factory=list)
    prepare: Callable[[dict, object], dict] | None = None
    summarize: Callable[[list[dict], dict], str] | None = None

    def plan(self, context: dict) -> Plan:
        steps = [PlanStep(s.tool, dict(s.args), s.purpose) for s in self.steps]
        return Plan(steps=steps, rationale=f"workflow:{self.name}", mode="workflow")

    def to_dict(self) -> dict:
        return {"name": self.name, "title": self.title, "description": self.description,
                "intent": self.intent, "tools": list(self.tools),
                "context_keys": list(self.context_keys),
                "steps": [s.to_dict() for s in self.steps]}


# ------------------------------------------------------------------ helpers
def _obs(observations: list[dict], tool: str) -> dict | None:
    for obs in observations:
        if obs.get("tool") == tool and obs.get("ok"):
            return obs.get("data") or {}
    return None


def _bullets(values, limit: int = 12) -> list[str]:
    out: list[str] = []
    for v in list(values or [])[:limit]:
        if isinstance(v, dict):
            label = v.get("label") or v.get("requirement") or v.get("test_case") or v.get("id") \
                or v.get("name") or str(v)
            extra = ""
            for key in ("confidence", "is_inferred", "value", "type", "kind", "xpath"):
                if key in v and v[key] not in (None, ""):
                    extra += f" ({key}={v[key]})"
            out.append(f"- {label}{extra}")
        else:
            out.append(f"- {v}")
    return out


def _section(title: str, lines: list[str], empty_hint: str = "") -> list[str]:
    if not lines:
        if not empty_hint:
            return []
        return [f"## {title}", "", f"- {empty_hint}", ""]
    return [f"## {title}", ""] + list(lines) + [""]


def _footer(observations: list[dict]) -> list[str]:
    failed = [o for o in observations if not o.get("ok")]
    if not failed:
        return ["## Gaps or next steps", "",
                "- Inferred links are flagged `is_inferred=true`; confirm them against the "
                "source artefacts before signing off.",
                "- Add more context (release, ECU, module) to narrow the result."]
    lines = [f"- `{o['tool']}` failed: {o.get('summary', '')}" for o in failed]
    return ["## Gaps or next steps", ""] + lines


# --------------------------------------------------------------- ARXML trace
def _prepare_arxml(ctx: dict, registry) -> dict:
    """Resolve the ARXML artifact to work on (explicit id wins)."""
    if ctx.get("artifact_id"):
        return ctx
    try:
        result = registry.invoke("arxml.artifacts", {"tenant": ctx.get("tenant", "default")})
        if result.ok:
            artifacts = (result.data or {}).get("artifacts") or []
            if artifacts:
                ctx["artifact_id"] = artifacts[0]["artifact_id"]
                ctx["artifact_options"] = [a["artifact_id"] for a in artifacts]
    except Exception:
        pass
    return ctx


def _summarize_arxml(observations: list[dict], ctx: dict) -> str:
    req = ctx.get("requirement") or ctx.get("query") or "the request"
    search = _obs(observations, "arxml.search") or {}
    topo = _obs(observations, "arxml.topology") or {}
    cfg = _obs(observations, "arxml.config") or {}
    tests = _obs(observations, "trace.tests") or {}
    arts = _obs(observations, "arxml.artifacts") or {}

    out = [f"### ARXML trace for `{req}`", ""]
    art_lines = [f"- {a['artifact_id']} ({a.get('components', 0)} components, "
                 f"{a.get('ports', 0)} ports, {a.get('runnables', 0)} runnables)"
                 for a in (arts.get("artifacts") or [])[:8]]
    out += _section("Artifacts", art_lines,
                    "No ARXML artifact is loaded for this tenant - upload one via "
                    "/api/arxml/parse first.")
    hits = search.get("hits") or []
    out += _section("Matching ARXML elements",
                    [f"- [{h.get('kind')}] {h.get('label')} ({h.get('id')})"
                     + (f" - xpath {h['xpath']}" if h.get("xpath") else "")
                     for h in hits[:12]],
                    "No ARXML element matches the request.")
    if topo:
        out += _section("Topology",
                        [f"- components: {len(topo.get('components') or [])}",
                         f"- ports: {len(topo.get('ports') or [])}",
                         f"- interfaces: {len(topo.get('interfaces') or [])}",
                         f"- runnables: {len(topo.get('runnables') or [])}",
                         f"- connectors: {len(topo.get('connectors') or [])}",
                         f"- ecuc parameters: {len(topo.get('ecuc_parameters') or [])}"]
                        )
    cfg_lines = [f"- {h.get('parameter')} = {h.get('value')!r} ({h.get('value_type')})"
                 for h in (cfg.get("hits") or [])[:10]]
    out += _section("ECUC configuration", cfg_lines,
                    "No ECUC parameter matches the request.")
    test_lines = [f"- {t.get('test_case')} covers {t.get('covers')}"
                  f" (confidence={t.get('confidence')}, inferred={t.get('is_inferred')})"
                  for t in (tests.get("tests") or [])[:10]]
    out += _section("Test coverage", test_lines,
                    "No test case is linked to this requirement in the graph.")
    out += _footer(observations)
    return "\n".join(x for x in out if x is not None)


# ----------------------------------------------------------------- code trace
def _prepare_code(ctx: dict, registry) -> dict:
    if not ctx.get("module"):
        for module in _KNOWN_MODULES:
            if module.lower() in (ctx.get("query", "") or "").lower():
                ctx["module"] = module
                break
    if not ctx.get("symbol"):
        ctx["symbol"] = ctx.get("requirement") or ctx.get("module") or ""
    return ctx


def _summarize_code(observations: list[dict], ctx: dict) -> str:
    target = ctx.get("symbol") or ctx.get("query") or "the request"
    syms = _obs(observations, "code.symbols") or {}
    cg = _obs(observations, "code.callgraph") or {}
    rte = _obs(observations, "code.rte_map") or {}
    reqs = _obs(observations, "trace.requirements") or {}
    tests = _obs(observations, "trace.tests") or {}

    out = [f"### C code trace for `{target}`", ""]
    fn_lines = [f"- {f.get('name')} ({f.get('file')}:{f.get('line')})"
                for f in ((syms.get("functions") or []))[:12]]
    out += _section("Functions", fn_lines,
                    "No C function matched - index a code folder with graph.build "
                    "code_dirs or pass a source snippet.")
    if cg:
        callers = [f"- {c}" for c in (cg.get("callers") or [])[:10]]
        callees = [f"- {c}" for c in (cg.get("callees") or [])[:10]]
        out += _section("Call graph", callers + callees)
    rte_lines = [f"- {t.get('source_id')} -> {t.get('target_id')} "
                  f"({t.get('link_type')}, confidence={t.get('confidence')})"
                  for t in (rte.get("traceability") or [])[:10]]
    if not rte_lines:
        rte_lines = [f"- {r}" for r in (rte.get("rte_calls") or [])[:10]]
    out += _section("RTE / port mapping", rte_lines)
    req_lines = [f"- {r.get('requirement')} (via {r.get('via')}, "
                 f"confidence={r.get('confidence')}, inferred={r.get('is_inferred')})"
                 for r in (reqs.get("requirements") or [])[:12]]
    out += _section("Requirements", req_lines,
                    "No requirement is linked to this symbol.")
    test_lines = [f"- {t.get('test_case')} covers {t.get('covers')}"
                  f" (confidence={t.get('confidence')}, inferred={t.get('is_inferred')})"
                  for t in (tests.get("tests") or [])[:12]]
    out += _section("Test cases", test_lines,
                    "No test case is linked to this symbol.")
    out += _footer(observations)
    return "\n".join(x for x in out if x is not None)


# -------------------------------------------------------------- impact analysis
def _prepare_impact(ctx: dict, registry) -> dict:
    if not ctx.get("symbol"):
        ctx["symbol"] = ctx.get("requirement") or ctx.get("node") or ctx.get("query") or ""
    if not ctx.get("node"):
        ctx["node"] = ctx.get("requirement") or ctx.get("symbol") or ctx.get("query") or ""
    return ctx


def _summarize_impact(observations: list[dict], ctx: dict) -> str:
    target = ctx.get("symbol") or ctx.get("query") or "the change"
    gs = _obs(observations, "graph.search") or {}
    nb = _obs(observations, "graph.neighbors") or {}
    matrix = _obs(observations, "trace.matrix") or {}
    gaps = _obs(observations, "trace.gaps") or {}

    out = [f"### Impact analysis for `{target}`", ""]
    node_lines = [f"- [{n.get('type')}] {n.get('label')}"
                  + (f" (community {n.get('community')})" if n.get("community") else "")
                  for n in (gs.get("nodes") or [])[:12]]
    out += _section("Related graph nodes", node_lines,
                    "No graph node matched - build the graph with graph.build first."
                    )
    neigh_lines = [f"- [{n.get('type')}] {n.get('label')}"
                   for n in (nb.get("nodes") or [])[:12]]
    out += _section("Direct neighbourhood", neigh_lines,
                    "The node was not found in the graph; check the identifier."
                    )
    if matrix:
        out += _section("Traceability matrix",
                        [f"- requirements: {matrix.get('requirements', 0)}",
                         f"- functions: {matrix.get('functions', 0)}",
                         f"- apis: {matrix.get('apis', 0)}",
                         f"- test cases: {matrix.get('test_cases', 0)}",
                         f"- rows: {matrix.get('row_count', 0)}"])
    if gaps:
        out += _section("Gaps",
                        [f"- without code: {len(gaps.get('without_code') or [])}",
                         f"- without test: {len(gaps.get('without_test') or [])}"]
                        + _bullets(gaps.get("without_code") or [], 8))
    out += _footer(observations)
    return "\n".join(x for x in out if x is not None)


# ------------------------------------------------------------ deep explanation
def _summarize_deep(observations: list[dict], ctx: dict) -> str:
    topic = ctx.get("topic") or ctx.get("query") or "the topic"
    gs = _obs(observations, "graph.search") or {}
    comm = _obs(observations, "graph.communities") or {}
    reqs = _obs(observations, "trace.requirements") or {}
    mm = _obs(observations, "mindmap.build") or {}

    out = [f"### Deep explanation of `{topic}`", ""]
    node_lines = [f"- [{n.get('type')}] {n.get('label')}"
                  for n in (gs.get("nodes") or [])[:12]]
    out += _section("Graph nodes", node_lines,
                    "No graph node matched - build the graph first.")
    comm_lines = [f"- {c.get('title')} — {c.get('summary', '')}"
                  for c in (comm.get("communities") or [])[:6]]
    out += _section("Communities", comm_lines,
                    "No community was ranked for this query.")
    req_lines = [f"- {r.get('requirement')} (via {r.get('via')})"
                 for r in (reqs.get("requirements") or [])[:10]]
    out += _section("Related requirements", req_lines,
                    "No requirement matched the topic.")
    mermaid = mm.get("mermaid") or ""
    if mermaid:
        out += ["## Mindmap", "", "```mermaid", mermaid, "```"]
    out += _footer(observations)
    return "\n".join(x for x in out if x is not None)


# ------------------------------------------------------------------ workflows
WORKFLOW_LIST: list[Workflow] = [
    Workflow(
        name="arxml_requirement_trace",
        title="ARXML requirement trace",
        description=("Trace a requirement through the ARXML artefacts: components, ports, "
                     "interfaces, runnables, connectors and ECUC values, then to the test "
                     "cases that cover it."),
        intent="arxml_trace",
        tools=["arxml.artifacts", "arxml.search", "arxml.topology", "arxml.config",
               "trace.tests"],
        context_keys=["query", "requirement", "artifact_id", "tenant", "parameter"],
        prepare=_prepare_arxml,
        summarize=_summarize_arxml,
        steps=[
            PlanStep("arxml.artifacts", {"tenant": "{tenant}"},
                     "enumerate the ARXML artefacts available for the tenant"),
            PlanStep("arxml.search", {"query": "{query}", "artifact_id": "{artifact_id}",
                                      "tenant": "{tenant}"},
                     "locate components/ports/runnables/ECUC matching the request"),
            PlanStep("arxml.topology", {"artifact_id": "{artifact_id}", "tenant": "{tenant}"},
                     "dump the deterministic topology of the selected artefact"),
            PlanStep("arxml.config", {"parameter": "{parameter}",
                                      "artifact_id": "{artifact_id}", "tenant": "{tenant}"},
                     "resolve the ECUC configuration values"),
            PlanStep("trace.tests", {"query": "{query}"},
                     "find the test cases that cover the requirement"),
        ],
    ),
    Workflow(
        name="code_requirement_trace",
        title="C code requirement trace",
        description=("Trace a requirement or symbol into the C implementation: functions, "
                     "call graph, RTE/port usage, the requirements it satisfies and the "
                     "test cases that cover it."),
        intent="code_trace",
        tools=["code.symbols", "code.callgraph", "code.rte_map", "trace.requirements",
               "trace.tests"],
        context_keys=["query", "symbol", "module", "path"],
        prepare=_prepare_code,
        summarize=_summarize_code,
        steps=[
            PlanStep("code.symbols", {"module": "{module}", "path": "{path}"},
                     "list the C functions of the module / file"),
            PlanStep("code.callgraph", {"function": "{symbol}", "path": "{path}", "depth": 2},
                     "walk the call graph around the symbol"),
            PlanStep("code.rte_map", {"path": "{path}"},
                     "map RTE_* call sites to ARXML ports"),
            PlanStep("trace.requirements", {"query": "{query}"},
                     "resolve the requirements the code satisfies"),
            PlanStep("trace.tests", {"query": "{query}"},
                     "resolve the test cases covering the requirement"),
        ],
    ),
    Workflow(
        name="impact_analysis",
        title="Impact analysis",
        description=("Determine the blast radius of a change: related graph nodes, direct "
                     "neighbourhood, the requirement/code/test matrix and the coverage gaps."),
        intent="impact",
        tools=["graph.search", "graph.neighbors", "trace.matrix", "trace.gaps"],
        context_keys=["query", "symbol", "module", "node"],
        prepare=_prepare_impact,
        summarize=_summarize_impact,
        steps=[
            PlanStep("graph.search", {"query": "{query}", "mode": "hybrid", "depth": 2,
                                      "limit": 25},
                     "retrieve the related subgraph"),
            PlanStep("graph.neighbors", {"node": "{node}", "depth": 2},
                     "expand the direct neighbourhood of the changed element"),
            PlanStep("trace.matrix", {"module": "{module}"},
                     "build the requirement / api / code / test matrix"),
            PlanStep("trace.gaps", {"module": "{module}"},
                     "list requirements without code or without a test"),
        ],
    ),
    Workflow(
        name="deep_explanation",
        title="Deep explanation",
        description=("Full picture of a topic: graph neighbourhood, community summaries, "
                     "related requirements and a Mermaid mindmap."),
        intent="mindmap",
        tools=["graph.search", "graph.communities", "trace.requirements", "mindmap.build"],
        context_keys=["query", "topic"],
        prepare=None,
        summarize=_summarize_deep,
        steps=[
            PlanStep("graph.search", {"query": "{query}", "mode": "hybrid", "depth": 2,
                                      "limit": 30},
                     "retrieve the local and global graph context"),
            PlanStep("graph.communities", {"query": "{query}", "limit": 6},
                     "rank the knowledge-graph communities"),
            PlanStep("trace.requirements", {"query": "{query}"},
                     "collect the related requirements"),
            PlanStep("mindmap.build", {"topic": "{topic}", "source": "auto", "depth": 2},
                     "render the mindmap"),
        ],
    ),
]

WORKFLOWS: dict[str, Workflow] = {w.name: w for w in WORKFLOW_LIST}


def list_workflows() -> list[dict]:
    """Workflow catalogue for the API / UI."""
    return [w.to_dict() for w in WORKFLOW_LIST]


def get_workflow(name: str) -> Workflow | None:
    return WORKFLOWS.get(name)


# intent -> workflow name (deterministic routing)
INTENT_WORKFLOW = {
    "arxml_trace": "arxml_requirement_trace",
    "code_trace": "code_requirement_trace",
    "impact": "impact_analysis",
    "mindmap": "deep_explanation",
    "trace": "code_requirement_trace",
    "graph": "impact_analysis",
}


def route_workflow(query: str, intent: str | None = None) -> str:
    """Pick the workflow for a query (deterministic keyword routing)."""
    from .planner import detect_intent
    intent = intent or detect_intent(query)
    return INTENT_WORKFLOW.get(intent, "deep_explanation")
