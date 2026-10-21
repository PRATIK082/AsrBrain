"""Test and log intelligence (Phase 6).

Test results arrive from CI systems in many shapes. This module reads the
common ones through **adapters** — a JUnit XML file, a generic CSV export — and
turns them into one model: test cases, runs and results.

A result is a fact about a run, not a verdict about the product. Nothing here
decides whether a failure is a defect; it records the failure, the run it came
from and the evidence around it.
"""
from __future__ import annotations

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

__all__ = [
    "TestCase",
    "TestResult",
    "TestRun",
    "cluster_failures",
    "ingest_junit_xml",
    "ingest_test_results_csv",
    "test_adapters",
]

_STATUS_MAP = {
    "passed": "passed", "pass": "passed", "ok": "passed", "success": "passed",
    "failed": "failed", "fail": "failed", "error": "failed", "failure": "failed",
    "skipped": "skipped", "skip": "skipped", "disabled": "skipped",
    "pending": "skipped", "xfail": "skipped",
    "error": "error", "errored": "error", "broken": "error",
    "unknown": "unknown",
}


@dataclass
class TestCase:
    id: str
    name: str = ""
    suite: str = ""
    classname: str = ""
    file_path: str = ""
    line: int | None = None
    parameters: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "suite": self.suite,
                "classname": self.classname, "file_path": self.file_path,
                "line": self.line, "parameters": self.parameters, "tags": self.tags}


@dataclass
class TestResult:
    id: str
    run_id: str
    test_case_id: str = ""
    name: str = ""
    classname: str = ""
    status: str = "unknown"
    duration_ms: int = 0
    message: str = ""
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "run_id": self.run_id, "test_case_id": self.test_case_id,
                "name": self.name, "classname": self.classname, "status": self.status,
                "duration_ms": self.duration_ms, "message": self.message,
                "stdout": self.stdout, "stderr": self.stderr}


@dataclass
class TestRun:
    id: str
    suite: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_ms: int = 0
    tool: str = ""
    ci_run_id: str = ""
    ci_url: str = ""
    branch: str = ""
    commit_sha: str = ""
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"id": self.id, "suite": self.suite, "started_at": self.started_at,
                "finished_at": self.finished_at, "duration_ms": self.duration_ms,
                "tool": self.tool, "ci_run_id": self.ci_run_id, "ci_url": self.ci_url,
                "branch": self.branch, "commit_sha": self.commit_sha,
                "summary": self.summary}


def _status(value: str) -> str:
    return _STATUS_MAP.get((value or "").strip().lower(), "unknown")


def _seconds_to_ms(value) -> int:
    try:
        return int(round(float(value) * 1000))
    except (TypeError, ValueError):
        return 0


def ingest_junit_xml(text: str, run_id: str = "", suite: str = "",
                     tool: str = "junit", ci_run_id: str = "",
                     branch: str = "", commit_sha: str = "") -> tuple[list[TestCase], TestRun, list[TestResult]]:
    """Read a JUnit XML report (pytest, JUnit, most CI systems).

    Returns `(cases, run, results)`.
    """
    root = ET.fromstring(text or "")
    if root.tag == "testsuites":
        suites = list(root.findall("testsuite"))
    else:
        suites = [root]

    run = TestRun(
        id=run_id or f"run-{suite or 'junit'}",
        suite=suite or (suites[0].get("name", "") if suites else ""),
        started_at=(suites[0].get("timestamp", "") if suites else ""),
        duration_ms=sum(_seconds_to_ms(s.get("time", 0)) for s in suites),
        tool=tool,
        ci_run_id=ci_run_id,
        branch=branch,
        commit_sha=commit_sha,
        summary={},
    )

    cases: list[TestCase] = []
    results: list[TestResult] = []
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "unknown": 0}
    index = 0
    for suite in suites:
        suite_name = suite.get("name", "")
        for case_el in suite.findall("testcase"):
            index += 1
            name = case_el.get("name", "")
            classname = case_el.get("classname", "")
            case_id = f"{classname}::{name}" if classname else name
            file_path = case_el.get("file", "")
            line = int(case_el["line"]) if case_el.get("line") else None
            cases.append(TestCase(id=case_id, name=name, suite=suite_name,
                                  classname=classname, file_path=file_path, line=line))

            status = "passed"
            message = ""
            stdout = ""
            stderr = ""
            failure = case_el.find("failure")
            error = case_el.find("error")
            skipped = case_el.find("skipped")
            if failure is not None:
                status = "failed"
                message = (failure.get("message") or (failure.text or "")).strip()
            elif error is not None:
                status = "error"
                message = (error.get("message") or (error.text or "")).strip()
            elif skipped is not None:
                status = "skipped"
                message = (skipped.get("message") or (skipped.text or "")).strip()
            out = case_el.find("system-out")
            err = case_el.find("system-err")
            if out is not None and out.text:
                stdout = out.text.strip()[:8000]
            if err is not None and err.text:
                stderr = err.text.strip()[:8000]
            counts[status] = counts.get(status, 0) + 1
            results.append(TestResult(
                id=f"{run.id}-r{index}", run_id=run.id, test_case_id=case_id,
                name=name, classname=classname, status=status,
                duration_ms=_seconds_to_ms(case_el.get("time", 0)),
                message=message[:2000], stdout=stdout, stderr=stderr,
            ))
    run.summary = {"total": len(results), **counts}
    return cases, run, results


