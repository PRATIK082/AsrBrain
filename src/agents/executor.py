"""Bounded agent executor: plan -> tool call -> observation -> answer.

Safety rules enforced here (not in the prompt):

* a hard step limit (`max_steps`), never exceeded
* only tools present in the registry can run
* a failing tool never aborts the run - it becomes an observation
* the final answer is always built from the observations; when a model is available it
  is constrained to cite them, and when it is not the deterministic digest is returned
* mutating tools are only executed when the caller explicitly allows them
"""
from __future__ import annotations

import json
import time
from typing import Iterator

from ..tools.base import REGISTRY, ToolRegistry
from .planner import Plan, PlanStep, detect_intent, plan_task

MAX_STEPS = 6
ALLOW_MUTATING = False


class AgentExecutor:
    def __init__(self, registry: ToolRegistry | None = None, max_steps: int = MAX_STEPS,
                 allow_mutating: bool = ALLOW_MUTATING) -> None:
        self.registry = registry or REGISTRY
        self.max_steps = max(1, int(max_steps))
        self.allow_mutating = allow_mutating

    # ------------------------------------------------------------------ run
    def run(self, query: str, plan: Plan | None = None, spec=None,
            context: dict | None = None) -> Iterator[dict]:
        """Yield agent events; the last one is always `complete`."""
        ctx = dict(context or {})
        started = time.time()
        if plan is None:
            plan = plan_task(query, spec=spec, registry=self.registry, max_steps=self.max_steps)
        yield {"event": "plan", "plan": plan.to_dict(), "intent": detect_intent(query)}

        observations: list[dict] = []
        trace: list[dict] = []
        for index, step in enumerate(plan.steps[: self.max_steps], start=1):
            spec_obj = self.registry.get(step.tool)
            if spec_obj is None:
                continue
            if spec_obj.mutating and not self.allow_mutating:
                yield {"event": "tool_skipped", "tool": step.tool,
                       "reason": "mutating tools are disabled for this run"}
                continue
            args = self._resolve_args(step, ctx)
            yield {"event": "tool_call", "index": index, "tool": step.tool,
                   "args": args, "purpose": step.purpose}
            result = self.registry.invoke(step.tool, args)
            summary = summarize_tool_result(step.tool, result)
            observations.append({"tool": step.tool, "summary": summary,
                                 "data": result.data if result.ok else {},
                                 "ok": result.ok})
            trace.append({"index": index, "tool": step.tool, "args": args,
                          "ok": result.ok, "duration_ms": result.duration_ms,
                          "error": result.error, "purpose": step.purpose})
            yield {"event": "tool_result", "index": index, "tool": step.tool,
                   "ok": result.ok, "duration_ms": result.duration_ms,
                   "error": result.error, "summary": summary,
                   "data": _trim(result.data)}

        answer = self._compose(query, observations, spec)
        yield {"event": "complete",
               "answer": answer["text"],
               "citations": answer["citations"],
               "observations": [{"tool": o["tool"], "summary": o["summary"], "ok": o["ok"]}
                                for o in observations],
               "trace": trace,
               "plan": plan.to_dict(),
               "intent": detect_intent(query),
               "elapsed_ms": int((time.time() - started) * 1000)}

    # -------------------------------------------------------------- helpers
    def _resolve_args(self, step: PlanStep, ctx: dict) -> dict:
        """Fill placeholders such as ``{topic}`` / ``{artifact_id}`` from the context."""
        args: dict = {}
        for key, value in (step.args or {}).items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                key_name = value[1:-1]
                args[key] = ctx.get(key_name, value)
            else:
                args[key] = value
        if "query" in args and not args["query"]:
            args["query"] = ctx.get("query", "")
        return args

    def _compose(self, query: str, observations: list[dict], spec) -> dict:
        """Build the final answer from the observations (cited)."""
        citations: list[dict] = []
        blocks: list[str] = []
        for i, obs in enumerate(observations, start=1):
            label = f"G{i}"
            citations.append({"label": label, "tool": obs["tool"],
                              "summary": obs["summary"][:400]})
            blocks.append(f"[{label}] tool={obs['tool']}\n{obs['summary']}")
        if not blocks:
            return {"text": "## Result\n\nNo tool produced evidence for this request. "
                            "Run `graph.build` to index the corpus, or register a project "
                            "source first.", "citations": []}
        context = "\n\n".join(blocks)
        if spec is not None:
            from ..generation.providers import complete
            prompt = (("You are an AUTOSAR engineering agent. Answer the user request using ONLY "
                       "the tool observations below. Cite every claim with [G<number>]. If the "
                       "observations do not answer the question, say exactly what is missing. "
                       "Never invent identifiers, files or values.\n\n"
                       f"Observations:\n{context}\n\nUser request: {query}\n\n"
                       "Structure: ## Result, ## Evidence, ## Gaps or next steps."))
            draft, note = complete(prompt, spec)
            if draft:
                return {"text": draft, "citations": citations}
        digest = "\n\n".join(f"### [{c['label']}] {c['tool']}\n{c['summary']}"
                             for c in citations)
        text = ("## Result\n\nThe agent executed "
                f"{len(citations)} tool call(s) for this request.\n\n"
                f"{digest}\n\n## Gaps or next steps\n"
                "- Provide more specific identifiers (requirement id, symbol, artifact id) "
                "to narrow the result.\n"
                "- Inferred links are flagged; confirm them against the source artefacts.")
        return {"text": text, "citations": citations}


