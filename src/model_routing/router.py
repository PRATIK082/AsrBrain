"""Policy-controlled local/cloud model router (Phase 2 §14)."""
from __future__ import annotations

from src.security.context import SecurityContext
from src.security.policy import ContentRiskAssessment, routing_decision

TASKS = ["chat_answer", "deep_explanation", "document_summary", "arxml_explanation",
         "arxml_to_code", "code_review", "diagram_analysis", "table_interpretation",
         "diff_summary", "entity_extraction", "answer_validation", "citation_validation"]

LOCAL_ONLY_TASKS = {"arxml_explanation", "arxml_to_code", "code_review"}


def route(task: str, ctx: SecurityContext, assessment: ContentRiskAssessment) -> dict:
    if task in LOCAL_ONLY_TASKS and ctx.cloud_policy == "local_only":
        return {"route": "local", "reason": f"task {task} is local-only under current policy",
                "task": task, "redacted": False}
    return routing_decision(ctx, assessment, task)
