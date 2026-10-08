"""Data classification + cloud/local policy engine (Phase 2 §4). Default-deny cloud for sensitive data."""
from __future__ import annotations

import re
from pydantic import BaseModel, Field

from src.security.context import SecurityContext

VIN_RE = re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")
PRIVATE_IP_RE = re.compile(r"\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b")
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
API_KEY_RE = re.compile(r"(?i)\b(api[_-]?key|secret|passwd|password)\s*[:=]\s*\S+")
ARXML_TAG_RE = re.compile(r"<\s*(?:\w+:)?(?:APPLICATION-SW-COMPONENT-TYPE|COMPOSITION-SW-COMPONENT-TYPE|ECUC-MODULE-CONFIGURATION-VALUES|R-PORT-PROTOTYPE|P-PORT-PROTOTYPE)")
C_SOURCE_RE = re.compile(r"#include\s*[<\"].*\.h[>\"]|Rte_(Read|Write|Call|Mode)|FUNC\s*\(")
ECU_HINT_RE = re.compile(r"(?i)\b(ecu|canif|can_tp|os_config|memmap|rte)\b")


class ContentRiskAssessment(BaseModel):
    classification: str = "internal"
    findings: list[str] = Field(default_factory=list)
    pii_detected: bool = False
    proprietary_code_detected: bool = False
    arxml_detected: bool = False
    credential_detected: bool = False
    cloud_eligible: bool = False
    redaction_required: bool = False
    policy_reason: str = ""


def classify_content(text: str = "", filename: str = "", declared: str = "") -> ContentRiskAssessment:
    findings: list[str] = []
    name = (filename or "").lower()
    is_arxml = bool(ARXML_TAG_RE.search(text or "")) or name.endswith(".arxml")
    is_code = name.endswith((".c", ".h", ".cpp", ".hpp")) or bool(C_SOURCE_RE.search(text or ""))
    vendor_doc = any(k in name for k in ("microsar", "tresos", "elektrobit", "vector", "kpit", "eb_"))
    oem_doc = any(k in name for k in ("oem", "customer", "requirement", "rfq", "sow"))
    pii = bool(EMAIL_RE.search(text or "") or VIN_RE.search(text or ""))
    cred = bool(API_KEY_RE.search(text or ""))
    priv_ip = bool(PRIVATE_IP_RE.search(text or ""))
    if is_arxml:
        findings.append("arxml artifact")
    if is_code:
        findings.append("source code")
    if vendor_doc:
        findings.append("vendor document")
    if oem_doc:
        findings.append("oem/customer document")
    if pii:
        findings.append("pii detected")
    if cred:
        findings.append("credential/secret pattern")
    if priv_ip:
        findings.append("private network identifier")

    if cred or is_arxml or is_code or vendor_doc or oem_doc:
        classification, cloud_eligible = "confidential", False
    elif pii or priv_ip or declared in ("confidential", "restricted"):
        classification, cloud_eligible = declared if declared else "confidential", False
    elif declared in ("public", "internal"):
        classification, cloud_eligible = declared, declared == "public"
    else:
        classification, cloud_eligible = "internal", False
    return ContentRiskAssessment(
        classification=classification, findings=findings,
        pii_detected=pii, proprietary_code_detected=is_code or vendor_doc,
        arxml_detected=is_arxml, credential_detected=cred,
        cloud_eligible=cloud_eligible, redaction_required=pii or priv_ip,
        policy_reason="default-deny: ARXML/code/vendor/OEM/customer content is local_only; "
                      "spec PDFs are policy-controlled, never auto cloud-safe")


def routing_decision(ctx: SecurityContext, assessment: ContentRiskAssessment,
                     task: str = "chat_answer") -> dict:
    """Policy-controlled local/cloud routing. Never route on question category alone."""
    if ctx.cloud_policy == "local_only" or not assessment.cloud_eligible:
        return {"route": "local", "reason": f"policy={ctx.cloud_policy}; eligible={assessment.cloud_eligible}",
                "task": task, "redacted": False}
    if ctx.cloud_policy == "cloud_redacted_only":
        return {"route": "cloud", "reason": "explicit policy allows redacted cloud", "task": task, "redacted": True}
    if ctx.cloud_policy in ("cloud_metadata_only", "cloud_allowed") and assessment.cloud_eligible:
        return {"route": "cloud", "reason": "explicit policy + public classification", "task": task, "redacted": False}
    return {"route": "local", "reason": "default-deny fallback", "task": task, "redacted": False}
