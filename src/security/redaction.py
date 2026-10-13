"""Reversible-token redaction. The token map NEVER leaves the local boundary (Phase 2 §4)."""
from __future__ import annotations

import re
from src.security.policy import VIN_RE, PRIVATE_IP_RE, EMAIL_RE

_PROJECT_RE = re.compile(r"\b([A-Z][A-Za-z0-9_-]{2,40}-(?:ECU|Project|Platform)[A-Za-z0-9_-]*)\b")


def redact(text: str, project_hint: str = "") -> tuple[str, dict[str, str]]:
    """Returns (redacted_text, token_map). Keep token_map local-only."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def _tok(kind: str, value: str) -> str:
        if value in mapping.values():
            return next(k for k, v in mapping.items() if v == value)
        counters[kind] = counters.get(kind, 0) + 1
        tok = f"<{kind}_{counters[kind]:03d}>"
        mapping[tok] = value
        return tok

    def _sub(rx: re.Pattern, kind: str, s: str) -> str:
        return rx.sub(lambda m: _tok(kind, m.group(0)), s)

    out = _sub(VIN_RE, "VIN", text)
    out = _sub(PRIVATE_IP_RE, "INTERNAL_IP", out)
    out = _sub(EMAIL_RE, "EMAIL", out)
    if project_hint:
        out = out.replace(project_hint, _tok("PROJECT", project_hint))
    out = _sub(_PROJECT_RE, "PROJECT", out)
    return out, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    for tok, val in mapping.items():
        text = text.replace(tok, val)
    return text
