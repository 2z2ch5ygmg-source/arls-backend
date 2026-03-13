-- Allow monthly base uploads to materialize overtime rows.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    ALTER TABLE monthly_schedules
      DROP CONSTRAINT IF EXISTS monthly_schedules_shift_type_check;

    ALTER TABLE monthly_schedules
      ADD CONSTRAINT monthly_schedules_shift_type_check
      CHECK (
        lower(COALESCE(NULLIF(trim(shift_type), ''), 'day')) IN ('day', 'overtime', 'night', 'off', 'holiday')
      );
  END IF;
END
$$;
