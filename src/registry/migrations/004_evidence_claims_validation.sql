-- 004: evidence claims and validation results.
-- An EvidenceClaim is one material statement of an answer plus its gate status.
-- A ValidationResult is the deterministic output of a tool (validate_arxml,
-- diff_arxml_versions, …) that ran against one artifact version.

CREATE TABLE IF NOT EXISTS evidence_claims (
    id          TEXT PRIMARY KEY,
    answer_id   TEXT NOT NULL DEFAULT '',
    claim       TEXT NOT NULL,
    claim_type  TEXT NOT NULL DEFAULT 'fact',  -- fact|interpretation|assumption|recommendation
    status      TEXT NOT NULL DEFAULT 'EVIDENCE_SUPPORTED',
    reason      TEXT NOT NULL DEFAULT '',
    citation_ids TEXT NOT NULL DEFAULT '[]',
    missing     TEXT NOT NULL DEFAULT '[]',
    conflicts   TEXT NOT NULL DEFAULT '[]',
    checked     TEXT NOT NULL DEFAULT '[]',
    confidence  REAL NOT NULL DEFAULT 0.0,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evidence_claims_answer ON evidence_claims(answer_id);
CREATE INDEX IF NOT EXISTS idx_evidence_claims_status ON evidence_claims(status);

CREATE TABLE IF NOT EXISTS validation_results (
    id                 TEXT PRIMARY KEY,
    artifact_version_id TEXT NOT NULL,
    tool_name          TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'unknown',  -- passed|failed|warning|skipped
    severity           TEXT NOT NULL DEFAULT 'info',     -- info|warning|high|critical
    message            TEXT NOT NULL DEFAULT '',
    details_json       TEXT NOT NULL DEFAULT '{}',
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_validation_results_version ON validation_results(artifact_version_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_tool ON validation_results(tool_name);