# ------------------------------------------------------------------ summaries
def summarize_tool_result(tool: str, result) -> str:
    """Compact, human-readable digest of one tool result."""
    if not result.ok:
        return f"ERROR: {result.error}"
    data = result.data or {}
    if tool == "graph.search":
        nodes = data.get("nodes", [])[:8]
        return ("nodes: " + ", ".join(f"{n['type']}:{n['label']}" for n in nodes)
                + (f" | communities: {len(data.get('communities', []))}" if data.get("communities") else ""))
    if tool == "graph.neighbors":
        return ("neighbourhood of " + str(data.get("node", "")) + ": "
                + ", ".join(f"{n['type']}:{n['label']}" for n in data.get("nodes", [])[:8]))
    if tool == "graph.path":
        return "path: " + " -> ".join(data.get("path", [])) if data.get("found") else "no path found"
    if tool == "graph.communities":
        return "; ".join(f"{c.get('title', '')} ({c.get('member_count', 0)} members)"
                         for c in data.get("communities", [])[:6])
    if tool == "graph.community":
        return f"{data.get('title', '')}: {data.get('summary', '')}"
    if tool == "graph.stats":
        return (f"nodes={data.get('nodes', 0)} edges={data.get('edges', 0)} "
                f"communities={data.get('communities', 0)} traces={data.get('trace_links', 0)}")
    if tool == "graph.build":
        return (f"built {data.get('nodes', 0)} nodes / {data.get('edges', 0)} edges "
                f"from {data.get('chunks', 0)} chunks in {data.get('elapsed_s', 0)}s")
    if tool == "mindmap.build":
        return "mindmap:\n" + str(data.get("mermaid", ""))[:1500]
    if tool.startswith("arxml."):
        return _json_digest(data, keys=("found", "hit_count", "components", "ports",
                                        "interfaces", "runnables", "ecuc_parameters"))
    if tool.startswith("code."):
        return _json_digest(data, keys=("error", "rte_calls", "source"))
    if tool.startswith("trace."):
        return _json_digest(data, keys=("count", "requirements", "tests", "rows",
                                        "without_code", "without_test"))
    return _json_digest(data)


def _json_digest(data: dict, keys: tuple[str, ...] = ()) -> str:
    if keys:
        parts = [f"{k}={data[k]}" for k in keys if k in data]
        if parts:
            return ", ".join(parts)
    try:
        return json.dumps(data, ensure_ascii=False)[:1200]
    except Exception:
        return str(data)[:1200]


def _trim(data: dict, limit: int = 4000) -> dict:
    """Keep the SSE payload small: truncate big collections."""
    out: dict = {}
    for k, v in (data or {}).items():
        if isinstance(v, list) and len(v) > 25:
            out[k] = v[:25]
        elif isinstance(v, str) and len(v) > limit:
            out[k] = v[:limit] + "…"
        else:
            out[k] = v
    return out
