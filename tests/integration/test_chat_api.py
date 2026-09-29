"""Chat contract tests: CRUD + staged events (LLM mocked) + real /api/chat answer path."""
from fastapi.testclient import TestClient
from apps.api.main import app
import src.workflows.stages as stages


def test_conversation_crud():
    c = TestClient(app)
    cid = c.post("/api/conversations", json={"title": "t"}).json()["id"]
    assert c.get(f"/api/conversations/{cid}").status_code == 200
    assert c.patch(f"/api/conversations/{cid}", json={"title": "t2"}).json()["ok"] is True
    assert any(x["id"] == cid for x in c.get("/api/conversations").json())
    assert c.delete(f"/api/conversations/{cid}").json()["ok"] is True


def test_staged_event_sequence_mocked_llm():
    from src.indexing.hybrid import HybridIndex, load_chunks
    from src.retrieval.pipeline import RetrievalPipeline
    from src.config.settings import settings
    chunks = load_chunks(settings.canonical_db)
    idx = HybridIndex.load("data/indexes/hybrid")
    pipe = RetrievalPipeline(idx, chunks)
    orig = stages._generate
    stages._generate = lambda q, e, comp, spec=None: {"draft": "Mock [E1].", "llm": "mock"}
    try:
        evs = list(stages.run_staged(pipe, "What is SOME/IP?", None, {}, {"skip_clarify": True}))
    finally:
        stages._generate = orig
    kinds = [e["event"] for e in evs]
    assert "clarify" not in kinds
    assert kinds[0] == "status" and "evidence" in kinds and kinds[-1] == "complete"
    assert evs[-1]["answer"].startswith("Mock")


def test_api_chat_answers_directly_single_release_corpus():
    c = TestClient(app)
    r = c.post("/api/chat", json={"message": "What is the purpose of SOME/IP?", "skip_clarify": True})
    assert r.status_code == 200
    d = r.json()
    assert d["needs_clarification"] is False
    assert "Sources" in d["answer"]
