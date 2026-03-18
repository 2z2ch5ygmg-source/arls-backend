ALTER TABLE support_assignment
    ADD COLUMN IF NOT EXISTS support_period text NOT NULL DEFAULT 'day',
    ADD COLUMN IF NOT EXISTS slot_index int NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS affiliation text,
    ADD COLUMN IF NOT EXISTS source_ticket_id bigint,
    ADD COLUMN IF NOT EXISTS source_event_uid text,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT timezone('utc', now());

UPDATE support_assignment
SET support_period = COALESCE(NULLIF(support_period, ''), 'day'),
    slot_index = COALESCE(slot_index, 1),
    updated_at = COALESCE(updated_at, created_at, timezone('utc', now()))
WHERE support_period IS NULL
   OR support_period = ''
   OR slot_index IS NULL
   OR updated_at IS NULL;

WITH normalized_slots AS (
  SELECT
    id,
    row_number() OVER (
      PARTITION BY tenant_id, site_id, work_date, support_period
      ORDER BY COALESCE(updated_at, created_at, timezone('utc', now())), id
    ) AS normalized_slot_index
  FROM support_assignment
)
UPDATE support_assignment sa
SET slot_index = normalized_slots.normalized_slot_index
FROM normalized_slots
WHERE sa.id = normalized_slots.id
  AND sa.slot_index IS DISTINCT FROM normalized_slots.normalized_slot_index;

ALTER TABLE support_assignment
    DROP CONSTRAINT IF EXISTS chk_support_assignment_worker_type;

ALTER TABLE support_assignment
    ADD CONSTRAINT chk_support_assignment_worker_type
        CHECK (worker_type IN ('F', 'BK', 'INTERNAL', 'UNAVAILABLE'));

ALTER TABLE support_assignment
    DROP CONSTRAINT IF EXISTS chk_support_assignment_support_period;

ALTER TABLE support_assignment
    ADD CONSTRAINT chk_support_assignment_support_period
        CHECK (support_period IN ('day', 'night'));

ALTER TABLE support_assignment
    DROP CONSTRAINT IF EXISTS chk_support_assignment_slot_index;

ALTER TABLE support_assignment
    ADD CONSTRAINT chk_support_assignment_slot_index
        CHECK (slot_index >= 1);

DROP INDEX IF EXISTS uq_support_assignment_tenant_site_date_name;
DROP INDEX IF EXISTS uq_support_assignment_tenant_site_date_period_name;

CREATE UNIQUE INDEX IF NOT EXISTS uq_support_assignment_tenant_site_date_period_slot
    ON support_assignment (tenant_id, site_id, work_date, support_period, slot_index);

CREATE INDEX IF NOT EXISTS idx_support_assignment_tenant_site_date_period_name
    ON support_assignment (tenant_id, site_id, work_date, support_period, lower(name));

CREATE INDEX IF NOT EXISTS idx_support_assignment_source_ticket
    ON support_assignment (tenant_id, source_ticket_id, work_date DESC);

CREATE INDEX IF NOT EXISTS idx_support_assignment_source_event
    ON support_assignment (source_event_uid);
