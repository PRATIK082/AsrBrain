"""Task planner for the agent loop.

Two planners share one interface:

* **LLM planner** - asks the model (via native tool calling when the provider supports
  it) which tools to call and with which arguments.
* **deterministic planner** - a keyword router that always works, even with no model
  available.  It is the default so the agent never blocks on a missing LLM.

Both produce a bounded list of `PlanStep`s.  The executor only ever runs tools that
exist in the registry and the planner can never exceed `max_steps`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..tools.base import REGISTRY, ToolRegistry

ARXML_WORDS = ("arxml", "swc", "port", "interface", "ecuc", "composition", "connect",
               "runnable", "rte generated", "ecu configuration")
CODE_WORDS = ("c code", "c file", ".c", ".h", "function", "implementation", "source code",
              "misra", "driver", "static analysis", "rte_", "buffer", "pointer")
TRACE_WORDS = ("requirement", "test case", "testcase", "coverage", "traceability",
               "trace", "matrix", "sw requirement", "sws_", "verif")
GRAPH_WORDS = ("graph", "relationship", "depends", "dependency", "impact", "neighbour",
               "neighbor", "community", "linked to", "connects")
MINDMAP_WORDS = ("mindmap", "mind map", "overview", "diagram", "tree", "structure",
                 "how does", "explain the")


@dataclass
class PlanStep:
    tool: str
    args: dict = field(default_factory=dict)
    purpose: str = ""

    def to_dict(self) -> dict:
        return {"tool": self.tool, "args": dict(self.args), "purpose": self.purpose}


@dataclass
class Plan:
    steps: list[PlanStep] = field(default_factory=list)
    rationale: str = ""
    mode: str = "deterministic"

    def to_dict(self) -> dict:
        return {"steps": [s.to_dict() for s in self.steps], "rationale": self.rationale,
                "mode": self.mode, "step_count": len(self.steps)}


def plan_task(query: str, spec=None, registry: ToolRegistry | None = None,
              max_steps: int = 6) -> Plan:
    """Plan tool calls for a user request."""
    reg = registry or REGISTRY
    if spec is not None:
        llm_plan = _llm_plan(query, spec, reg, max_steps)
        if llm_plan is not None:
            return llm_plan
    return deterministic_plan(query, reg, max_steps)


def deterministic_plan(query: str, registry: ToolRegistry | None = None,
                       max_steps: int = 6) -> Plan:
    """Keyword router: always available, fully explainable."""
    reg = registry or REGISTRY
    q = (query or "").lower()
    steps: list[PlanStep] = []
    reasons: list[str] = []

    wants_arxml = any(w in q for w in ARXML_WORDS)
    wants_code = any(w in q for w in CODE_WORDS)
    wants_trace = any(w in q for w in TRACE_WORDS)
    wants_graph = any(w in q for w in GRAPH_WORDS)
    wants_mindmap = any(w in q for w in MINDMAP_WORDS)

    if wants_arxml:
        steps.append(PlanStep("arxml.search", {"query": query}, "locate ARXML entities"))
        reasons.append("ARXML keywords detected")
    if wants_trace:
        steps.append(PlanStep("trace.requirements", {"query": query}, "map to requirements"))
        reasons.append("traceability keywords detected")
    if wants_code:
        steps.append(PlanStep("code.symbols", {}, "scan C symbols"))
        reasons.append("C code keywords detected")
    if wants_graph or not steps:
        steps.append(PlanStep("graph.search", {"query": query, "mode": "hybrid"},
                              "graph retrieval"))
        reasons.append("graph retrieval selected")
    if wants_mindmap:
        steps.append(PlanStep("mindmap.build", {"topic": query, "source": "auto"},
                              "build mindmap"))
        reasons.append("mindmap keywords detected")

    # keep only tools that actually exist
    steps = [s for s in steps if reg.get(s.tool) is not None][:max_steps]
    return Plan(steps=steps, rationale="; ".join(reasons) or "default graph retrieval",
                mode="deterministic")


def _llm_plan(query: str, spec, reg: ToolRegistry, max_steps: int) -> Plan | None:
    """Ask the model for a tool plan. Returns None when the provider cannot answer."""
    try:
        from ..generation.providers import chat_with_tools
    except Exception:
        return None
    allowed = reg.select(tags=None)[:40]
    schemas = [t.json_schema() for t in allowed]
    try:
        reply = chat_with_tools(
            [{"role": "system",
              "content": ("You are an AUTOSAR engineering agent. Choose the minimum set of "
                          "tools needed to answer the user request. Call tools only. "
                          "Do not answer directly.")},
             {"role": "user", "content": query}],
            schemas, spec)
    except Exception:
        return None
    calls = reply.get("tool_calls") or []
    steps: list[PlanStep] = []
    for call in calls[:max_steps]:
        name = call.get("name") or (call.get("function") or {}).get("name") or ""
        if reg.get(name) is None:
            continue
        raw_args = call.get("arguments") or (call.get("function") or {}).get("arguments") or {}
        if isinstance(raw_args, str):
            try:
                raw_args = json.loads(raw_args)
            except Exception:
                raw_args = {}
        if not isinstance(raw_args, dict):
            raw_args = {}
        steps.append(PlanStep(tool=name, args=raw_args, purpose="model selected"))
    if not steps:
        return None
    return Plan(steps=steps, rationale=reply.get("content", "")[:400] or "model tool plan",
                mode="llm")


# ------------------------------------------------------------------- intents
INTENTS = {
    "arxml_trace": ("arxml", "swc", "port", "ecuc", "composition", "ecu configuration"),
    "code_trace": (".c", "c code", "function", "implementation", "rte_", "driver"),
    "impact": ("impact", "affected", "change", "regression", "blast radius"),
    "mindmap": ("mindmap", "mind map", "diagram", "tree"),
    "trace": ("requirement", "test case", "coverage", "traceability", "matrix"),
    "graph": ("graph", "relationship", "dependency", "neighbour", "neighbor"),
}


def detect_intent(query: str) -> str:
    """Best-effort intent label used by the API and the UI."""
    q = (query or "").lower()
    best = "general"
    best_score = 0
    for intent, words in INTENTS.items():
        score = sum(1 for w in words if w in q)
        if score > best_score:
            best_score = score
            best = intent
    return best


def extract_identifiers(query: str) -> dict:
    """Pull AUTOSAR-ish identifiers out of a query (requirements, tests, symbols)."""
    out: dict[str, list[str]] = {"requirements": [], "tests": [], "symbols": []}
    out["requirements"] = re.findall(
        r"\b(?:SWS|SRS|RS|REQ|TSW|TPS|ASR)_[A-Za-z0-9]+_\d{3,6}\b", query or "")
    out["tests"] = re.findall(r"\b(?:TEST|TC|UT|IT)_[A-Za-z0-9_]{3,}\b", query or "")
    out["symbols"] = [s for s in re.findall(r"\b([A-Z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+)\b",
                                            query or "")
                      if s not in out["requirements"] and s not in out["tests"]]
    return out
