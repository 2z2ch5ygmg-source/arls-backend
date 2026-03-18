DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_mapping_entries'
      AND column_name = 'template_id'
  ) THEN
    ALTER TABLE schedule_import_mapping_entries
      ALTER COLUMN template_id DROP NOT NULL;

    ALTER TABLE schedule_import_mapping_entries
      DROP CONSTRAINT IF EXISTS schedule_import_mapping_entries_template_id_fkey;

    ALTER TABLE schedule_import_mapping_entries
      ADD CONSTRAINT schedule_import_mapping_entries_template_id_fkey
      FOREIGN KEY (template_id) REFERENCES schedule_templates(id) ON DELETE SET NULL;
  END IF;
END
$$;
