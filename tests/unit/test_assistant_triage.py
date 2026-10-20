"""Unit tests for the deterministic symptom triage.

The pipeline is stubbed so the tests never touch the model or the network:
triage must be reproducible from evidence alone.
"""
from src.assistant import triage


def _chunk(chunk_id: str, text: str, page: int = 42) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_pdf": "pdf\\AUTOSAR_TPS_SystemTemplate.pdf",
        "page_start": page,
        "page_end": page,
        "section_number": "4.1.2",
        "section_title": "Signal transmission",
        "autosar_release": "R22-11",
        "platform": "Foundation",
        "module": "Com",
        "requirement_ids": ["SWS_Com_00123"],
        "normalized_text": text,
        "text": text,
        "compressed": text[:200],
        "rerank_score": 0.8,
    }


class _StubPipe:
    """Minimal stand-in for RetrievalPipeline."""

    def __init__(self, evidence: list[dict]):
        self.evidence = evidence

    def retrieve(self, query: str, top_k_final: int = 8) -> dict:
        return {
            "plan": {
                "intent": "troubleshooting",
                "releases": ["R22-11"],
                "modules": ["Com"],
                "platforms": ["Foundation"],
                "release_mode": "any",
            },
            "rewrites": [],
            "evidence": self.evidence[:top_k_final],
            "per_release": {},
            "retrieval_score": 0.7,
        }


def test_classify_picks_the_matching_symptom_family():
    signal = triage.classify("the frame is never transmitted on the bus")
    assert signal["id"] == "signal_not_transmitted"
    assert signal["confidence"] > 0.2
    assert signal["checks"]

    timeout = triage.classify("a periodic signal times out intermittently")
    assert timeout["id"] == "timeout"

    port = triage.classify("the port connection is not established")
    assert port["id"] == "port_connection"

    init = triage.classify("initialisation of the module never completes")
    assert init["id"] == "initialisation"


def test_classify_falls_back_to_general_without_a_match():
    unknown = triage.classify("qwerty zxcvbn")
    assert unknown["id"] == "general"
    assert unknown["confidence"] <= 0.2


def test_triage_categories_are_public_and_unique():
    cats = triage.triage_categories()
    ids = [c["id"] for c in cats]
    assert len(ids) == len(set(ids))
    for cat in cats:
        assert cat["title"]
        assert cat["checks"]
        if cat["id"] != "general":
            assert cat["keywords"]


def test_diagnose_requires_a_symptom():
    out = triage.diagnose("   ")
    assert out["ok"] is False
    assert out["abstained"] is True
    assert out["likely_causes"] == []
    assert out["evidence"] == []


def test_diagnose_abstains_when_the_corpus_has_no_evidence():
    out = triage.diagnose("frame never transmitted", pipe=_StubPipe([]))
    assert out["ok"] is True
    assert out["abstained"] is True
    assert out["likely_causes"] == []
    assert out["confidence"] == 0.0
    assert "nothing is asserted" in out["summary"].lower()


def test_diagnose_returns_cited_causes_checks_and_fixes():
    evidence = [
        _chunk("c1", "The signal is not transmitted if the transmission mode is not set "
                      "to periodic. The configuration shall enable the signal group.", 100),
        _chunk("c2", "A timeout occurs when the deadline monitoring is enabled and the "
                      "signal is not received within the configured timeout.", 110),
    ]
    out = triage.diagnose(
        "the frame is never transmitted on the bus",
        module="Com",
        pipe=_StubPipe(evidence),
    )
    assert out["ok"] is True
    assert out["abstained"] is False
    assert out["category"]["id"] == "signal_not_transmitted"

    # Every cause is anchored to a label that exists in the evidence list.
    labels = {e["label"] for e in out["evidence"]}
    assert out["likely_causes"]
    for cause in out["likely_causes"]:
        assert cause["label"] in labels
        assert cause["source_pdf"]
        assert cause["page"]
        assert cause["cause"]

    assert out["checks"], "the triage must propose checks to run"
    for check in out["checks"]:
        assert check["question"] and check["how"]

    summary = out["summary"]
    assert "### Checks to run" in summary
    assert "### Most likely causes" in summary
    assert out["followups"]
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["level"] in {"Low", "Medium", "High"}


def test_diagnose_is_deterministic():
    evidence = [_chunk("c1", "The frame is not transmitted when the ipdu group is not mapped.")]
    first = triage.diagnose("frame not transmitted", pipe=_StubPipe(evidence))
    second = triage.diagnose("frame not transmitted", pipe=_StubPipe(evidence))
    assert first["summary"] == second["summary"]
    assert first["likely_causes"] == second["likely_causes"]
    assert first["confidence"] == second["confidence"]


def test_diagnose_uses_code_identifiers_in_the_query():
    seen = {}

    class _RecordingPipe(_StubPipe):
        def retrieve(self, query: str, top_k_final: int = 8) -> dict:
            seen["query"] = query
            return super().retrieve(query, top_k_final)

    evidence = [_chunk("c1", "Com_SignalTransmit triggers the transmission of the ipdu.")]
    out = triage.diagnose("signal not sent", code="Com_SignalTransmit();",
                           pipe=_RecordingPipe(evidence))
    assert "Com_SignalTransmit" in seen["query"]
    assert out["ok"] is True
