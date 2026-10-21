-- Requirements, test intelligence, trace links and findings (Phase 6).
--
-- The rule this migration encodes: a machine may *propose* a trace link, but
-- only a human can approve it. Every link therefore carries a review state,
-- and no table in this migration asserts compliance - it records the evidence
-- that is available for review.

CREATE TABLE IF NOT EXISTS requirements(
  id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  title TEXT DEFAULT '',
  revision TEXT DEFAULT '',
  status TEXT DEFAULT '',
  source TEXT DEFAULT '',
  parent_id TEXT DEFAULT '',
  verification_method TEXT DEFAULT '',
  module TEXT DEFAULT '',
  autosar_release TEXT DEFAULT '',
  artifact_version_id TEXT DEFAULT '',
  description TEXT DEFAULT '',
  properties_json TEXT DEFAULT '{}',
  review_state TEXT DEFAULT 'machine-extracted',
  created_at TEXT, updated_at TEXT);

CREATE INDEX IF NOT EXISTS idx_requirements_project ON requirements(project_id);
CREATE INDEX IF NOT EXISTS idx_requirements_parent ON requirements(parent_id);

CREATE TABLE IF NOT EXISTS requirement_versions(
  id TEXT PRIMARY KEY,
  requirement_id TEXT NOT NULL,
  revision TEXT DEFAULT '',
  status TEXT DEFAULT '',
  title TEXT DEFAULT '',
  changed_by TEXT DEFAULT '',
  change_note TEXT DEFAULT '',
  artifact_version_id TEXT DEFAULT '',
  source_location_id TEXT DEFAULT '',
  created_at TEXT);

CREATE INDEX IF NOT EXISTS idx_requirement_versions_requirement
  ON requirement_versions(requirement_id);

-- A trace link: requirement <-> test case (or any other entity).
CREATE TABLE IF NOT EXISTS trace_links(
  id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  target_type TEXT NOT NULL,
  target_id TEXT NOT NULL,
  link_type TEXT DEFAULT 'verifies',
  review_state TEXT DEFAULT 'proposed',
  confidence REAL DEFAULT 0.0,
  is_inferred INT DEFAULT 0,
  extraction_method TEXT DEFAULT '',
  artifact_version_id TEXT DEFAULT '',
  source_location_id TEXT DEFAULT '',
  reviewed_by TEXT DEFAULT '',
  review_note TEXT DEFAULT '',
  created_at TEXT, updated_at TEXT);

CREATE INDEX IF NOT EXISTS idx_trace_links_source ON trace_links(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_trace_links_target ON trace_links(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_trace_links_review ON trace_links(review_state);

CREATE TABLE IF NOT EXISTS test_cases(
  id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  suite TEXT DEFAULT '',
  name TEXT DEFAULT '',
  classname TEXT DEFAULT '',
  file_path TEXT DEFAULT '',
  line INT,
  parameters_json TEXT DEFAULT '{}',
  tags_json TEXT DEFAULT '[]',
  review_state TEXT DEFAULT 'machine-extracted',
  created_at TEXT, updated_at TEXT);

CREATE INDEX IF NOT EXISTS idx_test_cases_suite ON test_cases(suite);

CREATE TABLE IF NOT EXISTS test_runs(
  id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  suite TEXT DEFAULT '',
  started_at TEXT DEFAULT '',
  finished_at TEXT DEFAULT '',
  duration_ms INT DEFAULT 0,
  tool TEXT DEFAULT '',
  ci_run_id TEXT DEFAULT '',
  ci_url TEXT DEFAULT '',
  branch TEXT DEFAULT '',
  commit_sha TEXT DEFAULT '',
  artifact_version_id TEXT DEFAULT '',
  summary_json TEXT DEFAULT '{}',
  created_at TEXT);

CREATE INDEX IF NOT EXISTS idx_test_runs_suite ON test_runs(suite);

CREATE TABLE IF NOT EXISTS test_results(
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  test_case_id TEXT DEFAULT '',
  name TEXT DEFAULT '',
  classname TEXT DEFAULT '',
  status TEXT DEFAULT 'unknown',
  duration_ms INT DEFAULT 0,
  message TEXT DEFAULT '',
  stdout TEXT DEFAULT '',
  stderr TEXT DEFAULT '',
  artifact_version_id TEXT DEFAULT '',
  source_location_id TEXT DEFAULT '',
  created_at TEXT);

CREATE INDEX IF NOT EXISTS idx_test_results_run ON test_results(run_id);
CREATE INDEX IF NOT EXISTS idx_test_results_case ON test_results(test_case_id);
CREATE INDEX IF NOT EXISTS idx_test_results_status ON test_results(status);

CREATE TABLE IF NOT EXISTS findings(
  id TEXT PRIMARY KEY,
  project_id TEXT DEFAULT '',
  title TEXT DEFAULT '',
  severity TEXT DEFAULT 'info',
  status TEXT DEFAULT 'open',
  summary TEXT DEFAULT '',
  source_type TEXT DEFAULT '',
  source_id TEXT DEFAULT '',
  test_run_id TEXT DEFAULT '',
  test_result_id TEXT DEFAULT '',
  affected_configuration TEXT DEFAULT '',
  suspected_root_cause TEXT DEFAULT '',
  owner TEXT DEFAULT '',
  review_state TEXT DEFAULT 'open',
  evidence_json TEXT DEFAULT '[]',
  created_at TEXT, updated_at TEXT);

CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id);
CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status);
