"""The evidence-first answer contract (ADR-0001)."""

from .gate import AnswerabilityResult, STATUSES, evaluate_answerability

__all__ = ["AnswerabilityResult", "STATUSES", "evaluate_answerability"]
