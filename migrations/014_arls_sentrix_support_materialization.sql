DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_ticket_uuid uuid;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_ticket_state text;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_action text;
    ALTER TABLE monthly_schedules
      ADD COLUMN IF NOT EXISTS source_self_staff boolean NOT NULL DEFAULT FALSE;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_monthly_schedules_sentrix_support_lineage
  ON monthly_schedules (
    tenant_id,
    source_ticket_uuid,
    employee_id,
    schedule_date,
    lower(COALESCE(NULLIF(trim(shift_type), ''), 'day'))
  )
  WHERE COALESCE(source, '') = 'sentrix_support_ticket';

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'sentrix_support_arls_bridge_actions'
  ) THEN
    ALTER TABLE sentrix_support_arls_bridge_actions
      ADD COLUMN IF NOT EXISTS result_json jsonb NOT NULL DEFAULT '{}'::jsonb;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_sentrix_support_arls_bridge_actions_batch_status
  ON sentrix_support_arls_bridge_actions (tenant_id, batch_id, status, created_at ASC);

CREATE TABLE IF NOT EXISTS sentrix_support_schedule_materializations (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    ticket_id uuid NOT NULL REFERENCES sentrix_support_request_tickets(id) ON DELETE CASCADE,
    bridge_action_id uuid REFERENCES sentrix_support_arls_bridge_actions(id) ON DELETE SET NULL,
    batch_id uuid REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE SET NULL,
    snapshot_id uuid REFERENCES sentrix_support_roster_snapshots(id) ON DELETE SET NULL,
    site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_code text NOT NULL,
    work_date date NOT NULL,
    shift_kind text NOT NULL,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    employee_code text,
    employee_name text,
    self_staff boolean NOT NULL DEFAULT TRUE,
    monthly_schedule_id uuid REFERENCES monthly_schedules(id) ON DELETE SET NULL,
    coexistence_mode text NOT NULL DEFAULT 'owned_schedule',
    status text NOT NULL DEFAULT 'active',
    ticket_state text NOT NULL,
    source text NOT NULL DEFAULT 'sentrix_support_ticket',
    source_action text NOT NULL,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    result_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_text text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    retracted_at timestamptz,
    CONSTRAINT chk_sentrix_support_schedule_materializations_shift_kind
      CHECK (shift_kind IN ('day', 'night')),
    CONSTRAINT chk_sentrix_support_schedule_materializations_status
      CHECK (status IN ('active', 'retracted')),
    CONSTRAINT chk_sentrix_support_schedule_materializations_mode
      CHECK (coexistence_mode IN ('owned_schedule', 'linked_existing_schedule')),
    CONSTRAINT chk_sentrix_support_schedule_materializations_action
      CHECK (source_action IN ('UPSERT', 'RETRACT'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_schedule_materializations_scope
  ON sentrix_support_schedule_materializations (
    tenant_id,
    ticket_id,
    site_id,
    work_date,
    shift_kind,
    employee_id
  );

CREATE INDEX IF NOT EXISTS idx_sentrix_support_schedule_materializations_active
  ON sentrix_support_schedule_materializations (
    tenant_id,
    site_id,
    work_date,
    shift_kind,
    status
  );
