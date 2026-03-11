CREATE TABLE IF NOT EXISTS in_app_notifications (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES arls_users(id) ON DELETE CASCADE,
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    category text NOT NULL DEFAULT 'info',
    message text NOT NULL,
    dedupe_key text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    read_at timestamptz,
    CONSTRAINT chk_in_app_notifications_category
      CHECK (category IN ('info', 'success', 'warn', 'error'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_in_app_notifications_dedupe
  ON in_app_notifications (tenant_id, user_id, dedupe_key)
  WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_in_app_notifications_user_created
  ON in_app_notifications (user_id, read_at, created_at DESC);

CREATE TABLE IF NOT EXISTS sentrix_support_roster_snapshots (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id uuid NOT NULL REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE CASCADE,
    ticket_id uuid NOT NULL REFERENCES sentrix_support_request_tickets(id) ON DELETE CASCADE,
    site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_code text NOT NULL,
    site_name text,
    month_key text NOT NULL,
    work_date date NOT NULL,
    shift_kind text NOT NULL,
    sheet_name text,
    previous_snapshot_id uuid REFERENCES sentrix_support_roster_snapshots(id) ON DELETE SET NULL,
    previous_ticket_state text,
    ticket_state text NOT NULL,
    request_count int NOT NULL DEFAULT 0,
    valid_filled_count int NOT NULL DEFAULT 0,
    invalid_filled_count int NOT NULL DEFAULT 0,
    changed boolean NOT NULL DEFAULT TRUE,
    is_current boolean NOT NULL DEFAULT TRUE,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sentrix_support_roster_snapshots_shift_kind
      CHECK (shift_kind IN ('day', 'night'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_roster_snapshots_current
  ON sentrix_support_roster_snapshots (tenant_id, ticket_id)
  WHERE is_current = TRUE;

CREATE INDEX IF NOT EXISTS idx_sentrix_support_roster_snapshots_batch
  ON sentrix_support_roster_snapshots (batch_id, site_code, work_date DESC, shift_kind);

CREATE TABLE IF NOT EXISTS sentrix_support_roster_snapshot_entries (
    id uuid PRIMARY KEY,
    snapshot_id uuid NOT NULL REFERENCES sentrix_support_roster_snapshots(id) ON DELETE CASCADE,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id uuid NOT NULL REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE CASCADE,
    ticket_id uuid NOT NULL REFERENCES sentrix_support_request_tickets(id) ON DELETE CASCADE,
    sheet_name text NOT NULL,
    site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_code text NOT NULL,
    site_name text,
    work_date date NOT NULL,
    shift_kind text NOT NULL,
    slot_index int NOT NULL DEFAULT 0,
    raw_cell_text text,
    normalized_affiliation text,
    normalized_name text,
    display_value text,
    self_staff boolean NOT NULL DEFAULT FALSE,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    employee_code text,
    employee_name text,
    worker_type text,
    validity_state text NOT NULL DEFAULT 'valid',
    issue_code text,
    upload_scope_key text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sentrix_support_roster_snapshot_entries_shift_kind
      CHECK (shift_kind IN ('day', 'night')),
    CONSTRAINT chk_sentrix_support_roster_snapshot_entries_validity
      CHECK (validity_state IN ('valid', 'invalid', 'ignored'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_roster_snapshot_entries_slot
  ON sentrix_support_roster_snapshot_entries (snapshot_id, slot_index);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_roster_snapshot_entries_ticket
  ON sentrix_support_roster_snapshot_entries (ticket_id, self_staff, employee_id);

CREATE TABLE IF NOT EXISTS sentrix_support_notification_audit (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id uuid NOT NULL REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE CASCADE,
    site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_code text NOT NULL,
    message text NOT NULL,
    dedupe_key text NOT NULL,
    toast_recipient_count int NOT NULL DEFAULT 0,
    push_target_count int NOT NULL DEFAULT 0,
    push_sent_count int NOT NULL DEFAULT 0,
    push_failed_count int NOT NULL DEFAULT 0,
    recipient_user_ids_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending',
    error_text text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sentrix_support_notification_audit_status
      CHECK (status IN ('pending', 'sent', 'partial_failed', 'failed', 'skipped'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_notification_audit_dedupe
  ON sentrix_support_notification_audit (tenant_id, dedupe_key);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_notification_audit_batch
  ON sentrix_support_notification_audit (batch_id, site_code, created_at DESC);

CREATE TABLE IF NOT EXISTS sentrix_support_arls_bridge_actions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    batch_id uuid NOT NULL REFERENCES sentrix_support_hq_roster_batches(id) ON DELETE CASCADE,
    snapshot_id uuid NOT NULL REFERENCES sentrix_support_roster_snapshots(id) ON DELETE CASCADE,
    ticket_id uuid NOT NULL REFERENCES sentrix_support_request_tickets(id) ON DELETE CASCADE,
    site_id uuid NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    site_code text NOT NULL,
    work_date date NOT NULL,
    shift_kind text NOT NULL,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    employee_code text,
    employee_name text,
    action text NOT NULL,
    ticket_state text NOT NULL,
    self_staff boolean NOT NULL DEFAULT TRUE,
    source text NOT NULL DEFAULT 'sentrix_support_ticket',
    idempotency_key text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    error_text text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    processed_at timestamptz,
    CONSTRAINT chk_sentrix_support_arls_bridge_actions_shift_kind
      CHECK (shift_kind IN ('day', 'night')),
    CONSTRAINT chk_sentrix_support_arls_bridge_actions_action
      CHECK (action IN ('UPSERT', 'RETRACT')),
    CONSTRAINT chk_sentrix_support_arls_bridge_actions_status
      CHECK (status IN ('pending', 'success', 'failed', 'superseded'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sentrix_support_arls_bridge_actions_idempotency
  ON sentrix_support_arls_bridge_actions (idempotency_key);

CREATE INDEX IF NOT EXISTS idx_sentrix_support_arls_bridge_actions_ticket
  ON sentrix_support_arls_bridge_actions (ticket_id, work_date DESC, shift_kind, employee_id);
