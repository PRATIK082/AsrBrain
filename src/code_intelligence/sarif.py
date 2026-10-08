"""SARIF static-analysis adapter (P2/P3). Ingests external tool findings verbatim with
provenance; reported as `tool_reported`, never as a compliance determination.
"""
from __future__ import annotations

from src.code_intelligence.advisory import CodeFinding


def ingest_sarif(sarif: dict, tool_label: str = "") -> list[CodeFinding]:
    out: list[CodeFinding] = []
    runs = sarif.get("runs", []) if isinstance(sarif, dict) else []
    for run in runs:
        driver = ((run.get("tool") or {}).get("driver") or {})
        tool = tool_label or driver.get("name", "external-analyzer")
        version = driver.get("version", "")
        for res in run.get("results", []):
            rule = res.get("ruleId", "external-rule")
            msg = (res.get("message") or {}).get("text", "")
            loc = ""
            try:
                pl = res["locations"][0]["physicalLocation"]
                loc = f"{pl['artifactLocation']['uri']}:{pl['region'].get('startLine', '?')}"
            except Exception:
                pass
            out.append(CodeFinding(rule=f"{tool}/{rule}", level="tool_reported",
                                   location=loc, message=msg,
                                   provenance=f"sarif:{tool}:{version}"))
    return out
