"""Registry store — the provenance-first system of record (ADR-0002, ADR-0003).

The store owns one SQLite file today and is written so the same DDL and the
same call sites work against PostgreSQL later: every table is portable SQL,
every JSON column is stored as text and parsed on read, and no query relies on
SQLite-only syntax. Nothing here is destructive — the registry is additive and
can be rebuilt from the artifacts it describes.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from .db import connect, default_registry_db
from .migrator import apply_migrations
from .models import (
    AnswerAudit,
    Artifact,
    ArtifactVersion,
    Citation,
    EvidenceClaim,
    Job,
    Project,
    SourceLocation,
    ValidationResult,
    Workspace,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _load(value: Any) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _loads(value: Any) -> list:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


class RegistryStore:
    """CRUD over the registry tables. One instance = one database file."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_registry_db()
        apply_migrations(self.db_path)
        self._conn = connect(self.db_path)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # projects & workspaces
    # ------------------------------------------------------------------ #

    def create_project(self, name: str, project_id: str = "", description: str = "",
                       owner: str = "", data_classification: str = "internal",
                       access_policy: dict | None = None) -> Project:
        pid = project_id or _id("prj")
        ts = _now()
        self._conn.execute(
            "INSERT INTO projects(id, name, description, owner, data_classification,"
            " access_policy, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (pid, name, description, owner, data_classification, _json(access_policy), ts, ts),
        )
        self._conn.commit()
        project = self.get_project(pid)
        assert project is not None
        return project

    def get_project(self, project_id: str) -> Project | None:
        row = self._conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            return None
        return Project(
            id=row["id"], name=row["name"], description=row["description"],
            owner=row["owner"], data_classification=row["data_classification"],
            access_policy=_load(row["access_policy"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_projects(self) -> list[Project]:
        rows = self._conn.execute("SELECT id FROM projects ORDER BY created_at, id").fetchall()
        out = [p for p in (self.get_project(r["id"]) for r in rows) if p is not None]
        return out

    def create_workspace(self, project_id: str, name: str, workspace_id: str = "",
                         description: str = "", scope: str = "") -> Workspace:
        if self.get_project(project_id) is None:
            raise ValueError(f"unknown project: {project_id}")
        wid = workspace_id or _id("ws")
        ts = _now()
        self._conn.execute(
            "INSERT INTO workspaces(id, project_id, name, description, scope, created_at, updated_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (wid, project_id, name, description, scope, ts, ts),
        )
        self._conn.commit()
        ws = self.get_workspace(wid)
        assert ws is not None
        return ws

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        row = self._conn.execute("SELECT * FROM workspaces WHERE id=?", (workspace_id,)).fetchone()
        if row is None:
            return None
        return Workspace(
            id=row["id"], project_id=row["project_id"], name=row["name"],
            description=row["description"], scope=row["scope"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_workspaces(self, project_id: str = "") -> list[Workspace]:
        if project_id:
            rows = self._conn.execute(
                "SELECT id FROM workspaces WHERE project_id=? ORDER BY created_at, id",
                (project_id,)).fetchall()
        else:
            rows = self._conn.execute("SELECT id FROM workspaces ORDER BY created_at, id").fetchall()
        return [w for w in (self.get_workspace(r["id"]) for r in rows) if w is not None]

    # ------------------------------------------------------------------ #
    # artifacts & versions
    # ------------------------------------------------------------------ #

    def register_artifact(self, project_id: str, name: str, kind: str = "external",
                          artifact_id: str = "", workspace_id: str = "", source_uri: str = "",
                          content_hash: str = "", owner: str = "", branch: str = "",
                          autosar_release: str = "", data_classification: str = "internal",
                          access_policy: dict | None = None) -> Artifact:
        if self.get_project(project_id) is None:
            raise ValueError(f"unknown project: {project_id}")
        aid = artifact_id or _id("art")
        ts = _now()
        self._conn.execute(
            "INSERT INTO artifacts(id, project_id, workspace_id, kind, name, source_uri,"
            " content_hash, owner, branch, autosar_release, data_classification, access_policy,"
            " lifecycle_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, project_id, workspace_id, kind, name, source_uri, content_hash, owner, branch,
             autosar_release, data_classification, _json(access_policy), "active", ts, ts),
        )
        self._conn.commit()
        artifact = self.get_artifact(aid)
        assert artifact is not None
        return artifact

    def get_artifact(self, artifact_id: str) -> Artifact | None:
        row = self._conn.execute("SELECT * FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
        if row is None:
            return None
        return Artifact(
            id=row["id"], project_id=row["project_id"], workspace_id=row["workspace_id"],
            kind=row["kind"], name=row["name"], source_uri=row["source_uri"],
            content_hash=row["content_hash"], owner=row["owner"], branch=row["branch"],
            autosar_release=row["autosar_release"],
            data_classification=row["data_classification"],
            access_policy=_load(row["access_policy"]),
            lifecycle_state=row["lifecycle_state"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def list_artifacts(self, project_id: str = "", kind: str = "") -> list[Artifact]:
        sql = "SELECT id FROM artifacts"
        params: list = []
        if project_id:
            sql += " WHERE project_id=?"
            params.append(project_id)
        if kind:
            sql += (" AND" if project_id else " WHERE") + " kind=?"
            params.append(kind)
        sql += " ORDER BY created_at, id"
        return [a for a in (self.get_artifact(r["id"]) for r in self._conn.execute(sql, params).fetchall())
                if a is not None]

    def create_artifact_version(self, artifact_id: str, version_label: str = "",
                                content_hash: str = "", size_bytes: int = 0,
                                storage_uri: str = "", source_uri: str = "",
                                extracted_at: str = "", extractor_name: str = "",
                                extractor_version: str = "", extraction_confidence: float = 1.0,
                                metadata: dict | None = None, version_id: str = "",
                                lifecycle_state: str = "active") -> ArtifactVersion:
        if self.get_artifact(artifact_id) is None:
            raise ValueError(f"unknown artifact: {artifact_id}")
        vid = version_id or _id("ver")
        ts = _now()
        self._conn.execute(
            "INSERT INTO artifact_versions(id, artifact_id, version_label, content_hash,"
            " size_bytes, storage_uri, source_uri, extracted_at, extractor_name, extractor_version,"
            " extraction_confidence, metadata_json, lifecycle_state, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (vid, artifact_id, version_label, content_hash, size_bytes, storage_uri, source_uri,
             extracted_at or ts, extractor_name, extractor_version, extraction_confidence,
             _json(metadata), lifecycle_state, ts),
        )
        self._conn.commit()
        version = self.get_artifact_version(vid)
        assert version is not None
        return version

    def get_artifact_version(self, version_id: str) -> ArtifactVersion | None:
        row = self._conn.execute(
            "SELECT * FROM artifact_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            return None
        return ArtifactVersion(
            id=row["id"], artifact_id=row["artifact_id"], version_label=row["version_label"],
            content_hash=row["content_hash"], size_bytes=row["size_bytes"] or 0,
            storage_uri=row["storage_uri"], source_uri=row["source_uri"],
            extracted_at=row["extracted_at"], extractor_name=row["extractor_name"],
            extractor_version=row["extractor_version"],
            extraction_confidence=row["extraction_confidence"] or 0.0,
            metadata=_load(row["metadata_json"]),
            lifecycle_state=row["lifecycle_state"], created_at=row["created_at"],
        )

    def list_artifact_versions(self, artifact_id: str = "") -> list[ArtifactVersion]:
        if artifact_id:
            rows = self._conn.execute(
                "SELECT id FROM artifact_versions WHERE artifact_id=? ORDER BY created_at, id",
                (artifact_id,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM artifact_versions ORDER BY created_at, id").fetchall()
        return [v for v in (self.get_artifact_version(r["id"]) for r in rows) if v is not None]

    # ------------------------------------------------------------------ #
    # source locations & citations
    # ------------------------------------------------------------------ #

    def add_source_location(self, artifact_version_id: str, locator_type: str, locator: str,
                            location_id: str = "", page_start: int | None = None,
                            page_end: int | None = None, section: str = "",
                            line_start: int | None = None, line_end: int | None = None,
                            release: str = "", module: str = "",                             snippet: str = "") -> SourceLocation:
        if self.get_artifact_version(artifact_version_id) is None:
            raise ValueError(f"unknown artifact version: {artifact_version_id}")
        lid = location_id or _id("loc")
        self._conn.execute(
            "INSERT INTO source_locations(id, artifact_version_id, locator_type, locator,"
            " page_start, page_end, section, line_start, line_end, release, module, snippet, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (lid, artifact_version_id, locator_type, locator, page_start, page_end, section,
             line_start, line_end, release, module, snippet, _now()),
        )
        self._conn.commit()
        loc = self.get_source_location(lid)
        assert loc is not None
        return loc

    def get_source_location(self, location_id: str) -> SourceLocation | None:
        row = self._conn.execute(
            "SELECT * FROM source_locations WHERE id=?", (location_id,)).fetchone()
        if row is None:
            return None
        return SourceLocation(
            id=row["id"], artifact_version_id=row["artifact_version_id"],
            locator_type=row["locator_type"], locator=row["locator"],
            page_start=row["page_start"], page_end=row["page_end"], section=row["section"],
            line_start=row["line_start"], line_end=row["line_end"],
            release=row["release"], module=row["module"], snippet=row["snippet"],
            created_at=row["created_at"],
        )

    def list_source_locations(self, artifact_version_id: str = "") -> list[SourceLocation]:
        if artifact_version_id:
            rows = self._conn.execute(
                "SELECT id FROM source_locations WHERE artifact_version_id=?"
                " ORDER BY created_at, id", (artifact_version_id,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM source_locations ORDER BY created_at, id").fetchall()
        return [l for l in (self.get_source_location(r["id"]) for r in rows) if l is not None]

    def add_citation(self, source_location_id: str, answer_id: str = "",
                     conversation_id: str = "", message_id: str = "",
                     artifact_version_id: str = "", label: str = "", claim: str = "",
                     citation_id: str = "") -> Citation:
        if self.get_source_location(source_location_id) is None:
            raise ValueError(f"unknown source location: {source_location_id}")
        cid = citation_id or _id("cit")
        self._conn.execute(
            "INSERT INTO citations(id, answer_id, conversation_id, message_id, source_location_id,"
            " artifact_version_id, label, claim, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (cid, answer_id, conversation_id, message_id, source_location_id,
             artifact_version_id, label, claim, _now()),
        )
        self._conn.commit()
        cit = self.get_citation(cid)
        assert cit is not None
        return cit

    def get_citation(self, citation_id: str) -> Citation | None:
        row = self._conn.execute("SELECT * FROM citations WHERE id=?", (citation_id,)).fetchone()
        if row is None:
            return None
        return Citation(
            id=row["id"], source_location_id=row["source_location_id"],
            answer_id=row["answer_id"], conversation_id=row["conversation_id"],
            message_id=row["message_id"], artifact_version_id=row["artifact_version_id"],
            label=row["label"], claim=row["claim"], created_at=row["created_at"],
        )

    def list_citations(self, answer_id: str = "") -> list[Citation]:
        if answer_id:
            rows = self._conn.execute(
                "SELECT id FROM citations WHERE answer_id=? ORDER BY created_at, id",
                (answer_id,)).fetchall()
        else:
            rows = self._conn.execute("SELECT id FROM citations ORDER BY created_at, id").fetchall()
        return [c for c in (self.get_citation(r["id"]) for r in rows) if c is not None]

    # ------------------------------------------------------------------ #
    # evidence claims & validation results
    # ------------------------------------------------------------------ #

    def add_evidence_claim(self, claim: str, answer_id: str = "",
                           claim_type: str = "fact", status: str = "EVIDENCE_SUPPORTED",
                           reason: str = "", citation_ids: list[str] | None = None,
                           missing: list[str] | None = None,
                           conflicts: list[str] | None = None,
                           checked: list[str] | None = None, confidence: float = 0.0,
                           claim_id: str = "") -> EvidenceClaim:
        cid = claim_id or _id("clm")
        self._conn.execute(
            "INSERT INTO evidence_claims(id, answer_id, claim, claim_type, status, reason,"
            " citation_ids, missing, conflicts, checked, confidence, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, answer_id, claim, claim_type, status, reason,
             _json(citation_ids or []), _json(missing or []), _json(conflicts or []),
             _json(checked or []), confidence, _now()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM evidence_claims WHERE id=?", (cid,)).fetchone()
        assert row is not None
        return EvidenceClaim(
            id=row["id"], claim=row["claim"], answer_id=row["answer_id"],
            claim_type=row["claim_type"], status=row["status"], reason=row["reason"],
            citation_ids=_loads(row["citation_ids"]), missing=_loads(row["missing"]),
            conflicts=_loads(row["conflicts"]), checked=_loads(row["checked"]),
            confidence=row["confidence"] or 0.0, created_at=row["created_at"],
        )

    def list_evidence_claims(self, answer_id: str = "") -> list[EvidenceClaim]:
        if answer_id:
            rows = self._conn.execute(
                "SELECT id FROM evidence_claims WHERE answer_id=? ORDER BY created_at, id",
                (answer_id,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id FROM evidence_claims ORDER BY created_at, id").fetchall()
        out: list[EvidenceClaim] = []
        for r in rows:
            row = self._conn.execute(
                "SELECT * FROM evidence_claims WHERE id=?", (r["id"],)).fetchone()
            if row is None:
                continue
            out.append(EvidenceClaim(
                id=row["id"], claim=row["claim"], answer_id=row["answer_id"],
                claim_type=row["claim_type"], status=row["status"], reason=row["reason"],
                citation_ids=_loads(row["citation_ids"]), missing=_loads(row["missing"]),
                conflicts=_loads(row["conflicts"]), checked=_loads(row["checked"]),
                confidence=row["confidence"] or 0.0, created_at=row["created_at"],
            ))
        return out

    def add_validation_result(self, artifact_version_id: str, tool_name: str,
                              status: str = "unknown", severity: str = "info",
                              message: str = "", details: dict | None = None,
                              result_id: str = "") -> ValidationResult:
        rid = result_id or _id("val")
        self._conn.execute(
            "INSERT INTO validation_results(id, artifact_version_id, tool_name, status, severity,"
            " message, details_json, created_at) VALUES(?,?,?,?,?,?,?,?)",
            (rid, artifact_version_id, tool_name, status, severity, message,
             _json(details), _now()),
        )
        self._conn.commit()
        row = self._conn.execute(
            "SELECT * FROM validation_results WHERE id=?", (rid,)).fetchone()
        assert row is not None
        return ValidationResult(
            id=row["id"], artifact_version_id=row["artifact_version_id"],
            tool_name=row["tool_name"], status=row["status"], severity=row["severity"],
            message=row["message"], details=_load(row["details_json"]),
            created_at=row["created_at"],
        )

    def list_validation_results(self, artifact_version_id: str = "",
                                tool_name: str = "") -> list[ValidationResult]:
        sql = "SELECT * FROM validation_results"
        params: list = []
        if artifact_version_id:
            sql += " WHERE artifact_version_id=?"
            params.append(artifact_version_id)
        if tool_name:
            sql += (" AND" if artifact_version_id else " WHERE") + " tool_name=?"
            params.append(tool_name)
        sql += " ORDER BY created_at, id"
        out: list[ValidationResult] = []
        for row in self._conn.execute(sql, params).fetchall():
            out.append(ValidationResult(
                id=row["id"], artifact_version_id=row["artifact_version_id"],
                tool_name=row["tool_name"], status=row["status"], severity=row["severity"],
                message=row["message"], details=_load(row["details_json"]),
                created_at=row["created_at"],
            ))
        return out

    # ------------------------------------------------------------------ #
    # answer audit
    # ------------------------------------------------------------------ #

    def record_answer_audit(self, question: str, answer: str = "",
                            request_id: str = "", conversation_id: str = "",
                            message_id: str = "", answerability_status: str = "",
                            project_id: str = "", scope: dict | None = None,
                            citations: list[dict] | None = None,
                            tool_calls: list[dict] | None = None,
                            model_provider: str = "", model_name: str = "",
                            routing_reason: str = "", latency_ms: int = 0,
                            audit_id: str = "") -> AnswerAudit:
        aid = audit_id or _id("aud")
        self._conn.execute(
            "INSERT INTO answer_audits(id, request_id, conversation_id, message_id, question, answer,"
            " answerability_status, project_id, scope_json, citations_json, tool_calls_json,"
            " model_provider, model_name, routing_reason, latency_ms, created_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (aid, request_id, conversation_id, message_id, question, answer,
             answerability_status, project_id, _json(scope), _json(citations or []),
             _json(tool_calls or []), model_provider, model_name, routing_reason,
             latency_ms, _now()),
        )
        self._conn.commit()
        row = self._conn.execute("SELECT * FROM answer_audits WHERE id=?", (aid,)).fetchone()
        assert row is not None
        return AnswerAudit(
            id=row["id"], request_id=row["request_id"], conversation_id=row["conversation_id"],
            message_id=row["message_id"], question=row["question"], answer=row["answer"],
            answerability_status=row["answerability_status"], project_id=row["project_id"],
            scope=_load(row["scope_json"]), citations=_loads(row["citations_json"]),
            tool_calls=_loads(row["tool_calls_json"]),
            model_provider=row["model_provider"], model_name=row["model_name"],
            routing_reason=row["routing_reason"], latency_ms=row["latency_ms"] or 0,
            created_at=row["created_at"],
        )

    def list_answer_audits(self, conversation_id: str = "") -> list[AnswerAudit]:
        if conversation_id:
            rows = self._conn.execute(
                "SELECT * FROM answer_audits WHERE conversation_id=? ORDER BY created_at, id",
                (conversation_id,)).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM answer_audits ORDER BY created_at, id").fetchall()
        out: list[AnswerAudit] = []
        for row in rows:
            out.append(AnswerAudit(
                id=row["id"], request_id=row["request_id"],
                conversation_id=row["conversation_id"], message_id=row["message_id"],
                question=row["question"], answer=row["answer"],
                answerability_status=row["answerability_status"], project_id=row["project_id"],
                scope=_load(row["scope_json"]), citations=_loads(row["citations_json"]),
                tool_calls=_loads(row["tool_calls_json"]),
                model_provider=row["model_provider"], model_name=row["model_name"],
                routing_reason=row["routing_reason"], latency_ms=row["latency_ms"] or 0,
                created_at=row["created_at"],
            ))
        return out
