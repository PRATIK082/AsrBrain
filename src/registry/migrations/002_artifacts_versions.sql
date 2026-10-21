-- 002: artifact registry and immutable artifact versions.
-- An artifact is the logical thing ("the Com spec"); a version is one concrete
-- ingested state of it. Citations and claims always bind to a *version*.

CREATE TABLE IF NOT EXISTS artifacts (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    workspace_id        TEXT NOT NULL DEFAULT '',
    kind                TEXT NOT NULL,          -- spec|arxml|source|requirement_set|test_report|diagram|external
    name                TEXT NOT NULL,
    source_uri          TEXT NOT NULL DEFAULT '',
    content_hash        TEXT NOT NULL DEFAULT '',
    owner               TEXT NOT NULL DEFAULT '',
    branch              TEXT NOT NULL DEFAULT '',
    autosar_release     TEXT NOT NULL DEFAULT '',
    data_classification TEXT NOT NULL DEFAULT 'internal',
    access_policy       TEXT NOT NULL DEFAULT '{}',
    lifecycle_state     TEXT NOT NULL DEFAULT 'active',  -- draft|active|superseded|deleted
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_project ON artifacts(project_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_hash ON artifacts(content_hash);
CREATE INDEX IF NOT EXISTS idx_artifacts_kind ON artifacts(kind);

CREATE TABLE IF NOT EXISTS artifact_versions (
    id                    TEXT PRIMARY KEY,
    artifact_id           TEXT NOT NULL,
    version_label         TEXT NOT NULL DEFAULT '',
    content_hash          TEXT NOT NULL DEFAULT '',
    size_bytes            INTEGER NOT NULL DEFAULT 0,
    storage_uri           TEXT NOT NULL DEFAULT '',
    source_uri            TEXT NOT NULL DEFAULT '',
    extracted_at          TEXT NOT NULL,
    extractor_name        TEXT NOT NULL DEFAULT '',
    extractor_version     TEXT NOT NULL DEFAULT '',
    extraction_confidence REAL NOT NULL DEFAULT 1.0,
    metadata_json         TEXT NOT NULL DEFAULT '{}',
    lifecycle_state       TEXT NOT NULL DEFAULT 'active',
    created_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifact_versions_artifact ON artifact_versions(artifact_id);
CREATE INDEX IF NOT EXISTS idx_artifact_versions_hash ON artifact_versions(content_hash);
