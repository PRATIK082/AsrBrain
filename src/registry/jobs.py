"""Background job framework (Phase 2).

A job is a durable row in the registry. The API enqueues, a worker process
claims, runs and reports. Claiming is atomic: the row is moved from `queued`
to `running` inside a single transaction, so two workers cannot take the same
job. A job that dies is retried up to `max_attempts` and then marked `failed`
with the error recorded — nothing fails silently.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from .db import connect, default_registry_db
from .migrator import apply_migrations
from .models import Job


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _id() -> str:
    return f"job-{uuid.uuid4().hex[:12]}"


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True)


def _load(value: Any) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return {}


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"], kind=row["kind"], payload=_load(row["payload_json"]),
        status=row["status"], priority=row["priority"] or 0, attempts=row["attempts"] or 0,
        max_attempts=row["max_attempts"] or 0, project_id=row["project_id"] or "",
        workspace_id=row["workspace_id"] or "",
        artifact_version_id=row["artifact_version_id"] or "",
        error=row["error"] or "", result=_load(row["result_json"]),
        created_at=row["created_at"], updated_at=row["updated_at"],
        started_at=row["started_at"] or "", finished_at=row["finished_at"] or "",
    )


class JobStore:
    """Durable job queue backed by the registry database."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or default_registry_db()
        apply_migrations(self.db_path)
        self._conn = connect(self.db_path)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def enqueue(self, kind: str, payload: dict | None = None, priority: int = 0,
                max_attempts: int = 3, project_id: str = "", workspace_id: str = "",
                artifact_version_id: str = "", job_id: str = "") -> Job:
        jid = job_id or _id()
        ts = _now()
        self._conn.execute(
            "INSERT INTO jobs(id, kind, payload_json, status, priority, attempts, max_attempts,"
            " project_id, workspace_id, artifact_version_id, error, result_json,"
            " created_at, updated_at, started_at, finished_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (jid, kind, _json(payload), "queued", priority, 0, max_attempts, project_id,
             workspace_id, artifact_version_id, "", _json({}), ts, ts, "", ""),
        )
        self._conn.commit()
        job = self.get(jid)
        assert job is not None
        return job

    def get(self, job_id: str) -> Job | None:
        row = self._conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return _row_to_job(row) if row is not None else None

    def list(self, status: str = "", kind: str = "", limit: int = 100) -> list[Job]:
        sql = "SELECT * FROM jobs"
        params: list = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        if kind:
            sql += (" AND" if status else " WHERE") + " kind=?"
            params.append(kind)
        sql += " ORDER BY created_at, id LIMIT ?"
        params.append(int(limit))
        return [_row_to_job(r) for r in self._conn.execute(sql, params).fetchall()]

    def claim_next(self, kinds: list[str] | None = None) -> Job | None:
        """Atomically take the next queued job. Returns None when the queue is empty."""
        sql = "SELECT * FROM jobs WHERE status='queued'"
        params: list = []
        if kinds:
            sql += " AND kind IN (" + ",".join("?" for _ in kinds) + ")"
            params.extend(kinds)
        sql += " ORDER BY priority DESC, created_at, id LIMIT 1"
        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            return None
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            cur = self._conn.execute(
                "UPDATE jobs SET status='running', attempts=attempts+1, started_at=?, updated_at=?"
                " WHERE id=? AND status='queued'",
                (_now(), _now(), row["id"]),
            )
            if cur.rowcount != 1:
                self._conn.rollback()
                return None
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return self.get(row["id"])

    def complete(self, job_id: str, result: dict | None = None) -> Job | None:
        self._conn.execute(
            "UPDATE jobs SET status='succeeded', result_json=?, error='', finished_at=?, updated_at=?"
            " WHERE id=?", (_json(result), _now(), _now(), job_id))
        self._conn.commit()
        return self.get(job_id)

    def fail(self, job_id: str, error: str) -> Job | None:
        """Record a failure; requeue while attempts remain, otherwise mark it failed."""
        job = self.get(job_id)
        if job is None:
            return None
        if job.attempts < job.max_attempts:
            self._conn.execute(
                "UPDATE jobs SET status='queued', error=?, finished_at='', updated_at=? WHERE id=?",
                (error, _now(), job_id))
        else:
            self._conn.execute(
                "UPDATE jobs SET status='failed', error=?, finished_at=?, updated_at=? WHERE id=?",
                (error, _now(), _now(), job_id))
        self._conn.commit()
        return self.get(job_id)

    def cancel(self, job_id: str) -> Job | None:
        self._conn.execute(
            "UPDATE jobs SET status='cancelled', finished_at=?, updated_at=? WHERE id=?",
            (_now(), _now(), job_id))
        self._conn.commit()
        return self.get(job_id)

    def counts(self) -> dict:
        rows = self._conn.execute(
            "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}


# --------------------------------------------------------------------------- #
# worker
# --------------------------------------------------------------------------- #

Handler = Callable[[Job], dict]


def run_worker(handlers: dict[str, Handler], db_path: str | None = None,
               poll_interval_s: float = 1.0, max_iterations: int = 0,
               sleep: Callable[[float], None] = __import__("time").sleep) -> int:
    """Run the worker loop.

    `max_iterations` bounds the loop (used by tests); 0 means run forever.
    Returns the number of jobs processed.
    """
    store = JobStore(db_path)
    processed = 0
    iterations = 0
    while max_iterations <= 0 or iterations < max_iterations:
        iterations += 1
        job = store.claim_next()
        if job is None:
            if max_iterations > 0:
                break
            sleep(poll_interval_s)
            continue
        handler = handlers.get(job.kind)
        if handler is None:
            store.fail(job.id, f"no handler registered for job kind '{job.kind}'")
        else:
            try:
                result = handler(job)
                store.complete(job.id, result if isinstance(result, dict) else {"result": result})
            except Exception as exc:  # a failing job must not kill the worker
                store.fail(job.id, f"{type(exc).__name__}: {exc}")
        processed += 1
    store.close()
    return processed
