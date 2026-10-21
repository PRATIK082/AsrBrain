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

    Real handlers (artifact ingestion, ARXML extraction, embedding) arrive in
    Phase 3. This one exists so the queue path is exercisable end to end.
    """
    return {"ok": True, "kind": job.kind, "echo": True}


HANDLERS: dict[str, Callable[[Job], dict]] = {
    "echo": _echo_handler,
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
