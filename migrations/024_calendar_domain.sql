CREATE TABLE IF NOT EXISTS calendar_containers (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    owner_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    scope_type text NOT NULL CHECK (scope_type IN ('personal', 'team', 'shared')),
    name text NOT NULL,
    color text NOT NULL DEFAULT '#ff7a1a',
    provider text NOT NULL DEFAULT 'arls',
    external_ref text,
    is_default boolean NOT NULL DEFAULT FALSE,
    is_system boolean NOT NULL DEFAULT FALSE,
    is_active boolean NOT NULL DEFAULT TRUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_members (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    container_id uuid NOT NULL REFERENCES calendar_containers(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    email text,
    permission text NOT NULL CHECK (permission IN ('view_only', 'free_busy_only', 'edit', 'owner')),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    container_id uuid NOT NULL REFERENCES calendar_containers(id) ON DELETE CASCADE,
    created_by_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    title text NOT NULL,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    timezone text NOT NULL DEFAULT 'Asia/Seoul',
    is_all_day boolean NOT NULL DEFAULT FALSE,
    recurrence_rule text,
    availability_status text NOT NULL DEFAULT 'busy',
    visibility text NOT NULL DEFAULT 'private',
    location text,
    conferencing_provider text,
    conferencing_url text,
    description text,
    external_source text,
    external_ref text,
    status text NOT NULL DEFAULT 'confirmed',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_attendees (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    email text,
    display_name text,
    is_required boolean NOT NULL DEFAULT TRUE,
    is_organizer boolean NOT NULL DEFAULT FALSE,
    rsvp_status text NOT NULL DEFAULT 'needs_action',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_reminders (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    channel text NOT NULL DEFAULT 'in_app',
    minutes_before integer,
    absolute_trigger_at timestamptz,
    snoozed_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_notes (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    author_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    note_type text NOT NULL CHECK (note_type IN ('shared', 'private')),
    body text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_action_items (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    assignee_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    body text NOT NULL,
    due_at timestamptz,
    state text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_attachments (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    event_id uuid NOT NULL REFERENCES calendar_events(id) ON DELETE CASCADE,
    label text NOT NULL,
    url text NOT NULL,
    mime_type text,
    size_bytes bigint,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_booking_links (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    container_id uuid REFERENCES calendar_containers(id) ON DELETE SET NULL,
    slug text NOT NULL,
    title text NOT NULL,
    description text,
    is_public boolean NOT NULL DEFAULT TRUE,
    approval_required boolean NOT NULL DEFAULT FALSE,
    booking_window_days integer NOT NULL DEFAULT 14,
    buffer_before_minutes integer NOT NULL DEFAULT 0,
    buffer_after_minutes integer NOT NULL DEFAULT 0,
    expires_at timestamptz,
    host_notes text,
    intake_questions_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_sync_connections (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    owner_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    provider text NOT NULL,
    access_scope text NOT NULL DEFAULT 'read',
    account_email text,
    account_label text,
    sync_state text NOT NULL DEFAULT 'disconnected',
    last_synced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calendar_resources (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    resource_code text NOT NULL,
    resource_name text NOT NULL,
    resource_type text NOT NULL DEFAULT 'room',
    capacity integer,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT TRUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_personal_container
ON calendar_containers (tenant_id, owner_user_id)
WHERE scope_type = 'personal' AND owner_user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_team_container
ON calendar_containers (tenant_id, site_id)
WHERE scope_type = 'team' AND site_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_shared_system_container
ON calendar_containers (tenant_id, scope_type)
WHERE scope_type = 'shared' AND is_system = TRUE;

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_member_user
ON calendar_members (container_id, user_id)
WHERE user_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_booking_links_slug
ON calendar_booking_links (slug);

CREATE INDEX IF NOT EXISTS idx_calendar_events_tenant_window
ON calendar_events (tenant_id, starts_at, ends_at);

CREATE INDEX IF NOT EXISTS idx_calendar_events_container_start
ON calendar_events (container_id, starts_at);

CREATE INDEX IF NOT EXISTS idx_calendar_booking_links_tenant
ON calendar_booking_links (tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_calendar_sync_connections_tenant
ON calendar_sync_connections (tenant_id, created_at DESC);
