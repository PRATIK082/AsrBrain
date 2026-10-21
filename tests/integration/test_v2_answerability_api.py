"""Integration tests for the evidence-first answerability contract (Phase 5).

The endpoint must return a **real** status computed from the stored evidence —
never a placeholder and never a fabricated "VERIFIED".
"""
from fastapi.testclient import TestClient
from apps.api.main import app
import src.workflows.stages as stages


def _mock_llm(draft: str):
    """Patch both generation paths so no model is contacted."""
    original_generate = stages._generate
    original_stream = stages._stream_tokens
    stages._generate = lambda q, e, comp, spec=None: {"draft": draft, "llm": "mock"}
    stages._stream_tokens = lambda prompt, spec=None: iter(())

    def restore() -> None:
        stages._generate = original_generate
        stages._stream_tokens = original_stream

    return restore


def test_answerability_unknown_conversation_is_404():
    c = TestClient(app)
    r = c.get("/api/v2/answerability/conv-does-not-exist")
    assert r.status_code == 404


def test_answerability_index_out_of_range_is_404():
    c = TestClient(app)
    cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
    r = c.get(f"/api/v2/answerability/{cid}/99")
    assert r.status_code == 404


def test_chat_stores_a_computed_answerability():
    c = TestClient(app)
    restore = _mock_llm("SOME/IP is the AUTOSAR service-oriented middleware [E1].")
    try:
        cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
        r = c.post("/api/chat", json={
            "conversation_id": cid,
            "message": "What is the purpose of SOME/IP?",
            "skip_clarify": True,
        })
        assert r.status_code == 200
        body = r.json()
        assert "answerability" in body
        status = body["answerability"]["status"]
        assert status in {"VERIFIED", "EVIDENCE_SUPPORTED", "NEEDS_ENGINEER_REVIEW",
                          "INSUFFICIENT_EVIDENCE"}
        assert body["answerability"]["reason"]
    finally:
        restore()


def test_answerability_endpoint_returns_the_same_status():
    c = TestClient(app)
    restore = _mock_llm("SOME/IP is the AUTOSAR service-oriented middleware [E1].")
    try:
        cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
        posted = c.post("/api/chat", json={
            "conversation_id": cid,
            "message": "What is the purpose of SOME/IP?",
            "skip_clarify": True,
        }).json()
        stored = c.get(f"/api/v2/answerability/{cid}/0")
        assert stored.status_code == 200
        data = stored.json()
        assert data["status"] == posted["answerability"]["status"]
        assert data["reason"]
        assert isinstance(data["missing"], list)
        assert isinstance(data["checked"], list)
    finally:
        restore()


def test_answerability_is_never_a_percentage():
    c = TestClient(app)
    restore = _mock_llm("SOME/IP is the AUTOSAR service-oriented middleware [E1].")
    try:
        cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
        c.post("/api/chat", json={
            "conversation_id": cid,
            "message": "What is the purpose of SOME/IP?",
            "skip_clarify": True,
        })
        data = c.get(f"/api/v2/answerability/{cid}/0").json()
        # A numeric confidence is a heuristic, never the user-facing contract.
        assert not isinstance(data["status"], (int, float))
        assert "%" not in str(data["status"])
    finally:
        restore()


def test_conversation_answerability_lists_every_turn():
    c = TestClient(app)
    restore = _mock_llm("SOME/IP is the AUTOSAR service-oriented middleware [E1].")
    try:
        cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
        c.post("/api/chat", json={
            "conversation_id": cid, "message": "What is SOME/IP?",
            "skip_clarify": True,
        })
        data = c.get(f"/api/v2/answerability/{cid}").json()
        assert data["count"] >= 1
        assert data["turns"][0]["status"]
    finally:
        restore()


def test_audit_trail_records_the_answer():
    c = TestClient(app)
    restore = _mock_llm("SOME/IP is the AUTOSAR service-oriented middleware [E1].")
    try:
        cid = c.post("/api/conversations", json={"title": "gate"}).json()["id"]
        c.post("/api/chat", json={
            "conversation_id": cid, "message": "What is SOME/IP?",
            "skip_clarify": True,
        })
        data = c.get(f"/api/v2/audit/{cid}").json()
        assert data["count"] >= 1
        audit = data["audits"][0]
        assert audit["question"]
        assert audit["answerability_status"]
        assert audit["conversation_id"] == cid
    finally:
        restore()


def test_v1_routes_still_work():
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/assistant/capabilities").status_code == 200
    assert c.get("/api/v2/modules").status_code == 200