_CSV_ALIASES = {
    "name": ("name", "test", "test_name", "testcase", "case"),
    "classname": ("classname", "class", "suite", "class_name"),
    "status": ("status", "result", "outcome", "state"),
    "duration": ("duration", "time", "duration_s", "duration_ms", "elapsed"),
    "message": ("message", "error", "failure", "detail", "details"),
    "file": ("file", "file_path", "path", "location"),
    "line": ("line", "lineno", "line_number"),
}


def _pick_csv(row: dict, name: str) -> str:
    for alias in _CSV_ALIASES[name]:
        if alias in row and row[alias] not in (None, ""):
            return str(row[alias]).strip()
    return ""


def ingest_test_results_csv(text: str, run_id: str = "", suite: str = "",
                            tool: str = "csv", branch: str = "",
                            commit_sha: str = "") -> tuple[list[TestCase], TestRun, list[TestResult]]:
    """Read a generic CSV export of test results."""
    reader = csv.DictReader(io.StringIO(text or ""))
    run = TestRun(id=run_id or f"run-{suite or 'csv'}", suite=suite, tool=tool,
                  branch=branch, commit_sha=commit_sha)
    cases: list[TestCase] = []
    results: list[TestResult] = []
    counts = {"passed": 0, "failed": 0, "skipped": 0, "error": 0, "unknown": 0}
    index = 0
    for row in reader:
        index += 1
        name = _pick_csv(row, "name")
        if not name:
            continue
        classname = _pick_csv(row, "classname")
        case_id = f"{classname}::{name}" if classname else name
        status = _status(_pick_csv(row, "status"))
        duration_raw = _pick_csv(row, "duration")
        duration_ms = (int(duration_raw) if duration_raw.isdigit()
                       and "ms" not in duration_raw.lower()
                       else _seconds_to_ms(duration_raw))
        cases.append(TestCase(id=case_id, name=name, suite=suite or classname,
                              classname=classname, file_path=_pick_csv(row, "file")))
        counts[status] = counts.get(status, 0) + 1
        results.append(TestResult(
            id=f"{run.id}-r{index}", run_id=run.id, test_case_id=case_id,
            name=name, classname=classname, status=status, duration_ms=duration_ms,
            message=_pick_csv(row, "message")[:2000],
        ))
    run.duration_ms = sum(r.duration_ms for r in results)
    run.summary = {"total": len(results), **counts}
    return cases, run, results


def cluster_failures(results: list[TestResult]) -> list[dict]:
    """Group failures by their message shape.

    Two failures that differ only in a number or a path are the same defect
    seen twice. The key is the message with every digit and hex blob replaced
    by a placeholder, so the cluster key is stable across runs.
    """
    clusters: dict[str, dict] = {}
    for result in results:
        # Accept both the dataclass and a plain dict (the store returns dicts).
        get = result.get if isinstance(result, dict) else lambda k, d="": getattr(result, k, d)
        status = get("status", "")
        if status not in ("failed", "error"):
            continue
        message = get("message", "") or ""
        name = get("name", "") or ""
        result_id = get("id", "") or ""
        test_case_id = get("test_case_id", "") or ""
        key = re.sub(r"[0-9a-fA-F]{6,}", "<hex>", message or name or "failure")
        key = re.sub(r"\d+", "<n>", key).strip().lower()[:200]
        cluster = clusters.setdefault(key, {
            "key": key, "count": 0, "statuses": [], "examples": [],
            "test_cases": [], "first_message": message,
        })
        cluster["count"] += 1
        cluster["statuses"].append(status)
        if test_case_id and test_case_id not in cluster["test_cases"]:
            cluster["test_cases"].append(test_case_id)
        if len(cluster["examples"]) < 3:
            cluster["examples"].append({"result_id": result_id, "name": name,
                                        "message": message[:400]})
    return sorted(clusters.values(), key=lambda c: -c["count"])


def test_adapters() -> list[dict]:
    """The ingestion adapters, for discovery by the API and the agent."""
    return [
        {"name": "junit_xml", "description": "JUnit XML test report (pytest, JUnit, most CI systems).",
         "extensions": [".xml"], "mutating": False},
        {"name": "test_csv", "description": "Generic CSV export of test results.",
         "extensions": [".csv"], "mutating": False},
    ]
