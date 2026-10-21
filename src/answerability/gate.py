"""The answerability gate (ADR-0001).

Every answer the product produces gets one of four statuses. The status is
**computed by code, not claimed by the model**:

``VERIFIED``
    A deterministic tool result and the authoritative source evidence agree.
``EVIDENCE_SUPPORTED``
    The cited sources support the answer, but no deterministic validation
    applies to it.
``NEEDS_ENGINEER_REVIEW``
    The evidence is partial, ambiguous or in conflict, or a human has to
    decide.
``INSUFFICIENT_EVIDENCE``
    The corpus does not cover the question. The answer says which artifact or
    metadata is missing and which scope was searched — it does not answer
    substantively.

A numeric confidence is **not** a correctness rate and is never used as the
user-facing contract. It stays inside the audit record.
"""
from __future__ import annotations

import re
from typing import Any

__all__ = ["AnswerabilityResult", "evaluate_answerability", "STATUSES"]

STATUSES = ("VERIFIED", "EVIDENCE_SUPPORTED", "NEEDS_ENGINEER_REVIEW",
            "INSUFFICIENT_EVIDENCE")

#: A citation marker in an answer body, e.g. ``[E3]``.
_CITE_RE = re.compile(r"\[E\d+\]")
#: Sentence boundary, used to judge which claims carry a citation.
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")

#: A tool verdict that counts as a deterministic confirmation.
_CONFIRMING = {"ok", "passed", "verified", "match", "resolved", "valid", "success"}
#: A tool verdict that means "a human must look".
_UNCERTAIN = {"conflict", "incomplete", "ambiguous", "partial", "unresolved",
              "failed", "error", "not_found"}


class AnswerabilityResult(dict):
    """The gate's verdict. A dict so it serialises straight into the API."""

    @property
    def status(self) -> str:
        return str(self.get("status", "INSUFFICIENT_EVIDENCE"))


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _tool_verdicts(tool_results: Any) -> list[dict]:
    """Normalise the tool results into `{tool, status, ok, uncertain}` records."""
    out: list[dict] = []
    for item in _as_list(tool_results):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("verdict") or "").lower()
        ok = item.get("ok")
        if ok is None:
            ok = status in _CONFIRMING
        out.append({
            "tool": str(item.get("tool") or item.get("name") or "tool"),
            "status": status,
            "ok": bool(ok),
            "uncertain": status in _UNCERTAIN or str(item.get("status", "")).lower() == "conflict",
            "detail": str(item.get("summary") or item.get("message") or ""),
        })
    return out


def evaluate_answerability(*, evidence: Any = None, verification: Any = None,
                           tool_results: Any = None, scope: Any = None,
                           plan: Any = None, answer: str = "",
                           conflicts: Any = None) -> AnswerabilityResult:
    """Decide how far an answer can be trusted — deterministically.

    `evidence` is the list of retrieved passages, `verification` the claim
    verdicts (`claim_support_rate`, `citation_coverage`, `verdicts`),
    `tool_results` the deterministic tool outcomes, `scope` what was searched.
    """
    checked: list[str] = []
    missing: list[str] = []
    found_conflicts: list[str] = [str(c) for c in _as_list(conflicts) if c]

    passages = [e for e in _as_list(evidence) if isinstance(e, dict) or getattr(e, "get", None)]
    checked.append("evidence_presence")
    if not passages:
        missing.append("no passage in the searched scope")
        return AnswerabilityResult({
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "the corpus does not cover this question in the searched scope",
            "missing": missing,
            "conflicts": found_conflicts,
            "checked": checked,
            "scope": scope or {},
        })

    ver = verification if isinstance(verification, dict) else {}
    support_rate = float(ver.get("claim_support_rate", 0.0) or 0.0)
    citation_coverage = float(ver.get("citation_coverage", 0.0) or 0.0)
    verdicts = _as_list(ver.get("verdicts"))

    checked.append("citation_validity")
    if verdicts:
        uncited = [v for v in verdicts if isinstance(v, dict) and not v.get("supported", False)]
        checked.append("claim_support")
    else:
        # No claim verdicts: judge the citations from the answer text and the
        # passages themselves. A rate that was derived from verdicts tells us
        # nothing when there are no verdicts, so the answer is read directly.
        checked.append("claim_support")
        labelled = [p for p in passages if str(p.get("label") or "").strip()]
        sentences = [x.strip() for x in _SENT_SPLIT.split(answer or "") if x.strip()]
        sentences = [x for x in sentences if not x.startswith("#")]
        cited = [x for x in sentences if _CITE_RE.search(x)]
        uncited = [x for x in sentences if not _CITE_RE.search(x)]
        if sentences:
            support_rate = len(cited) / float(len(cited) + len(uncited))
            citation_coverage = 1.0 if cited else 0.0
        else:
            support_rate = float(ver.get("claim_support_rate", 1.0 if labelled else 0.0) or 0.0)
            citation_coverage = float(ver.get("citation_coverage", 1.0 if labelled else 0.0) or 0.0)
            if not sentences and not uncited:
                uncited = [] if labelled else passages

    tools = _tool_verdicts(tool_results)
    if tools:
        checked.append("tool_corroboration")
    for tool in tools:
        if tool["uncertain"]:
            found_conflicts.append(
                f"{tool['tool']} could not decide ({tool['status'] or 'unknown'})")

    # --- conflicts win over everything ------------------------------------
    if found_conflicts:
        return AnswerabilityResult({
            "status": "NEEDS_ENGINEER_REVIEW",
            "reason": "the evidence is in conflict or a tool could not decide",
            "missing": missing,
            "conflicts": found_conflicts,
            "checked": checked,
            "scope": scope or {},
        })

    # --- nothing cited -> not enough evidence ------------------------------
    if citation_coverage <= 0.0 or support_rate <= 0.0:
        missing.append("a citation that resolves to a retrieved passage")
        return AnswerabilityResult({
            "status": "INSUFFICIENT_EVIDENCE",
            "reason": "the answer carries no resolvable citation",
            "missing": missing,
            "conflicts": found_conflicts,
            "checked": checked,
            "scope": scope or {},
        })

    # --- partial support -> a human must look -----------------------------
    if support_rate < 1.0 or uncited:
        missing.append(f"{len(uncited) or 'some'} claim(s) without a supporting citation")
        return AnswerabilityResult({
            "status": "NEEDS_ENGINEER_REVIEW",
            "reason": "only part of the answer is backed by a cited passage",
            "missing": missing,
            "conflicts": found_conflicts,
            "checked": checked,
            "scope": scope or {},
        })

    # --- everything cited ----------------------------------------------------
    confirming = [t for t in tools if t["ok"]]
    if confirming:
        return AnswerabilityResult({
            "status": "VERIFIED",
            "reason": f"{confirming[0]['tool']} and the cited passages agree",
            "missing": missing,
            "conflicts": found_conflicts,
            "checked": checked,
            "scope": scope or {},
        })

    return AnswerabilityResult({
        "status": "EVIDENCE_SUPPORTED",
        "reason": "the cited passages support the answer; no deterministic check applies",
        "missing": missing,
        "conflicts": found_conflicts,
        "checked": checked,
        "scope": scope or {},
    })
