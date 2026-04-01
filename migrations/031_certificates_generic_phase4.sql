DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'employees'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'employees'
        AND column_name = 'employment_status'
    ) THEN
      ALTER TABLE employees ADD COLUMN employment_status text NOT NULL DEFAULT 'active';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'employees'
        AND column_name = 'loa_start_date'
    ) THEN
      ALTER TABLE employees ADD COLUMN loa_start_date date;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'employees'
        AND column_name = 'loa_end_date'
    ) THEN
      ALTER TABLE employees ADD COLUMN loa_end_date date;
    END IF;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'certificate_requests'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'company_id'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN company_id uuid REFERENCES companies(id) ON DELETE SET NULL;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'submit_to'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN submit_to text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'copy_count'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN copy_count int NOT NULL DEFAULT 1;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'include_address'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN include_address boolean NOT NULL DEFAULT false;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'include_phone'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN include_phone boolean NOT NULL DEFAULT false;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'rejection_reason'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN rejection_reason text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'generation_error'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN generation_error text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'mail_error'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN mail_error text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'mail_company_sent_at'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN mail_company_sent_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'mail_employee_sent_at'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN mail_employee_sent_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'template_id'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN template_id uuid;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'template_version'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN template_version int;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'template_file_path'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN template_file_path text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'file_name'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN file_name text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'file_mime_type'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN file_mime_type text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'file_bytes'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN file_bytes bytea;
    END IF;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_certificate_requests_tenant_employee_requested
    ON certificate_requests (tenant_id, employee_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_certificate_requests_tenant_type_requested
    ON certificate_requests (tenant_id, certificate_type_id, requested_at DESC);
