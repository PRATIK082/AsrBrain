from src.generation.verification import verify, confidence_score


def _ev(cid="c1", rel="4.4.0", plat="Classic"):
    return {"chunk_id": cid, "source_pdf": "SWS_CanIf_4.4.0.pdf", "page_start": 1, "page_end": 1,
            "autosar_release": rel, "platform": plat, "normalized_text": "x", "compressed": "x",
            "requirement_ids": []}


def test_uncited_claim_unsupported():
    v = verify("CanIf does things.", [_ev()], {})
    assert v["claim_support_rate"] == 0.0


def test_cited_claim_supported():
    v = verify("CanIf does things [E1].", [_ev()], {})
    assert v["claim_support_rate"] == 1.0


def test_empty_evidence_abstains():
    v = verify("Nothing [E1].", [], {})
    c = confidence_score(0.0, [], v, {})
    assert c["should_abstain"] is True
