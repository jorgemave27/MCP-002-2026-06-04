PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS adrs (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DRAFT','ACCEPTED','DEPRECATED')),
  context TEXT NOT NULL,
  decision TEXT NOT NULL,
  consequences TEXT NOT NULL,
  options_json TEXT NOT NULL,
  tags_json TEXT NOT NULL DEFAULT '[]',
  supersedes TEXT REFERENCES adrs(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  author TEXT,
  embedding_model TEXT
);

CREATE TABLE IF NOT EXISTS adr_embeddings (
  adr_id TEXT PRIMARY KEY REFERENCES adrs(id) ON DELETE CASCADE,
  embedding_json TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS adr_audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  adr_id TEXT NOT NULL REFERENCES adrs(id),
  event_type TEXT NOT NULL,
  payload TEXT,
  timestamp TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS adr_audit_log_no_update
BEFORE UPDATE ON adr_audit_log
BEGIN
  SELECT RAISE(ABORT, 'adr_audit_log is append-only: UPDATE is not allowed');
END;

CREATE TRIGGER IF NOT EXISTS adr_audit_log_no_delete
BEFORE DELETE ON adr_audit_log
BEGIN
  SELECT RAISE(ABORT, 'adr_audit_log is append-only: DELETE is not allowed');
END;

CREATE INDEX IF NOT EXISTS idx_adrs_project_status ON adrs(project_id, status);
CREATE INDEX IF NOT EXISTS idx_adrs_status ON adrs(status);
CREATE INDEX IF NOT EXISTS idx_audit_adr_id ON adr_audit_log(adr_id);
