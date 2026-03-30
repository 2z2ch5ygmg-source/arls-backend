ALTER TABLE calendar_booking_links
    ADD COLUMN IF NOT EXISTS approval_policy text NOT NULL DEFAULT 'instant',
    ADD COLUMN IF NOT EXISTS assignment_mode text NOT NULL DEFAULT 'single_host';

ALTER TABLE calendar_events
    ADD COLUMN IF NOT EXISTS custom_fields_json jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE TABLE IF NOT EXISTS calendar_comments (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    author_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    body text NOT NULL DEFAULT '',
    is_internal boolean NOT NULL DEFAULT FALSE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_calendar_comments_event
ON calendar_comments (event_id, created_at ASC);
