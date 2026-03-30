DO $$
BEGIN
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
        AND column_name = 'legacy_source_type'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN legacy_source_type text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'legacy_source_id'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN legacy_source_id text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'certificate_requests'
        AND column_name = 'issue_number'
    ) THEN
      ALTER TABLE certificate_requests ADD COLUMN issue_number text;
    END IF;
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_requests_tenant_legacy_source
    ON certificate_requests (tenant_id, legacy_source_type, legacy_source_id)
    WHERE legacy_source_type IS NOT NULL
      AND legacy_source_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_certificate_issue_jobs_request
    ON certificate_issue_jobs (certificate_request_id);
