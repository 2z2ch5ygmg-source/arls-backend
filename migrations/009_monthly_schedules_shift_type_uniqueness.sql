DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    UPDATE monthly_schedules
    SET shift_type = lower(COALESCE(NULLIF(trim(shift_type), ''), 'day'))
    WHERE COALESCE(NULLIF(trim(shift_type), ''), 'day')
          IS DISTINCT FROM lower(COALESCE(NULLIF(trim(shift_type), ''), 'day'));

    DELETE FROM monthly_schedules older
    USING monthly_schedules newer
    WHERE older.id <> newer.id
      AND older.tenant_id = newer.tenant_id
      AND older.employee_id = newer.employee_id
      AND older.schedule_date = newer.schedule_date
      AND lower(COALESCE(NULLIF(trim(older.shift_type), ''), 'day'))
          = lower(COALESCE(NULLIF(trim(newer.shift_type), ''), 'day'))
      AND older.id::text < newer.id::text;

    ALTER TABLE monthly_schedules
      DROP CONSTRAINT IF EXISTS monthly_schedules_tenant_id_employee_id_schedule_date_key;

    DROP INDEX IF EXISTS monthly_schedules_tenant_id_employee_id_schedule_date_key;

    CREATE UNIQUE INDEX IF NOT EXISTS uq_monthly_schedules_tenant_employee_date_shift_type
      ON monthly_schedules (
        tenant_id,
        employee_id,
        schedule_date,
        lower(COALESCE(NULLIF(trim(shift_type), ''), 'day'))
      );
  END IF;
END
$$;
