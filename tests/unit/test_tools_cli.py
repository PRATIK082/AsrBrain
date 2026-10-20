"""Unit tests for the tool / agent CLI (``python -m src.tools.cli``)."""
from __future__ import annotations

import json

from src.tools import cli


def _capsys(capsys):
    return capsys.readouterr().out


def test_cli_list_prints_every_tool(capsys):
    assert cli.main(["list"]) == 0
    out = _capsys(capsys)
    assert "graph.search" in out
    assert "mindmap.build" in out
    assert "tools" in out


def test_cli_workflows_lists_the_four_workflows(capsys):
    assert cli.main(["workflows"]) == 0
    out = _capsys(capsys)
    for name in ("arxml_requirement_trace", "code_requirement_trace",
                 "impact_analysis", "deep_explanation"):
        assert name in out


def test_cli_call_parses_json_arguments(capsys):
    assert cli.main(["call", "graph.stats"]) == 0
    payload = json.loads(_capsys(capsys))
    assert payload["tool"] == "graph.stats"
    assert payload["ok"] is True
    assert "nodes" in payload["data"]


def test_cli_call_reports_unknown_tool(capsys):
    assert cli.main(["call", "does.not.exist"]) == 1
    payload = json.loads(_capsys(capsys))
    assert payload["ok"] is False
    assert "unknown tool" in payload["error"]


def test_cli_mindmap_renders_mermaid(capsys):
    assert cli.main(["mindmap", "CanIf", "--source", "outline",
                      "--outline", json.dumps([{"label": "A"}])]) == 0
    out = _capsys(capsys)
    assert out.lstrip().startswith("mindmap")
    assert "CanIf" in out


def test_cli_agent_runs_a_workflow(capsys):
    assert cli.main(["agent", "impact of CanIf", "--workflow", "impact_analysis",
                     "--provider", "none"]) == 0
    out = _capsys(capsys)
    assert "Impact analysis" in out
