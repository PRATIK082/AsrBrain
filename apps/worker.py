"""Background worker for the provenance-first registry (Phase 2).

The worker claims queued jobs from the registry job table, dispatches them to a
registered handler and records the outcome. A failing job never kills the
worker: it is retried up to `max_attempts` and then marked `failed` with the
error preserved, so nothing fails silently.

Run it with:

    python -m apps.worker
    python apps/worker.py

Handlers are registered by kind. Until a later phase adds real handlers, the
built-in set is intentionally small — an unknown job kind is failed loudly
rather than silently ignored.
"""
from __future__ import annotations

import sys
from typing import Callable

from src.config.settings import settings
from src.registry.jobs import Job, JobStore, run_worker


def _echo_handler(job: Job) -> dict:
    """Default handler: records that the job was observed.

    This one exists so the queue path is exercisable end to end.
    """
    return {"ok": True, "kind": job.kind, "echo": True}


def _artifact_ingest_handler(job: Job) -> dict:
    """Register one source file in the provenance registry.

    The bytes go to the object store, the artifact and one immutable version
    are registered, and every indexed chunk of that file gets a source
    location so a citation can be bound to an exact passage.
    """
    from src.ingestion.registry_ingest import ingest_document
    from src.objects import default_object_store
    from src.registry import RegistryStore

    payload = job.payload or {}
    path = str(payload.get("path") or "")
    project_id = str(payload.get("project_id") or "")
    if not path or not project_id:
        raise ValueError("artifact.ingest requires 'path' and 'project_id'")

    registry = RegistryStore(settings.registry_db)
    try:
        result = ingest_document(
            registry,
            default_object_store(),
            path=path,
            project_id=project_id,
            name=str(payload.get("name") or ""),
            kind=str(payload.get("kind") or "spec"),
            canonical_db=str(payload.get("canonical_db") or settings.canonical_db),
            workspace_id=str(payload.get("workspace_id") or ""),
            owner=str(payload.get("owner") or ""),
            branch=str(payload.get("branch") or ""),
            autosar_release=str(payload.get("autosar_release") or ""),
            data_classification=str(payload.get("data_classification") or "internal"),
            version_label=str(payload.get("version_label") or ""),
        )
    finally:
        registry.close()
    return {"ok": True, **result}


HANDLERS: dict[str, Callable[[Job], dict]] = {
    "echo": _echo_handler,
    "artifact.ingest": _artifact_ingest_handler,
}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    db_path = settings.registry_db
    if argv:
        db_path = argv[0]
    max_iterations = settings.worker_max_iterations
    print(f"[worker] registry={db_path} poll={settings.worker_poll_interval_s}s "
          f"max_iterations={max_iterations or 'forever'}", flush=True)
    processed = run_worker(
        HANDLERS,
        db_path=db_path,
        poll_interval_s=settings.worker_poll_interval_s,
        max_iterations=max_iterations,
    )
    print(f"[worker] processed {processed} job(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
