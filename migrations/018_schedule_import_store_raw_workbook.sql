DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_batches'
  ) THEN
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_bytes bytea;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_mime_type text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_sha256 text;
  END IF;
END $$;
