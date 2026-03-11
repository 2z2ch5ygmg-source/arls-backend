DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_templates'
  ) THEN
    CREATE TABLE schedule_templates (
      id uuid PRIMARY KEY,
      tenant_id uuid NOT NULL,
      template_name text NOT NULL,
      duty_type text NOT NULL,
      start_time time,
      end_time time,
      paid_hours numeric(5,2),
      break_minutes int,
      site_id uuid,
      is_default boolean NOT NULL DEFAULT false,
      is_active boolean NOT NULL DEFAULT true,
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
      updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
      CONSTRAINT chk_schedule_templates_duty_type CHECK (duty_type IN ('day', 'overtime', 'night')),
      CONSTRAINT chk_schedule_templates_paid_hours CHECK (paid_hours IS NULL OR (paid_hours >= 0 AND paid_hours <= 24)),
      CONSTRAINT chk_schedule_templates_break_minutes CHECK (break_minutes IS NULL OR (break_minutes >= 0 AND break_minutes <= 1440))
    );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_schedule_templates_tenant_active
  ON schedule_templates (tenant_id, is_active, duty_type, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_schedule_templates_tenant_site_active
  ON schedule_templates (tenant_id, site_id, is_active, duty_type, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_templates_tenant_site_name
  ON schedule_templates (tenant_id, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(template_name));

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_templates_default_scope
  ON schedule_templates (tenant_id, COALESCE(site_id, '00000000-0000-0000-0000-000000000000'::uuid), duty_type)
  WHERE is_default = TRUE AND is_active = TRUE;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS template_id uuid;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS shift_start_time time;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS shift_end_time time;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS paid_hours numeric(5,2);

    CREATE INDEX IF NOT EXISTS idx_monthly_schedules_tenant_date_template
      ON monthly_schedules (tenant_id, schedule_date, template_id);
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
      ADD COLUMN IF NOT EXISTS employee_name text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS duty_type text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS template_id uuid;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS template_name text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS work_value text;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS shift_start_time time;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS shift_end_time time;
    ALTER TABLE schedule_import_rows
      ADD COLUMN IF NOT EXISTS paid_hours numeric(5,2);
  END IF;
END
$$;
