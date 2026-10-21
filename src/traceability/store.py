"""Persistence for requirements, trace links, tests and findings (Phase 6).

One source of truth for the database: the registry DB
(`data/canonical/registry.db`). The traceability tables live in the same file
as the provenance spine, so a requirement and the evidence that covers it are
in one database and can be joined.

Two rules run through this module:

* **A machine may propose a trace link, but only a human may approve it.**
  `review_state` is written with the link and is never promoted automatically.
* **Nothing here asserts compliance.** The tables record the evidence that is
  available for review.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..registry.db import connect

__all__ = ["Finding", "TraceabilityStore"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class Finding:
    """A recorded problem — always with the evidence that supports it."""

    id: str
    project_id: str
    title: str
    severity: str = "info"          # info | low | medium | high | critical
    status: str = "open"            # open | investigating | resolved | accepted | rejected
    summary: str = ""
    source_type: str = ""
    source_id: str = ""
    test_run_id: str = ""
    test_result_id: str = ""
    affected_configuration: str = ""
    suspected_root_cause: str = ""
    owner: str = ""
    review_state: str = "machine-extracted"
    evidence: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


class TraceabilityStore:
    """CRUD over the Phase-6 tables."""

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            from ..config.settings import settings
            db_path = settings.registry_db
        self.db_path = db_path
        self._conn: sqlite3.Connection = connect(db_path)
        self._apply_migrations()

    def _apply_migrations(self) -> None:
        from ..registry.migrator import apply_migrations
        apply_migrations(self.db_path)

    # -- requirements ------------------------------------------------------
    def upsert_requirement(self, requirement, project_id: str = "") -> dict:
        data = requirement.to_dict() if hasattr(requirement, "to_dict") else dict(requirement)
        rid = str(data.get("id") or "")
        if not rid:
            raise ValueError("a requirement needs an id")
        now = _now()
        self._conn.execute(
            "INSERT INTO requirements(id, project_id, title, revision, status, source,"
            " parent_id, verification_method, module, autosar_release, artifact_version_id,"
            " description, properties_json, review_state, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET title=excluded.title, revision=excluded.revision,"
            " status=excluded.status, source=excluded.source, parent_id=excluded.parent_id,"
            " verification_method=excluded.verification_method, module=excluded.module,"
            " autosar_release=excluded.autosar_release,"
            " artifact_version_id=excluded.artifact_version_id,"
            " description=excluded.description, properties_json=excluded.properties_json,"
            " review_state=excluded.review_state, updated_at=excluded.updated_at",
            (rid, data.get("project_id") or project_id, data.get("title", ""),
             data.get("revision", ""), data.get("status", ""), data.get("source", ""),
             data.get("parent_id", ""), data.get("verification_method", ""),
             data.get("module", ""), data.get("autosar_release", ""),
             data.get("artifact_version_id", ""), data.get("description", ""),
             json.dumps(data.get("properties") or {}), data.get("review_state", ""),
             data.get("created_at") or now, now))
        self._conn.commit()
        return self.get_requirement(rid) or {}

    def get_requirement(self, requirement_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM requirements WHERE id=?",
                                 (requirement_id,)).fetchone()
        return self._requirement_row(row) if row else None

    def list_requirements(self, project_id: str = "", limit: int = 1000) -> list[dict]:
        if project_id:
            rows = self._conn.execute(
                "SELECT * FROM requirements WHERE project_id=? ORDER BY id LIMIT ?",
                (project_id, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM requirements ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [self._requirement_row(r) for r in rows]

    def _requirement_row(self, row) -> dict:
        return {
            "id": row["id"], "project_id": row["project_id"], "title": row["title"],
            "revision": row["revision"], "status": row["status"], "source": row["source"],
            "parent_id": row["parent_id"],
            "verification_method": row["verification_method"], "module": row["module"],
            "autosar_release": row["autosar_release"],
            "artifact_version_id": row["artifact_version_id"],
            "description": row["description"],
            "properties": json.loads(row["properties_json"] or "{}"),
            "review_state": row["review_state"], "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    # -- trace links -------------------------------------------------------
    def add_trace_link(self, *, project_id: str, source_type: str, source_id: str,
                       target_type: str, target_id: str, link_type: str = "traces",
                       review_state: str = "proposed", confidence: float = 1.0,
                       is_inferred: bool = False, extraction_method: str = "",
                       artifact_version_id: str = "", source_location_id: str = "",
                       reviewed_by: str = "", review_note: str = "",
                       link_id: str = "") -> dict:
        lid = link_id or _id("link")
        now = _now()
        self._conn.execute(
            "INSERT INTO trace_links(id, project_id, source_type, source_id, target_type,"
            " target_id, link_type, review_state, confidence, is_inferred,"
            " extraction_method, artifact_version_id, source_location_id, reviewed_by,"
            " review_note, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET review_state=excluded.review_state,"
            " confidence=excluded.confidence, reviewed_by=excluded.reviewed_by,"
            " review_note=excluded.review_note, updated_at=excluded.updated_at",
            (lid, project_id, source_type, source_id, target_type, target_id, link_type,
             review_state, float(confidence), 1 if is_inferred else 0, extraction_method,
             artifact_version_id, source_location_id, reviewed_by, review_note, now, now))
        self._conn.commit()
        return self.get_trace_link(lid) or {}

    def set_link_review_state(self, link_id: str, review_state: str,
                              reviewed_by: str = "", review_note: str = "") -> dict | None:
        """Record a human review decision on a proposed link."""
        self._conn.execute(
            "UPDATE trace_links SET review_state=?, reviewed_by=?, review_note=?,"
            " updated_at=? WHERE id=?",
            (review_state, reviewed_by, review_note, _now(), link_id))
        self._conn.commit()
        return self.get_trace_link(link_id)

    def get_trace_link(self, link_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM trace_links WHERE id=?",
                                 (link_id,)).fetchone()
        return dict(row) if row else None

    def list_trace_links(self, project_id: str = "", source_type: str = "",
                         target_type: str = "", limit: int = 2000) -> list[dict]:
        clauses, params = [], []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if source_type:
            clauses.append("source_type=?")
            params.append(source_type)
        if target_type:
            clauses.append("target_type=?")
            params.append(target_type)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM trace_links{where} ORDER BY id LIMIT ?", params).fetchall()
        return [dict(r) for r in rows]

    # -- tests -------------------------------------------------------------
    def upsert_test_case(self, case) -> dict:
        data = case.to_dict() if hasattr(case, "to_dict") else dict(case)
        cid = str(data.get("id") or "") or _id("test")
        now = _now()
        self._conn.execute(
            "INSERT INTO test_cases(id, project_id, suite, name, classname, file_path,"
            " line, parameters_json, tags_json, review_state, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET suite=excluded.suite, name=excluded.name,"
            " classname=excluded.classname, file_path=excluded.file_path, line=excluded.line,"
            " parameters_json=excluded.parameters_json, tags_json=excluded.tags_json,"
            " review_state=excluded.review_state, updated_at=excluded.updated_at",
            (cid, data.get("project_id", ""), data.get("suite", ""), data.get("name", ""),
             data.get("classname", ""), data.get("file_path", ""), data.get("line"),
             json.dumps(data.get("parameters") or {}), json.dumps(data.get("tags") or []),
             data.get("review_state", ""), data.get("created_at") or now, now))
        self._conn.commit()
        return self.get_test_case(cid) or {}

    def get_test_case(self, case_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM test_cases WHERE id=?",
                                 (case_id,)).fetchone()
        if not row:
            return None
        return {"id": row["id"], "project_id": row["project_id"], "suite": row["suite"],
                "name": row["name"], "classname": row["classname"],
                "file_path": row["file_path"], "line": row["line"],
                "parameters": json.loads(row["parameters_json"] or "{}"),
                "tags": json.loads(row["tags_json"] or "[]"),
                "review_state": row["review_state"]}

    def list_test_cases(self, project_id: str = "", limit: int = 2000) -> list[dict]:
        if project_id:
            rows = self._conn.execute(
                "SELECT id FROM test_cases WHERE project_id=? ORDER BY id LIMIT ?",
                (project_id, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM test_cases ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [self.get_test_case(r["id"]) for r in rows if self.get_test_case(r["id"])]

    def add_test_run(self, run) -> dict:
        data = run.to_dict() if hasattr(run, "to_dict") else dict(run)
        rid = str(data.get("id") or "") or _id("run")
        self._conn.execute(
            "INSERT INTO test_runs(id, project_id, suite, started_at, finished_at,"
            " duration_ms, tool, ci_run_id, ci_url, branch, commit_sha, artifact_version_id,"
            " summary_json, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET finished_at=excluded.finished_at,"
            " duration_ms=excluded.duration_ms, summary_json=excluded.summary_json",
            (rid, data.get("project_id", ""), data.get("suite", ""),
             data.get("started_at", ""), data.get("finished_at", ""),
             data.get("duration_ms", 0), data.get("tool", ""), data.get("ci_run_id", ""),
             data.get("ci_url", ""), data.get("branch", ""), data.get("commit_sha", ""),
             data.get("artifact_version_id", ""), json.dumps(data.get("summary") or {}),
             data.get("created_at") or _now()))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM test_runs WHERE id=?",
                                       (rid,)).fetchone() or {})

    def list_test_runs(self, project_id: str = "", limit: int = 200) -> list[dict]:
        if project_id:
            rows = self._conn.execute(
                "SELECT * FROM test_runs WHERE project_id=? ORDER BY started_at DESC LIMIT ?",
                (project_id, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM test_runs ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["summary"] = json.loads(data.pop("summary_json", "{}") or "{}")
            out.append(data)
        return out

    def add_test_result(self, result) -> dict:
        data = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        rid = str(data.get("id") or "") or _id("result")
        self._conn.execute(
            "INSERT INTO test_results(id, run_id, test_case_id, name, classname, status,"
            " duration_ms, message, stdout, stderr, artifact_version_id, source_location_id,"
            " created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET status=excluded.status,"
            " duration_ms=excluded.duration_ms, message=excluded.message,"
            " stdout=excluded.stdout, stderr=excluded.stderr",
            (rid, data.get("run_id", ""), data.get("test_case_id", ""),
             data.get("name", ""), data.get("classname", ""), data.get("status", ""),
             data.get("duration_ms", 0), data.get("message", ""), data.get("stdout", ""),
             data.get("stderr", ""), data.get("artifact_version_id", ""),
             data.get("source_location_id", ""), data.get("created_at") or _now()))
        self._conn.commit()
        return dict(self._conn.execute("SELECT * FROM test_results WHERE id=?",
                                       (rid,)).fetchone() or {})

    def list_test_results(self, run_id: str = "", limit: int = 5000) -> list[dict]:
        if run_id:
            rows = self._conn.execute(
                "SELECT * FROM test_results WHERE run_id=? ORDER BY id LIMIT ?",
                (run_id, limit)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM test_results ORDER BY id LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # -- findings ----------------------------------------------------------
    def add_finding(self, finding: Finding) -> dict:
        now = _now()
        self._conn.execute(
            "INSERT INTO findings(id, project_id, title, severity, status, summary,"
            " source_type, source_id, test_run_id, test_result_id, affected_configuration,"
            " suspected_root_cause, owner, review_state, evidence_json, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(id) DO UPDATE SET title=excluded.title, severity=excluded.severity,"
            " status=excluded.status, summary=excluded.summary, owner=excluded.owner,"
            " review_state=excluded.review_state, evidence_json=excluded.evidence_json,"
            " updated_at=excluded.updated_at",
            (finding.id, finding.project_id, finding.title, finding.severity,
             finding.status, finding.summary, finding.source_type, finding.source_id,
             finding.test_run_id, finding.test_result_id, finding.affected_configuration,
             finding.suspected_root_cause, finding.owner, finding.review_state,
             json.dumps(finding.evidence or []), finding.created_at or now, now))
        self._conn.commit()
        return self.get_finding(finding.id) or {}

    def get_finding(self, finding_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM findings WHERE id=?",
                                 (finding_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["evidence"] = json.loads(data.pop("evidence_json", "[]") or "[]")
        return data

    def list_findings(self, project_id: str = "", severity: str = "",
                      limit: int = 1000) -> list[dict]:
        clauses, params = [], []
        if project_id:
            clauses.append("project_id=?")
            params.append(project_id)
        if severity:
            clauses.append("severity=?")
            params.append(severity)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM findings{where} ORDER BY id LIMIT ?", params).fetchall()
        out = []
        for row in rows:
            data = dict(row)
            data["evidence"] = json.loads(data.pop("evidence_json", "[]") or "[]")
            out.append(data)
        return out

    def close(self) -> None:
        self._conn.close()
