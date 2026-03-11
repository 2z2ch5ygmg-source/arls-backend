DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'attendance_records'
  ) THEN
    CREATE INDEX IF NOT EXISTS idx_attendance_records_tenant_event_at
      ON attendance_records (tenant_id, event_at DESC);

    CREATE INDEX IF NOT EXISTS idx_attendance_records_tenant_employee_event_at
      ON attendance_records (tenant_id, employee_id, event_at DESC);

    CREATE INDEX IF NOT EXISTS idx_attendance_records_tenant_employee_event_type_event_at
      ON attendance_records (tenant_id, employee_id, event_type, event_at DESC);
  END IF;
END $$;
