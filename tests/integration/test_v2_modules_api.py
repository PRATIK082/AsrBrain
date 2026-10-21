"""Contract tests for the v2 engineering-workspace endpoints.

The v2 surface is additive: the v1 routes keep their path, request shape and
response keys. These tests pin the new contract and, importantly, assert that
the answerability endpoint refuses to invent a status.
"""
from fastapi.testclient import TestClient
from apps.api.main import app


def test_v2_module_catalogue_shape():
    c = TestClient(app)
    r = c.get("/api/v2/modules")
    assert r.status_code == 200
    d = r.json()
    assert d["workspace"]["title"]
    assert d["workspace"]["project"]
    modules = d["modules"]
    assert len(modules) >= 9
    ids = [m["id"] for m in modules]
    assert len(ids) == len(set(ids)), "module ids must be unique"
    for m in modules:
        assert m["id"] and m["title"] and m["href"]
        assert m["status"] in {"available", "partial", "planned"}
        assert m["description"]
        assert m["capability"]
        assert m["phase"]


def test_v2_catalogue_never_overclaims():
    c = TestClient(app)
    modules = c.get("/api/v2/modules").json()["modules"]
    for m in modules:
        if m["status"] == "planned":
            # A planned module must say what is missing.
            assert m["missing"], f"planned module {m['id']} must state what is missing"
        else:
            # A shipped module must not claim a missing capability.
            assert m["capability"]


def test_v2_catalogue_contains_the_nine_product_modules():
    c = TestClient(app)
    ids = {m["id"] for m in c.get("/api/v2/modules").json()["modules"]}
    assert {
        "chat", "knowledge", "arxml", "graph", "requirements",
        "tests", "diffs", "diagrams", "evaluation",
    } <= ids


def test_v2_answerability_of_an_unknown_conversation_is_not_found():
    # Phase 1 shipped a 501 placeholder; Phase 5 implements the gate, so an
    # unknown conversation is now a 404. The endpoint must never answer with a
    # status it did not compute.
    c = TestClient(app)
    r = c.get("/api/v2/answerability/conv-missing/0")
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body
    assert "status" not in body


def test_v1_routes_are_untouched_by_v2():
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/assistant/capabilities").status_code == 200
    assert c.get("/api/assistant/prompts").status_code == 200
    assert c.get("/api/assistant/triage/categories").status_code == 200
