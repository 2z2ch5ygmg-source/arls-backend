CREATE TABLE IF NOT EXISTS schedule_finance_submission_states (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    state text NOT NULL DEFAULT 'review_download_ready',
    current_revision text,
    review_download_revision text,
    review_downloaded_at timestamptz,
    review_downloaded_by uuid,
    review_downloaded_role text,
    review_download_filename text,
    active_final_batch_id uuid,
    active_final_revision text,
    active_final_source_revision text,
    active_final_filename text,
    final_uploaded_at timestamptz,
    final_uploaded_by uuid,
    final_uploaded_role text,
    final_download_enabled boolean NOT NULL DEFAULT false,
    final_upload_stale boolean NOT NULL DEFAULT false,
    conflict_required boolean NOT NULL DEFAULT false,
    last_event text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_schedule_finance_submission_states UNIQUE (tenant_id, site_id, month_key)
);

CREATE INDEX IF NOT EXISTS idx_schedule_finance_submission_states_scope
  ON schedule_finance_submission_states (tenant_id, site_code, month_key);

CREATE TABLE IF NOT EXISTS schedule_finance_submission_batches (
    id uuid PRIMARY KEY,
    submission_id uuid NOT NULL REFERENCES schedule_finance_submission_states(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    batch_kind text NOT NULL,
    source_revision text NOT NULL,
    final_revision text,
    filename text,
    artifact_bytes bytea,
    import_batch_id uuid REFERENCES schedule_import_batches(id) ON DELETE SET NULL,
    actor_id uuid NOT NULL,
    actor_role text,
    status text NOT NULL DEFAULT 'created',
    is_stale boolean NOT NULL DEFAULT false,
    total_rows int NOT NULL DEFAULT 0,
    valid_rows int NOT NULL DEFAULT 0,
    invalid_rows int NOT NULL DEFAULT 0,
    applied_rows int NOT NULL DEFAULT 0,
    skipped_rows int NOT NULL DEFAULT 0,
    conflict_count int NOT NULL DEFAULT 0,
    blocked_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    diff_counts_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_schedule_finance_submission_batches_submission
  ON schedule_finance_submission_batches (submission_id, created_at DESC);

ALTER TABLE schedule_finance_submission_states
DROP CONSTRAINT IF EXISTS fk_schedule_finance_submission_active_final_batch;

ALTER TABLE schedule_finance_submission_states
ADD CONSTRAINT fk_schedule_finance_submission_active_final_batch
FOREIGN KEY (active_final_batch_id)
REFERENCES schedule_finance_submission_batches(id)
ON DELETE SET NULL;
