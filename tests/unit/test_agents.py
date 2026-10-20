"""Unit tests for the agent loop: planner, executor, workflows and runner."""
from __future__ import annotations

import pytest

from src.agents.executor import AgentExecutor, summarize_tool_result
from src.agents.planner import (Plan, PlanStep, deterministic_plan, detect_intent,
                                extract_identifiers, plan_task)
from src.agents.runner import run_auto, run_generic, run_workflow
from src.agents.workflows import (WORKFLOWS, base_context, get_workflow, list_workflows,
                                  route_workflow)
from src.tools.base import ToolRegistry, ToolSpec
from src.tools.registry import build_registry


def _echo_registry():
    reg = ToolRegistry()
    reg.register(ToolSpec(name="demo.echo", description="echo", parameters={},
                          fn=lambda msg="": {"msg": msg}))
    reg.register(ToolSpec(name="demo.boom", description="fail", parameters={},
                          fn=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    reg.register(ToolSpec(name="demo.write", description="mutating", parameters={},
                          fn=lambda: {"written": True}, mutating=True))
    return reg


# ----------------------------------------------------------------- intent / ids
@pytest.mark.parametrize("query,expected", [
    ("trace SWS_Com_00123 in the arxml", "arxml_trace"),
    ("which C function implements Rte_Read_Speed", "code_trace"),
    ("what is the impact of changing CanIf_Init", "impact"),
    ("show me a mindmap of the CanIf module", "mindmap"),
    ("which test case covers SWS_Com_00123", "trace"),
])
def test_detect_intent(query, expected):
    assert detect_intent(query) == expected


def test_extract_identifiers():
    ids = extract_identifiers("Trace SWS_Com_00123 and CanIf_Init and TEST_CanIf_Transmit")
    assert "SWS_Com_00123" in ids["requirements"]
    assert "TEST_CanIf_Transmit" in ids["tests"]
    assert "CanIf_Init" in ids["symbols"]


# --------------------------------------------------------------------- planner
def test_deterministic_plan_only_uses_known_tools():
    reg = build_registry()
    plan = deterministic_plan("trace SWS_Com_00123 in arxml and c code", registry=reg)
    assert plan.mode == "deterministic"
    assert plan.steps
    assert all(reg.get(s.tool) is not None for s in plan.steps)


def test_deterministic_plan_filters_unknown_tools():
    reg = _echo_registry()
    plan = deterministic_plan("trace SWS_Com_00123 in arxml and c code", registry=reg)
    assert plan.steps == []


def test_deterministic_plan_respects_max_steps():
    reg = build_registry()
    plan = deterministic_plan("arxml trace requirement test case graph mindmap c code",
                              registry=reg, max_steps=2)
    assert len(plan.steps) <= 2


def test_plan_task_without_spec_falls_back_to_deterministic():
    plan = plan_task("graph search", spec=None, registry=build_registry())
    assert plan.mode == "deterministic"
    assert plan.steps


def test_plan_to_dict_shape():
    plan = Plan(steps=[PlanStep("a.b", {"x": 1}, "why")], rationale="r", mode="deterministic")
    d = plan.to_dict()
    assert d["step_count"] == 1
    assert d["steps"][0]["tool"] == "a.b"
    assert d["steps"][0]["args"] == {"x": 1}


# -------------------------------------------------------------------- executor
def test_executor_runs_the_plan_and_completes():
    reg = _echo_registry()
    plan = Plan(steps=[PlanStep("demo.echo", {"msg": "hi"}, "say hi")])
    events = list(AgentExecutor(registry=reg).run("hello", plan=plan))
    assert events[0]["event"] == "plan"
    assert any(e["event"] == "tool_call" for e in events)
    assert any(e["event"] == "tool_result" for e in events)
    final = events[-1]
    assert final["event"] == "complete"
    assert final["citations"]
    assert "demo.echo" in final["answer"]


def test_executor_skips_mutating_tools_unless_allowed():
    reg = _echo_registry()
    plan = Plan(steps=[PlanStep("demo.write", {}, "write")])
    events = list(AgentExecutor(registry=reg).run("go", plan=plan))
    assert any(e["event"] == "tool_skipped" for e in events)

    allowed = list(AgentExecutor(registry=reg, allow_mutating=True).run("go", plan=plan))
    assert not any(e["event"] == "tool_skipped" for e in allowed)


def test_executor_survives_a_failing_tool():
    reg = _echo_registry()
    plan = Plan(steps=[PlanStep("demo.boom", {}, "fail")])
    events = list(AgentExecutor(registry=reg).run("go", plan=plan))
    result = [e for e in events if e["event"] == "tool_result"][0]
    assert result["ok"] is False
    assert events[-1]["event"] == "complete"


def test_executor_resolves_placeholders_from_context():
    reg = _echo_registry()
    plan = Plan(steps=[PlanStep("demo.echo", {"msg": "{topic}"}, "echo topic")])
    events = list(AgentExecutor(registry=reg).run("go", plan=plan,
                                                  context={"topic": "CanIf"}))
    call = [e for e in events if e["event"] == "tool_call"][0]
    assert call["args"]["msg"] == "CanIf"


def test_executor_enforces_max_steps():
    reg = _echo_registry()
    plan = Plan(steps=[PlanStep("demo.echo", {}, "x") for _ in range(10)])
    events = list(AgentExecutor(registry=reg, max_steps=3).run("go", plan=plan))
    calls = [e for e in events if e["event"] == "tool_call"]
    assert len(calls) == 3


def test_executor_without_tools_reports_missing_evidence():
    reg = _echo_registry()
    events = list(AgentExecutor(registry=reg).run("go", plan=Plan(steps=[])))
    assert "No tool produced evidence" in events[-1]["answer"]


def test_summarize_tool_result_handles_errors():
    from src.tools.base import ToolResult
    res = ToolResult(tool="x", ok=False, error="bad")
    assert summarize_tool_result("x", res).startswith("ERROR")


# ------------------------------------------------------------------- workflows
def test_workflow_catalogue_is_complete():
    names = {w["name"] for w in list_workflows()}
    assert names == {"arxml_requirement_trace", "code_requirement_trace",
                     "impact_analysis", "deep_explanation"}
    for w in list_workflows():
        assert w["title"] and w["description"] and w["intent"]
        assert w["steps"]


def test_get_workflow_returns_none_for_unknown():
    assert get_workflow("nope") is None
    assert get_workflow("impact_analysis") is not None


def test_route_workflow_is_deterministic():
    assert route_workflow("trace SWS_Com_00123 in arxml") == "arxml_requirement_trace"
    assert route_workflow("what breaks if CanIf_Init changes") == "impact_analysis"
    assert route_workflow("show a mindmap of CanIf") == "deep_explanation"


def test_base_context_extracts_identifiers():
    ctx = base_context("Trace SWS_CanIf_00123 in CanIf code")
    assert ctx["requirement"] == "SWS_CanIf_00123"
    assert ctx["module"] == "CanIf"
    assert ctx["query"].startswith("Trace")


def test_base_context_resolves_a_graph_node_identifier():
    """The node placeholder must never carry the whole question."""
    ctx = base_context("which tests cover the CanIf initialization requirement")
    assert ctx["node"] == "CanIf"
    assert ctx["node"] != ctx["query"]

    req = base_context("what breaks if SWS_CanIf_00123 changes")
    assert req["node"] == "SWS_CanIf_00123"


def test_impact_workflow_expands_a_real_node():
    reg = build_registry()
    events = list(run_workflow("impact_analysis",
                               "impact of the CanIf module", registry=reg))
    call = [e for e in events if e["event"] == "tool_call" and e["tool"] == "graph.neighbors"]
    assert call, "graph.neighbors was never called"
    assert call[0]["args"]["node"] == "CanIf"


def test_workflow_plan_uses_only_registered_tools():
    reg = build_registry()
    for wf in WORKFLOWS.values():
        plan = wf.plan(base_context("SWS_CanIf_00123"))
        for step in plan.steps:
            assert reg.get(step.tool) is not None, f"{wf.name}:{step.tool}"


# --------------------------------------------------------------------- runner
def test_run_workflow_emits_events_and_a_report():
    reg = build_registry()
    events = list(run_workflow("impact_analysis", "impact of CanIf_Init", registry=reg))
    assert events[0]["event"] == "workflow"
    assert events[-1]["event"] == "complete"
    assert events[-1]["workflow"] == "impact_analysis"
    assert "Impact analysis" in events[-1]["answer"]
    assert "Gaps or next steps" in events[-1]["answer"]


def test_run_workflow_unknown_name_is_an_error_event():
    events = list(run_workflow("nope", "x", registry=build_registry()))
    assert events[0]["event"] == "error"


def test_run_auto_routes_and_runs():
    events = list(run_auto("trace SWS_CanIf_00123 in arxml", registry=build_registry()))
    assert events[-1]["event"] == "complete"
    assert events[-1]["workflow"] in {w.name for w in WORKFLOWS.values()}


def test_run_generic_produces_an_answer():
    events = list(run_generic("graph search for CanIf", registry=build_registry()))
    assert events[-1]["event"] == "complete"
    assert events[-1]["answer"]


def test_all_workflows_run_end_to_end():
    reg = build_registry()
    for name in WORKFLOWS:
        events = list(run_workflow(name, "SWS_CanIf_00123 CanIf", registry=reg))
        assert events[-1]["event"] == "complete", name
        assert events[-1]["answer"].strip(), name
