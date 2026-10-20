"""Workflow runner: executes a named workflow and streams the same events as the
generic agent loop.

The runner is intentionally thin - the workflow owns the plan, the executor owns the
tool invocation and the safety rules, and the runner only wires them together and
replaces the generic answer with the workflow-specific, deterministic report.
"""
from __future__ import annotations

from typing import Iterator

from ..tools.base import REGISTRY, ToolRegistry
from .executor import AgentExecutor
from .planner import detect_intent, plan_task
from .workflows import (WORKFLOWS, Workflow, base_context, get_workflow, list_workflows,
                        route_workflow)

MAX_STEPS = 8


def list_workflow_catalogue() -> list[dict]:
    return list_workflows()


def run_workflow(name: str, query: str, registry: ToolRegistry | None = None, spec=None,
                 context: dict | None = None, allow_mutating: bool = False,
                 max_steps: int = MAX_STEPS) -> Iterator[dict]:
    """Run one workflow; yields agent events ending with `complete`."""
    reg = registry or REGISTRY
    workflow = get_workflow(name)
    if workflow is None:
        yield {"event": "error", "error": f"unknown workflow: {name}",
               "available": list(WORKFLOWS)}
        return

    ctx = base_context(query, context)
    yield {"event": "workflow", "workflow": workflow.to_dict(),
           "context": {k: v for k, v in ctx.items() if k != "artifact_options"}}

    if workflow.prepare is not None:
        try:
            ctx = workflow.prepare(ctx, reg) or ctx
        except Exception as e:
            yield {"event": "tool_skipped", "tool": "workflow.prepare",
                   "reason": f"{type(e).__name__}: {e}"}

    executor = AgentExecutor(registry=reg, max_steps=max_steps,
                              allow_mutating=allow_mutating)
    plan = workflow.plan(ctx)

    observations: list[dict] = []
    answer_text = ""
    citations: list[dict] = []
    trace: list[dict] = []
    for event in executor.run(query, plan=plan, spec=spec, context=ctx):
        kind = event.get("event")
        if kind == "tool_result":
            observations.append({"tool": event.get("tool", ""),
                                 "summary": event.get("summary", ""),
                                 "ok": bool(event.get("ok")),
                                 "data": event.get("data") or {}})
        elif kind == "complete":
            answer_text = event.get("answer") or ""
            citations = event.get("citations") or []
            trace = event.get("trace") or []
            continue
        yield event

    if workflow.summarize is not None:
        try:
            report = workflow.summarize(observations, ctx)
        except Exception as e:
            report = f"## Result\n\nWorkflow summary failed: {type(e).__name__}: {e}"
        if report:
            digest = answer_text.strip()
            label = "### Tool digests" if spec is None else "### Model phrasing"
            answer_text = f"{report}\n\n---\n\n{label}\n\n{digest}".strip() if digest else report
    else:
        answer_text = answer_text or "## Result\n\nNo evidence was produced."

    yield {"event": "complete", "answer": answer_text, "citations": citations,
           "observations": [{"tool": o["tool"], "summary": o["summary"], "ok": o["ok"]}
                            for o in observations],
           "trace": trace,
           "workflow": workflow.name, "intent": detect_intent(query),
           "plan": plan.to_dict()}


def run_auto(query: str, registry: ToolRegistry | None = None, spec=None,
             context: dict | None = None, allow_mutating: bool = False,
             max_steps: int = MAX_STEPS) -> Iterator[dict]:
    """Route the query to a workflow automatically and run it."""
    yield from run_workflow(route_workflow(query), query, registry=registry, spec=spec,
                            context=context, allow_mutating=allow_mutating,
                            max_steps=max_steps)


def run_generic(query: str, registry: ToolRegistry | None = None, spec=None,
                context: dict | None = None, allow_mutating: bool = False,
                max_steps: int = 6) -> Iterator[dict]:
    """Free-form agent loop (model or deterministic planner)."""
    reg = registry or REGISTRY
    executor = AgentExecutor(registry=reg, max_steps=max_steps,
                              allow_mutating=allow_mutating)
    yield from executor.run(query, plan=plan_task(query, spec=spec, registry=reg,
                                                  max_steps=max_steps),
                            spec=spec, context=context)
