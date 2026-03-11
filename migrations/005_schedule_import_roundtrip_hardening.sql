DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_batches'
  ) THEN
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS import_mode text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS site_id uuid;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS site_code text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS month_key text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS template_version text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS export_source_version text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS export_revision text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS current_revision text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS metadata_error text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS blocked_reasons_json jsonb NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS diff_counts_json jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS is_stale boolean NOT NULL DEFAULT false;
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_rows'
  ) THEN
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS validation_code text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS source_block text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS section_label text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS current_work_value text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS diff_category text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS apply_action text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS is_blocking boolean NOT NULL DEFAULT false;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS is_protected boolean NOT NULL DEFAULT false;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS protected_reason text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS current_schedule_id uuid;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_schedule_import_batches_scope
  ON schedule_import_batches (tenant_id, site_code, month_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedule_import_rows_batch_apply
  ON schedule_import_rows (batch_id, is_blocking, apply_action, row_no);

CREATE TABLE IF NOT EXISTS site_daytime_need_counts (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    required_count int NOT NULL DEFAULT 0 CHECK (required_count >= 0 AND required_count <= 300),
    raw_text text,
    source text NOT NULL DEFAULT 'monthly_workbook',
    updated_by uuid,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_site_daytime_need_counts UNIQUE (tenant_id, site_id, work_date)
);

CREATE INDEX IF NOT EXISTS idx_site_daytime_need_counts_tenant_site_date
  ON site_daytime_need_counts (tenant_id, site_id, work_date DESC);
