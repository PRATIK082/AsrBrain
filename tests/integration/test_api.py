from fastapi.testclient import TestClient
from apps.api.main import app
import src.workflows.router as router


def test_health():
    c = TestClient(app)
    assert c.get("/health").status_code == 200


def test_query_cited():
    c = TestClient(app)
    # The legacy /query path answers with a model by default, so the assertion
    # below depended on a live LLM. Stub the generator: the contract under
    # test is "the answer carries citations", not "the model worded it well".
    orig = router.generate
    router.generate = lambda q, e, comp, spec=None: {
        "draft": "SOME/IP is the AUTOSAR service-oriented middleware protocol [E1].",
        "llm": "mock",
    }
    try:
        r = c.post("/query", json={"query": "What is the purpose of SOME/IP?"})
    finally:
        router.generate = orig
    assert r.status_code == 200
    d = r.json()
    assert len(d["evidence"]) > 0
    assert "Sources" in d["answer"]
    assert d["plan"]["intent"] == "definition"
