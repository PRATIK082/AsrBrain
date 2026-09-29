from fastapi.testclient import TestClient
from apps.api.main import app


def test_health():
    c = TestClient(app)
    assert c.get("/health").status_code == 200


def test_query_cited():
    c = TestClient(app)
    r = c.post("/query", json={"query": "What is the purpose of SOME/IP?"})
    assert r.status_code == 200
    d = r.json()
    assert len(d["evidence"]) > 0
    assert "Sources" in d["answer"]
    assert d["plan"]["intent"] == "definition"
