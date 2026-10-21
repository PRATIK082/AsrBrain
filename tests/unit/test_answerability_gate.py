"""Unit tests for the answerability gate (ADR-0001).

The gate must be decided by code, never by the model and never by a numeric
confidence. These tests pin the decision order.
"""
from src.answerability import STATUSES, evaluate_answerability


def _evidence(count: int = 2) -> list[dict]:
    return [{"label": f"E{i + 1}", "source_pdf": "x.pdf", "page": i + 1}
            for i in range(count)]


def test_the_four_statuses_are_the_contract():
    assert STATUSES == ("VERIFIED", "EVIDENCE_SUPPORTED",
                         "NEEDS_ENGINEER_REVIEW", "INSUFFICIENT_EVIDENCE")


def test_no_evidence_is_insufficient_evidence():
    result = evaluate_answerability(evidence=[], verification={})
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["reason"]
    assert result["missing"]


def test_nothing_cited_is_insufficient_evidence():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 0.0, "claim_support_rate": 1.0})
    assert result["status"] == "INSUFFICIENT_EVIDENCE"


def test_partial_support_needs_engineer_review():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 0.5})
    assert result["status"] == "NEEDS_ENGINEER_REVIEW"


def test_uncited_claims_need_engineer_review():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0},
        answer="The middleware is SOME/IP [E1]. It also runs on a plain bus.")
    assert result["status"] == "NEEDS_ENGINEER_REVIEW"


def test_cited_without_a_tool_is_evidence_supported():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0})
    assert result["status"] == "EVIDENCE_SUPPORTED"
    assert result["checked"]


def test_a_confirming_tool_makes_it_verified():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0},
        tool_results=[{"tool": "validate_arxml", "status": "passed"}])
    assert result["status"] == "VERIFIED"


def test_a_conflicting_tool_needs_engineer_review():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0},
        tool_results=[{"tool": "diff_arxml_versions", "status": "conflict"}])
    assert result["status"] == "NEEDS_ENGINEER_REVIEW"
    assert result["conflicts"]


def test_a_failing_tool_never_verifies():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0},
        tool_results=[{"tool": "validate_arxml", "status": "failed"}])
    assert result["status"] != "VERIFIED"


def test_the_scope_is_echoed_back():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0},
        scope={"releases": ["R24-11"], "modules": ["Com"]})
    assert result["scope"]["releases"] == ["R24-11"]


def test_the_status_is_never_a_percentage():
    result = evaluate_answerability(
        evidence=_evidence(),
        verification={"citation_coverage": 1.0, "claim_support_rate": 1.0})
    assert isinstance(result["status"], str)
    assert result["status"] in STATUSES
    assert "%" not in result["status"]
