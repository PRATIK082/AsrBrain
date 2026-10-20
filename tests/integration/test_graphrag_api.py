"""Integration tests for the GraphRAG, tool-catalogue and agent endpoints."""
from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.api.main import app
from src.graphrag.runtime import get_store, reset_store


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def graph(monkeypatch, tmp_path):
    """Point the process-wide graph store at a temporary file and seed it."""
    monkeypatch.setenv("GRAPH_DB_PATH", str(tmp_path / "graph.db"))
    reset_store()
    store = get_store()
    store.upsert_node("requirement", "SWS_CanIf_00123")
    store.upsert_node("api", "CanIf_Init")
    store.upsert_node("module", "CanIf")
    store.upsert_node("function", "CanIf_Main")
    store.upsert_edge("api:CanIf_Init", "requirement:SWS_CanIf_00123", "satisfies")
    store.upsert_edge("function:CanIf_Main", "api:CanIf_Init", "calls")
    store.degree()
    store.commit()
    yield store
    reset_store()


# ------------------------------------------------------------------ tool catalogue
def test_tools_catalogue_lists_every_tool(client):
    r = client.get("/api/tools")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] >= 20
    assert d["count"] == len(d["tools"]) == len(d["names"])
    for t in d["tools"]:
        assert t["name"] and t["description"]
        assert t["parameters"]["type"] == "object"
    assert "mindmap.build" in d["names"]


def test_invoke_tool_endpoint_returns_data(client, graph):
    r = client.post("/api/tools/graph.stats", json={"args": {}})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["tool"] == "graph.stats"
    assert d["data"]["nodes"] >= 3


def test_invoke_unknown_tool_returns_404(client, graph):
    r = client.post("/api/tools/does.not.exist", json={"args": {}})
    assert r.status_code == 404


def test_mutating_tool_requires_explicit_opt_in(client, graph):
    r = client.post("/api/tools/graph.build", json={"args": {}})
    assert r.status_code == 403
    r2 = client.post("/api/tools/graph.build",
                     json={"args": {"canonical_db": "nope.db"}, "allow_mutating": True})
    assert r2.status_code == 200
    assert r2.json()["ok"] is False          # the tool failed, the API did not


# ------------------------------------------------------------------------- mindmap
def test_mindmap_endpoint_renders_mermaid(client, graph):
    r = client.post("/api/mindmap", json={"topic": "CanIf", "source": "outline",
                                           "outline": [{"label": "Init"}]})
    assert r.status_code == 200
    d = r.json()
    assert d["mermaid"].startswith("mindmap")
    assert d["topic"] == "CanIf"


def test_mindmap_endpoint_requires_topic(client, graph):
    r = client.post("/api/mindmap", json={"topic": "   "})
    assert r.status_code == 400


# -------------------------------------------------------------------------- graph
def test_graph_stats_endpoint(client, graph):
    r = client.get("/api/graph/stats")
    assert r.status_code == 200
    d = r.json()
    assert d["nodes"] >= 3
    assert d["edges"] >= 2


def test_graph_query_endpoint_returns_nodes(client, graph):
    r = client.post("/api/graph/query", json={"query": "CanIf_Init", "mode": "local",
                                               "depth": 2, "limit": 10})
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "local"
    assert d["node_count"] >= 1
    assert d["stats"]["nodes"] >= 3


def test_graph_query_global_mode_returns_communities(client, graph):
    r = client.post("/api/graph/query", json={"query": "CanIf", "mode": "global"})
    assert r.status_code == 200
    assert "communities" in r.json()


def test_graph_node_endpoint_returns_neighbourhood(client, graph):
    r = client.get("/api/graph/node/api:CanIf_Init", params={"depth": 1})
    assert r.status_code == 200
    d = r.json()
    assert d["node"]["label"] == "CanIf_Init"
    assert d["node_count"] >= 1


def test_graph_node_unknown_returns_404(client, graph):
    r = client.get("/api/graph/node/requirement:does_not_exist")
    assert r.status_code == 404


def test_graph_build_endpoint_creates_nodes(client, graph, tmp_path):
    canon = tmp_path / "canonical.db"
    conn = sqlite3.connect(canon)
    conn.execute(
        "CREATE TABLE chunks (chunk_id TEXT, document_id TEXT, source_pdf TEXT, "
        "page_start INTEGER, module TEXT, autosar_release TEXT, requirement_ids TEXT, "
        "api_names TEXT, ecu_parameters TEXT, text TEXT, normalized_text TEXT)")
    conn.execute(
        "INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("c1", "d1", "spec.pdf", 1, "CanIf", "R21-11",
         json.dumps(["SWS_CanIf_00123"]), json.dumps(["CanIf_Init"]), json.dumps([]),
         "CanIf_Init shall initialise the CAN interface.", ""))
    conn.commit()
    conn.close()

    r = client.post("/api/graph/build", json={"canonical_db": str(canon), "clear": True})
    assert r.status_code == 200
    d = r.json()
    assert d["built"] is True
    assert d["nodes"] >= 2

    stats = client.get("/api/graph/stats").json()
    assert stats["nodes"] >= 2


# ------------------------------------------------------------------------- agent
def test_agent_workflows_endpoint(client, graph):
    r = client.get("/api/agent/workflows")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 4
    names = {w["name"] for w in d["workflows"]}
    assert names == {"arxml_requirement_trace", "code_requirement_trace",
                     "impact_analysis", "deep_explanation"}
    for w in d["workflows"]:
        assert w["steps"]
        assert w["tools"]


def test_agent_run_endpoint_returns_answer_and_trace(client, graph):
    r = client.post("/api/agent/run", json={
        "query": "what is the impact of changing CanIf_Init",
        "provider": "none",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["workflow"] == "impact_analysis"
    assert d["intent"]
    assert d["answer"]
    assert d["routed_workflow"] == "impact_analysis"
    assert isinstance(d["observations"], list)


def test_agent_run_explicit_workflow(client, graph):
    r = client.post("/api/agent/run", json={
        "query": "SWS_CanIf_00123",
        "workflow": "deep_explanation",
        "provider": "none",
    })
    assert r.status_code == 200
    assert r.json()["workflow"] == "deep_explanation"


def test_agent_run_freeform_mode(client, graph):
    r = client.post("/api/agent/run", json={
        "query": "search the graph for CanIf",
        "mode": "freeform",
        "provider": "none",
    })
    assert r.status_code == 200
    assert r.json()["answer"]


def test_agent_run_requires_query(client, graph):
    r = client.post("/api/agent/run", json={"query": "  ", "provider": "none"})
    assert r.status_code == 400


def test_agent_run_unknown_workflow_is_rejected(client, graph):
    r = client.post("/api/agent/run", json={"query": "x", "workflow": "nope",
                                             "provider": "none"})
    assert r.status_code == 400


def test_agent_stream_endpoint_emits_sse(client, graph):
    r = client.post("/api/agent/stream", json={
        "query": "impact of CanIf_Init", "provider": "none"})
    assert r.status_code == 200
    payloads = []
    for line in r.text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    assert payloads
    assert payloads[0]["event"] == "workflow"
    assert payloads[-1]["event"] == "complete"
