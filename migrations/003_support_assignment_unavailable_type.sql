DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'external_support_workers'
  ) THEN
    ALTER TABLE external_support_workers
      DROP CONSTRAINT IF EXISTS chk_external_support_worker_type;
    ALTER TABLE external_support_workers
      ADD CONSTRAINT chk_external_support_worker_type
      CHECK (worker_type IN ('F', 'BK', 'INTERNAL', 'UNAVAILABLE'));
  END IF;
END
$$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'support_assignment'
  ) THEN
    ALTER TABLE support_assignment
      DROP CONSTRAINT IF EXISTS chk_support_assignment_worker_type;
    ALTER TABLE support_assignment
      ADD CONSTRAINT chk_support_assignment_worker_type
      CHECK (worker_type IN ('F', 'BK', 'INTERNAL', 'UNAVAILABLE'));
  END IF;
END
$$;
