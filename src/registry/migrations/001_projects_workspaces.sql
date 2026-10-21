-- 001: projects and workspaces.
-- Portable DDL: TEXT primary keys, TEXT timestamps (ISO-8601), JSON kept as TEXT.
-- The PostgreSQL adapter can cast the JSON columns to JSONB without a schema rewrite.

CREATE TABLE IF NOT EXISTS projects (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT NOT NULL DEFAULT '',
    owner             TEXT NOT NULL DEFAULT '',
    data_classification TEXT NOT NULL DEFAULT 'internal',
    access_policy     TEXT NOT NULL DEFAULT '{}',
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workspaces (
    id            TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    scope         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(project_id);
