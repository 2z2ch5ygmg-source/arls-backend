DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_mapping_profiles'
  ) THEN
    CREATE TABLE schedule_import_mapping_profiles (
      id uuid PRIMARY KEY,
      tenant_id uuid NOT NULL,
      profile_name text NOT NULL,
      is_active boolean NOT NULL DEFAULT true,
      created_by uuid,
      created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
      updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
    );
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_schedule_import_mapping_profiles_tenant
  ON schedule_import_mapping_profiles (tenant_id, is_active, updated_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_import_mapping_profiles_active
  ON schedule_import_mapping_profiles (tenant_id)
  WHERE is_active = TRUE;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_mapping_entries'
  ) THEN
    CREATE TABLE schedule_import_mapping_entries (
      id uuid PRIMARY KEY,
      profile_id uuid NOT NULL REFERENCES schedule_import_mapping_profiles(id) ON DELETE CASCADE,
      row_type text NOT NULL,
      numeric_hours numeric(5,2) NOT NULL,
      template_id uuid NOT NULL REFERENCES schedule_templates(id) ON DELETE RESTRICT,
      created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
      updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
      CONSTRAINT chk_schedule_import_mapping_entries_row_type
        CHECK (row_type IN ('day', 'overtime', 'night')),
      CONSTRAINT chk_schedule_import_mapping_entries_hours
        CHECK (numeric_hours >= 0 AND numeric_hours <= 24)
    );
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_import_mapping_entries_key
  ON schedule_import_mapping_entries (profile_id, row_type, numeric_hours);

CREATE INDEX IF NOT EXISTS idx_schedule_import_mapping_entries_template
  ON schedule_import_mapping_entries (template_id);
