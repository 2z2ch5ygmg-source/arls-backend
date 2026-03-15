CREATE TABLE IF NOT EXISTS sentrix_support_hq_roster_batches (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    month_key text NOT NULL,
    download_scope text NOT NULL,
    selected_site_code text,
    filename text,
    workbook_family text,
    template_version text,
    bundle_revision text,
    latest_status text NOT NULL DEFAULT 'unknown',
    status text NOT NULL DEFAULT 'previewed',
    uploaded_by uuid NOT NULL,
    uploaded_role text,
    issue_count int NOT NULL DEFAULT 0,
    blocking_issue_count int NOT NULL DEFAULT 0,
    total_scope_count int NOT NULL DEFAULT 0,
    valid_scope_count int NOT NULL DEFAULT 0,
    upload_meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    completed_at timestamptz,
    CONSTRAINT chk_sentrix_support_hq_roster_batches_scope
      CHECK (download_scope IN ('all', 'site', 'selected')),
    CONSTRAINT chk_sentrix_support_hq_roster_batches_status
      CHECK (status IN ('previewed', 'applied', 'blocked', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_hq_roster_batches_scope
  ON sentrix_support_hq_roster_batches (tenant_id, month_key, created_at DESC);

CREATE TABLE IF NOT EXISTS sentrix_support_hq_roster_rows (
    id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    sheet_name text NOT NULL,
    site_id uuid,
    site_code text,
    site_name text,
    work_date date,
    shift_kind text,
    slot_index int NOT NULL DEFAULT 0,
    row_kind text NOT NULL DEFAULT 'worker',
    status text NOT NULL DEFAULT 'pending',
    severity text,
    issue_code text,
    ticket_id uuid,
    raw_cell_text text,
    parsed_display_value text,
    effect_text text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sentrix_support_hq_roster_rows_shift_kind
      CHECK (shift_kind IS NULL OR shift_kind IN ('day', 'night')),
    CONSTRAINT chk_sentrix_support_hq_roster_rows_slot_index
      CHECK (slot_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_hq_roster_rows_batch
  ON sentrix_support_hq_roster_rows (batch_id, site_code, work_date, shift_kind, slot_index);
