from src.workflows.suggest import suggest


def _ev(api="CanIf_Init", req="SWS_CANIF_00001"):
    return {"api_names": [api], "requirement_ids": [req]}


def test_grounded_followups():
    plan = {"modules": ["CanIf"], "releases": [], "intent": "api_lookup"}
    out = suggest(plan, [_ev()])
    assert 1 <= len(out) <= 4
    assert any("CanIf_Init" in s for s in out)


def test_empty_evidence_still_suggests():
    out = suggest({"modules": [], "releases": [], "intent": "unknown"}, [])
    assert 1 <= len(out) <= 4
