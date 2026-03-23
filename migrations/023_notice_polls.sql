CREATE TABLE IF NOT EXISTS notice_polls (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    notice_id uuid NOT NULL REFERENCES notices(id) ON DELETE CASCADE,
    question text NOT NULL,
    allow_multiple boolean NOT NULL DEFAULT false,
    is_anonymous boolean NOT NULL DEFAULT true,
    result_visibility text NOT NULL DEFAULT 'always',
    closes_at timestamptz,
    allow_change_vote boolean NOT NULL DEFAULT false,
    created_by uuid NOT NULL REFERENCES arls_users(id),
    updated_by uuid NOT NULL REFERENCES arls_users(id),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_notice_polls_result_visibility CHECK (result_visibility IN ('always', 'after_close'))
);

CREATE INDEX IF NOT EXISTS idx_notice_polls_tenant_notice
  ON notice_polls (tenant_id, notice_id, created_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS notice_poll_options (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    poll_id uuid NOT NULL REFERENCES notice_polls(id) ON DELETE CASCADE,
    label text NOT NULL,
    sort_order integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_notice_poll_options_poll
  ON notice_poll_options (tenant_id, poll_id, sort_order ASC, created_at ASC, id ASC);

CREATE TABLE IF NOT EXISTS notice_poll_votes (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    poll_id uuid NOT NULL REFERENCES notice_polls(id) ON DELETE CASCADE,
    option_id uuid NOT NULL REFERENCES notice_poll_options(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES arls_users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_notice_poll_votes_poll_user
  ON notice_poll_votes (tenant_id, poll_id, user_id, created_at DESC, id DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_notice_poll_votes_choice
  ON notice_poll_votes (poll_id, option_id, user_id);
