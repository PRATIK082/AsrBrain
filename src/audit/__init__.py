"""The answer audit trail."""

from .trail import new_request_id, read_audits, record_answer

__all__ = ["new_request_id", "read_audits", "record_answer"]
