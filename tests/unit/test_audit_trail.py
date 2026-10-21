"""Unit tests for the answer audit trail (Phase 5)."""
from src.audit.trail import new_request_id, read_audits, record_answer
from src.registry.store import RegistryStore


def test_a_request_id_is_unique():
    assert new_request_id() != new_request_id()
    assert new_request_id().startswith("req-")


def test_recording_without_a_store_still_returns_the_record():
    record = record_answer(None, question="q", answer="a", status="EVIDENCE_SUPPORTED")
    assert record["question"] == "q"
    assert record["answerability_status"] == "EVIDENCE_SUPPORTED"


def test_an_audit_is_written_and_can_be_read_back(tmp_path):
    store = RegistryStore(str(tmp_path / "registry.db"))
    try:
        record = record_answer(
            store,
            question="What is SOME/IP?",
            answer="A middleware protocol [E1].",
            status="EVIDENCE_SUPPORTED",
            request_id="req-1",
            conversation_id="conv-1",
            message_id="msg-1",
            project_id="p1",
            scope={"releases": ["R24-11"]},
            citations=[{"label": "E1", "source_pdf": "x.pdf", "page": 3}],
            tool_calls=[{"tool": "validate_arxml", "status": "passed"}],
            model_provider="ollama",
            model_name="qwen3:14b",
            routing_reason="local only",
            latency_ms=1234,
        )
        assert record["id"]
        audits = read_audits(store, conversation_id="conv-1")
        assert len(audits) == 1
        stored = audits[0]
        assert stored["question"] == "What is SOME/IP?"
        assert stored["answerability_status"] == "EVIDENCE_SUPPORTED"
        assert stored["conversation_id"] == "conv-1"
        assert stored["citations"]
        assert stored["tool_calls"]
        assert stored["latency_ms"] == 1234
    finally:
        store.close()


def test_audits_of_other_conversations_are_not_returned(tmp_path):
    store = RegistryStore(str(tmp_path / "registry.db"))
    try:
        record_answer(store, question="q1", answer="a1", status="VERIFIED",
                      conversation_id="conv-1")
        record_answer(store, question="q2", answer="a2", status="VERIFIED",
                      conversation_id="conv-2")
        assert len(read_audits(store, conversation_id="conv-1")) == 1
        assert len(read_audits(store)) == 2
    finally:
        store.close()
