CREATE TABLE IF NOT EXISTS schedule_support_roundtrip_sources (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    source_batch_id uuid REFERENCES schedule_import_batches(id) ON DELETE SET NULL,
    source_revision text NOT NULL,
    source_filename text,
    source_uploaded_by uuid NOT NULL,
    source_uploaded_role text,
    source_uploaded_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    state text NOT NULL DEFAULT 'waiting_for_hq_merge',
    hq_merge_available boolean NOT NULL DEFAULT false,
    hq_merge_stale boolean NOT NULL DEFAULT false,
    conflict_required boolean NOT NULL DEFAULT false,
    final_download_enabled boolean NOT NULL DEFAULT false,
    latest_hq_batch_id uuid,
    latest_hq_revision text,
    latest_merged_revision text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_schedule_support_roundtrip_sources UNIQUE (tenant_id, site_id, month_key)
);

CREATE INDEX IF NOT EXISTS idx_schedule_support_roundtrip_sources_scope
  ON schedule_support_roundtrip_sources (tenant_id, site_code, month_key);

CREATE TABLE IF NOT EXISTS schedule_support_roundtrip_batches (
    id uuid PRIMARY KEY,
    source_id uuid NOT NULL REFERENCES schedule_support_roundtrip_sources(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    source_revision text NOT NULL,
    workbook_kind text NOT NULL,
    filename text,
    uploaded_by uuid NOT NULL,
    uploaded_role text,
    status text NOT NULL DEFAULT 'staged',
    template_version text,
    support_form_version text,
    is_stale boolean NOT NULL DEFAULT false,
    is_partial boolean NOT NULL DEFAULT false,
    total_rows int NOT NULL DEFAULT 0,
    meaningful_rows int NOT NULL DEFAULT 0,
    applied_rows int NOT NULL DEFAULT 0,
    ignored_blank_count int NOT NULL DEFAULT 0,
    internal_conversion_count int NOT NULL DEFAULT 0,
    conflict_count int NOT NULL DEFAULT 0,
    blocked_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    diff_counts_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    completed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_schedule_support_roundtrip_batches_source
  ON schedule_support_roundtrip_batches (source_id, created_at DESC);

CREATE TABLE IF NOT EXISTS schedule_support_roundtrip_rows (
    id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES schedule_support_roundtrip_batches(id) ON DELETE CASCADE,
    row_no int NOT NULL DEFAULT 0,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    schedule_date date NOT NULL,
    support_period text NOT NULL,
    slot_index int NOT NULL DEFAULT 1,
    source_block text NOT NULL,
    section_label text,
    workbook_value text,
    current_value text,
    resolved_worker_type text,
    resolved_worker_name text,
    employee_id uuid,
    employee_code text,
    employee_name text,
    apply_action text NOT NULL DEFAULT 'none',
    diff_category text NOT NULL DEFAULT 'unchanged',
    validation_code text,
    validation_error text,
    is_blocking boolean NOT NULL DEFAULT false,
    is_protected boolean NOT NULL DEFAULT false,
    protected_reason text,
    line_count int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_schedule_support_roundtrip_rows_batch
  ON schedule_support_roundtrip_rows (batch_id, schedule_date, support_period, slot_index);

CREATE TABLE IF NOT EXISTS schedule_support_roundtrip_assignments (
    id uuid PRIMARY KEY,
    source_id uuid NOT NULL REFERENCES schedule_support_roundtrip_sources(id) ON DELETE CASCADE,
    source_revision text NOT NULL,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    work_date date NOT NULL,
    support_period text NOT NULL,
    slot_index int NOT NULL DEFAULT 1,
    worker_type text NOT NULL,
    worker_name text NOT NULL,
    employee_id uuid,
    employee_code text,
    employee_name text,
    is_internal boolean NOT NULL DEFAULT false,
    internal_shift_type text,
    internal_template_id uuid,
    internal_shift_start_time text,
    internal_shift_end_time text,
    internal_paid_hours numeric(6,2),
    source_batch_id uuid REFERENCES schedule_support_roundtrip_batches(id) ON DELETE SET NULL,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_schedule_support_roundtrip_assignments UNIQUE (source_id, source_revision, work_date, support_period, slot_index)
);

CREATE INDEX IF NOT EXISTS idx_schedule_support_roundtrip_assignments_scope
  ON schedule_support_roundtrip_assignments (tenant_id, site_code, work_date, support_period, slot_index);
