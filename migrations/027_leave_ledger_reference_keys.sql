DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'leave_ledger'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'leave_ledger'
        AND column_name = 'reference_key'
    ) THEN
      ALTER TABLE leave_ledger ADD COLUMN reference_key text;
    END IF;
  END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_leave_grants_tenant_employee_reference
    ON leave_grants (tenant_id, employee_id, reference_key)
    WHERE reference_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_leave_ledger_tenant_employee_reference
    ON leave_ledger (tenant_id, employee_id, reference_key)
    WHERE reference_key IS NOT NULL;
