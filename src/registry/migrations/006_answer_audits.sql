-- 006: answer audit trail.
-- Every answer that leaves the API is recorded here: the question, the answer,
-- its gate status, the scope it was computed under, the citations it used, the
-- deterministic tools that ran and the model that was asked (if any).

CREATE TABLE IF NOT EXISTS answer_audits (
    id                 TEXT PRIMARY KEY,
    request_id         TEXT NOT NULL DEFAULT '',
    conversation_id    TEXT NOT NULL DEFAULT '',
    message_id         TEXT NOT NULL DEFAULT '',
    question           TEXT NOT NULL DEFAULT '',
    answer             TEXT NOT NULL DEFAULT '',
    answerability_status TEXT NOT NULL DEFAULT '',
    project_id         TEXT NOT NULL DEFAULT '',
    scope_json         TEXT NOT NULL DEFAULT '{}',
    citations_json     TEXT NOT NULL DEFAULT '[]',
    tool_calls_json    TEXT NOT NULL DEFAULT '[]',
    model_provider     TEXT NOT NULL DEFAULT '',
    model_name         TEXT NOT NULL DEFAULT '',
    routing_reason     TEXT NOT NULL DEFAULT '',
    latency_ms         INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_answer_audits_conversation ON answer_audits(conversation_id);
CREATE INDEX IF NOT EXISTS idx_answer_audits_status ON answer_audits(answerability_status);
CREATE INDEX IF NOT EXISTS idx_answer_audits_request ON answer_audits(request_id);
