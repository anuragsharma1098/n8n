-- Schema for the qa_metrics database used by the QA Quality Gate workflows.
-- Safe to run repeatedly: every statement is idempotent.

CREATE TABLE IF NOT EXISTS test_runs (
    id          BIGSERIAL PRIMARY KEY,
    project     TEXT        NOT NULL,
    branch      TEXT        NOT NULL,
    commit_sha  TEXT,
    build_url   TEXT,
    total       INTEGER     NOT NULL,
    passed      INTEGER     NOT NULL,
    failed      INTEGER     NOT NULL,   -- failures and errors
    skipped     INTEGER     NOT NULL,
    duration_ms BIGINT      NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS test_runs_project_branch_idx ON test_runs (project, branch, id DESC);

CREATE TABLE IF NOT EXISTS test_results (
    id          BIGSERIAL PRIMARY KEY,
    run_id      BIGINT  NOT NULL REFERENCES test_runs (id) ON DELETE CASCADE,
    test_id     TEXT    NOT NULL,       -- "classname::name", stable across runs
    suite       TEXT,
    name        TEXT    NOT NULL,
    status      TEXT    NOT NULL CHECK (status IN ('passed', 'failed', 'error', 'skipped')),
    duration_ms INTEGER NOT NULL DEFAULT 0,
    message     TEXT,
    retried     BOOLEAN NOT NULL DEFAULT false  -- passed only after a rerun (e.g. Surefire flakyFailure)
);

CREATE INDEX IF NOT EXISTS test_results_run_idx ON test_results (run_id);
CREATE INDEX IF NOT EXISTS test_results_test_idx ON test_results (test_id, run_id);
