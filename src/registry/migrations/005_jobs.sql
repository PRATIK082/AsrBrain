-- 005: background jobs.
-- The queue lives in the registry database so it shares the transaction and
-- isolation guarantees of the evidence model. A PostgreSQL deployment can
-- replace the claim query with SELECT ... FOR UPDATE SKIP LOCKED (ADR-0010).

CREATE TABLE IF NOT EXISTS jobs (
    id                 TEXT PRIMARY KEY,
    kind               TEXT NOT NULL,
    payload_json       TEXT NOT NULL DEFAULT '{}',
    status             TEXT NOT NULL DEFAULT 'queued',  -- queued|running|succeeded|failed|cancelled
    priority           INTEGER NOT NULL DEFAULT 0,
    attempts           INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 3,
    project_id         TEXT NOT NULL DEFAULT '',
    workspace_id       TEXT NOT NULL DEFAULT '',
    artifact_version_id TEXT NOT NULL DEFAULT '',
    error              TEXT NOT NULL DEFAULT '',
    result_json        TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL,
    started_at         TEXT NOT NULL DEFAULT '',
    finished_at        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_kind ON jobs(kind);
