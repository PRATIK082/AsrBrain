"""The answer audit trail (Phase 5).

Every answer the product produces leaves a record: what was asked, what was
searched, which passages were cited, which tools ran, which model was used and
why, and how long it took. The record is what makes an answer auditable
after the fact — and what an auditor reads when they disagree with it.

The trail is append-only from the product's point of view: a record is never
rewritten, only superseded by a new one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

__all__ = ["new_request_id", "record_answer", "read_audits"]


def new_request_id() -> str:
    """A request id that ties the trail to one request."""
    return f"req-{uuid.uuid4().hex[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def record_answer(store, *, question: str, answer: str, status: str,
                  request_id: str = "", conversation_id: str = "",
                  message_id: str = "", project_id: str = "",
                  scope: dict | None = None, citations: list | None = None,
                  tool_calls: list | None = None, model_provider: str = "",
                  model_name: str = "", routing_reason: str = "",
                  latency_ms: int = 0) -> dict:
    """Write one answer audit into the registry.

    Returns the record that was written. A registry that is not configured is
    not an error: the trail is best-effort and the answer is still returned to
    the user.
    """
    record = {
        "id": f"audit-{uuid.uuid4().hex[:12]}",
        "request_id": request_id or new_request_id(),
        "conversation_id": conversation_id,
        "message_id": message_id,
        "question": question,
        "answer": answer,
        "answerability_status": status,
        "project_id": project_id,
        "scope": scope or {},
        "citations": list(citations or []),
        "tool_calls": list(tool_calls or []),
        "model_provider": model_provider,
        "model_name": model_name,
        "routing_reason": routing_reason,
        "latency_ms": int(latency_ms or 0),
        "created_at": _now(),
    }
    if store is None:
        return record
    payload = {k: v for k, v in record.items() if k not in ("id", "created_at")}
    store.record_answer_audit(audit_id=record["id"], **payload)
    return record


def read_audits(store, conversation_id: str = "", limit: int = 100) -> list[dict]:
    """Read the audit trail, newest first.

    The records are returned as plain dicts so they serialise straight into
    the API, whatever the registry hands back.
    """
    if store is None:
        return []
    audits = store.list_answer_audits(conversation_id)
    out: list[dict] = []
    for item in audits:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump())
        elif isinstance(item, dict):
            out.append(dict(item))
    return out[:limit]
