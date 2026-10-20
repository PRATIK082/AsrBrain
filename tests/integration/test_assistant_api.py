"""Integration tests for the institutional-assistant API surface.

The assistant endpoints are read-only over the canonical store, so they are
deterministic. The chat test mocks the generator so no model is contacted.
"""
from fastapi.testclient import TestClient
from apps.api.main import app
import src.workflows.stages as stages


def test_assistant_capabilities():
    c = TestClient(app)
    r = c.get("/api/assistant/capabilities")
    assert r.status_code == 200
    d = r.json()
    assert d["assistant"]
    assert isinstance(d["ready"], bool)
    assert d["modes"] and d["surfaces"] and d["guarantees"]
    assert "corpus" in d


def test_assistant_overview():
    c = TestClient(app)
    r = c.get("/api/assistant/overview")
    assert r.status_code == 200
    d = r.json()
    assert "modules" in d and "concept_flow" in d and "entity_anchors" in d


def test_assistant_prompts_envelope():
    c = TestClient(app)
    r = c.get("/api/assistant/prompts")
    assert r.status_code == 200
    d = r.json()
    assert "groups" in d
    assert isinstance(d["groups"], list)
    assert d["groups"]
    for group in d["groups"]:
        assert group["group"]
        assert group["prompts"]


def test_assistant_triage_categories_envelope():
    c = TestClient(app)
    r = c.get("/api/assistant/triage/categories")
    assert r.status_code == 200
    d = r.json()
    assert "categories" in d
    ids = [cat["id"] for cat in d["categories"]]
    assert "signal_not_transmitted" in ids
    for cat in d["categories"]:
        assert cat["title"]
        assert cat["checks"]


def test_assistant_diagnose_requires_a_symptom():
    c = TestClient(app)
    r = c.post("/api/assistant/diagnose", json={"symptom": ""})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is False
    assert d["abstained"] is True


def test_assistant_diagnose_is_deterministic_without_a_provider():
    c = TestClient(app)
    r = c.post("/api/assistant/diagnose", json={
        "symptom": "A signal is configured but the frame is never transmitted on the bus",
        "module": "Com",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["category"]["id"]
    assert d["checks"]
    assert d["summary"]
    # Without a provider the answer must come from the deterministic path.
    assert d.get("llm", "") == ""
    labels = {e["label"] for e in d["evidence"]}
    for cause in d["likely_causes"]:
        assert cause["label"] in labels


def test_assistant_diagnose_persists_nothing_but_reports_evidence():
    c = TestClient(app)
    r = c.post("/api/assistant/diagnose", json={
        "symptom": "A periodic signal times out intermittently",
        "module": "Com",
    })
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    if d["evidence"]:
        first = d["evidence"][0]
        assert first["label"].startswith("E")
        assert first["source_pdf"]
        assert first["page"]


def test_chat_stores_evidence_meta_for_the_assistant_ui():
    c = TestClient(app)
    orig = stages._generate
    stages._generate = lambda q, e, comp, spec=None: {
        "draft": "Mock answer with a citation [E1].", "llm": "mock"}
    try:
        cid = c.post("/api/conversations", json={"title": "assistant ui"}).json()["id"]
        r = c.post("/api/chat", json={
            "conversation_id": cid,
            "message": "What is the purpose of SOME/IP?",
            "skip_clarify": True,
        })
        assert r.status_code == 200
        conv = c.get(f"/api/conversations/{cid}").json()
    finally:
        stages._generate = orig
    assistant_msgs = [m for m in conv["messages"] if m["role"] == "assistant"]
    assert assistant_msgs, "the assistant turn must be persisted"
    meta = assistant_msgs[-1].get("meta") or {}
    assert "evidence" in meta, "per-turn evidence must be stored for the source panel"
    assert meta["evidence"], "the cited passages must be stored"
    assert meta["evidence"][0]["source_pdf"]
