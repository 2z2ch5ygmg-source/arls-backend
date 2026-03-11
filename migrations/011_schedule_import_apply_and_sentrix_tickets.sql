DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_batches'
  ) THEN
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS issues_json jsonb NOT NULL DEFAULT '[]'::jsonb;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS mapping_profile_id uuid;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS mapping_profile_name text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS mapping_profile_updated_at timestamptz;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS apply_result_json jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS applied_by uuid;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS applied_role text;
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
      ADD COLUMN IF NOT EXISTS payload_json jsonb NOT NULL DEFAULT '{}'::jsonb;
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_batch_id uuid;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_revision text;
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'site_daytime_need_counts'
  ) THEN
    ALTER TABLE site_daytime_need_counts
      ADD COLUMN IF NOT EXISTS source_batch_id uuid;
    ALTER TABLE site_daytime_need_counts
      ADD COLUMN IF NOT EXISTS source_revision text;
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS sentrix_support_request_tickets (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    site_code text NOT NULL,
    month_key text NOT NULL,
    work_date date NOT NULL,
    shift_kind text NOT NULL,
    request_count int NOT NULL DEFAULT 0 CHECK (request_count >= 0 AND request_count <= 300),
    work_purpose text,
    status text NOT NULL DEFAULT 'active',
    source_workflow text NOT NULL DEFAULT 'arls_monthly_base_upload',
    source_batch_id uuid REFERENCES schedule_import_batches(id) ON DELETE SET NULL,
    source_revision text,
    detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    retracted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sentrix_support_request_tickets_shift_kind CHECK (shift_kind IN ('day', 'night')),
    CONSTRAINT chk_sentrix_support_request_tickets_status CHECK (status IN ('active', 'retracted'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_request_tickets_scope
  ON sentrix_support_request_tickets (tenant_id, site_id, work_date, shift_kind, source_workflow);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_request_tickets_month
  ON sentrix_support_request_tickets (tenant_id, site_id, month_key, work_date DESC);
