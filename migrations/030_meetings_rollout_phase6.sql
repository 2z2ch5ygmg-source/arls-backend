CREATE INDEX IF NOT EXISTS idx_meeting_sessions_room_state_started
  ON meeting_sessions (meeting_room_id, state, started_at DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_meeting_participants_room_user
  ON meeting_participants (meeting_room_id, user_id, invited_at DESC);

CREATE INDEX IF NOT EXISTS idx_meeting_chat_links_room_created
  ON meeting_chat_links (meeting_room_id, created_at DESC);

CREATE TABLE IF NOT EXISTS groupware_rollout_checks (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    module_key text NOT NULL,
    environment_key text NOT NULL DEFAULT 'default',
    check_type text NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    summary text NOT NULL DEFAULT '',
    detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    checked_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    checked_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_groupware_rollout_checks_status
      CHECK (status IN ('pending', 'ready', 'blocked', 'passed', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_groupware_rollout_checks_module_checked
  ON groupware_rollout_checks (tenant_id, module_key, checked_at DESC, created_at DESC);
