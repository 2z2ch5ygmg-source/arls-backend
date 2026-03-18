CREATE TABLE IF NOT EXISTS schedule_finance_download_acks (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    actor_id uuid NOT NULL,
    actor_role text,
    download_scope text NOT NULL DEFAULT 'site',
    published_batch_id uuid REFERENCES schedule_finance_submission_batches(id) ON DELETE SET NULL,
    published_version text,
    seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_schedule_finance_download_acks_scope
      CHECK (download_scope IN ('site', 'selected'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_finance_download_acks_actor_site_month
  ON schedule_finance_download_acks (tenant_id, actor_id, site_id, month_key);

CREATE INDEX IF NOT EXISTS idx_schedule_finance_download_acks_scope
  ON schedule_finance_download_acks (tenant_id, month_key, actor_id, seen_at DESC);
