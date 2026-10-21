-- 003: source locations and citations.
-- A SourceLocation is an exact, addressable place inside one artifact version
-- (PDF page, ARXML qualified path, source symbol, test case, table row range).
-- A Citation points an answer claim at such a location.

CREATE TABLE IF NOT EXISTS source_locations (
    id                 TEXT PRIMARY KEY,
    artifact_version_id TEXT NOT NULL,
    locator_type       TEXT NOT NULL,   -- pdf_page|arxml_xpath|source_symbol|test_case|row_range|json_pointer
    locator            TEXT NOT NULL,
    page_start         INTEGER,
    page_end           INTEGER,
    section            TEXT NOT NULL DEFAULT '',
    line_start         INTEGER,
    line_end           INTEGER,
    release            TEXT NOT NULL DEFAULT '',
    module             TEXT NOT NULL DEFAULT '',
    snippet            TEXT NOT NULL DEFAULT '',
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_locations_version ON source_locations(artifact_version_id);

CREATE TABLE IF NOT EXISTS citations (
    id                  TEXT PRIMARY KEY,
    answer_id           TEXT NOT NULL DEFAULT '',
    conversation_id     TEXT NOT NULL DEFAULT '',
    message_id          TEXT NOT NULL DEFAULT '',
    source_location_id  TEXT NOT NULL,
    artifact_version_id TEXT NOT NULL DEFAULT '',
    label               TEXT NOT NULL DEFAULT '',
    claim               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_citations_answer ON citations(answer_id);
CREATE INDEX IF NOT EXISTS idx_citations_location ON citations(source_location_id);
