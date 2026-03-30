CREATE TABLE IF NOT EXISTS groupware_attachment_objects (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    module_key text NOT NULL,
    resource_type text NOT NULL,
    resource_id text,
    storage_backend text NOT NULL DEFAULT 'database',
    storage_key text,
    blob_url text,
    file_name text NOT NULL,
    file_ext text,
    mime_type text,
    byte_size bigint NOT NULL DEFAULT 0,
    sha256 text,
    metadata_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    uploaded_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_groupware_attachment_objects_tenant_module_created
    ON groupware_attachment_objects (tenant_id, module_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_groupware_attachment_objects_resource
    ON groupware_attachment_objects (tenant_id, resource_type, resource_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approval_forms (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    form_key text NOT NULL,
    display_name text NOT NULL,
    category text NOT NULL DEFAULT 'general',
    status text NOT NULL DEFAULT 'draft',
    description text NOT NULL DEFAULT '',
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, form_key)
);

CREATE TABLE IF NOT EXISTS approval_form_versions (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    form_id uuid NOT NULL REFERENCES approval_forms(id) ON DELETE CASCADE,
    version_no int NOT NULL,
    schema_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT false,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (form_id, version_no)
);

CREATE TABLE IF NOT EXISTS approval_documents (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    form_id uuid REFERENCES approval_forms(id) ON DELETE SET NULL,
    form_version_id uuid REFERENCES approval_form_versions(id) ON DELETE SET NULL,
    company_id uuid REFERENCES companies(id) ON DELETE SET NULL,
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    requester_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    document_no text,
    title text NOT NULL,
    status text NOT NULL DEFAULT 'draft',
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    legacy_source_type text,
    legacy_source_id text,
    submitted_at timestamptz,
    completed_at timestamptz,
    cancelled_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_approval_documents_tenant_status_created
    ON approval_documents (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_documents_tenant_requester_created
    ON approval_documents (tenant_id, requester_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_approval_documents_legacy_source
    ON approval_documents (tenant_id, legacy_source_type, legacy_source_id);

CREATE TABLE IF NOT EXISTS approval_steps (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    step_order int NOT NULL,
    step_type text NOT NULL DEFAULT 'approver',
    status text NOT NULL DEFAULT 'pending',
    approver_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    approver_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    delegated_from_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    acted_at timestamptz,
    due_at timestamptz,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_approval_steps_document_order
    ON approval_steps (document_id, step_order);
CREATE INDEX IF NOT EXISTS idx_approval_steps_tenant_approver_status
    ON approval_steps (tenant_id, approver_user_id, status, step_order);

CREATE TABLE IF NOT EXISTS approval_actions (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    step_id uuid REFERENCES approval_steps(id) ON DELETE SET NULL,
    actor_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    action_type text NOT NULL,
    comment_text text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_approval_actions_document_created
    ON approval_actions (document_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approval_comments (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    actor_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    body text NOT NULL,
    visibility text NOT NULL DEFAULT 'internal',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_approval_comments_document_created
    ON approval_comments (document_id, created_at DESC);

CREATE TABLE IF NOT EXISTS approval_attachments (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    attachment_object_id uuid NOT NULL REFERENCES groupware_attachment_objects(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (document_id, attachment_object_id)
);

CREATE TABLE IF NOT EXISTS approval_watchers (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    watcher_user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    watcher_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (document_id, watcher_user_id)
);

CREATE TABLE IF NOT EXISTS approval_notifications (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    document_id uuid NOT NULL REFERENCES approval_documents(id) ON DELETE CASCADE,
    recipient_user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    channel text NOT NULL DEFAULT 'in_app',
    notification_type text NOT NULL,
    state text NOT NULL DEFAULT 'queued',
    delivered_at timestamptz,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_approval_notifications_recipient_state
    ON approval_notifications (tenant_id, recipient_user_id, state, created_at DESC);

CREATE TABLE IF NOT EXISTS leave_policies (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    policy_key text NOT NULL,
    display_name text NOT NULL,
    rules_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, policy_key)
);

CREATE TABLE IF NOT EXISTS leave_grants (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    policy_id uuid REFERENCES leave_policies(id) ON DELETE SET NULL,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    grant_type text NOT NULL DEFAULT 'annual',
    granted_days numeric(8,2) NOT NULL DEFAULT 0,
    granted_hours numeric(8,2) NOT NULL DEFAULT 0,
    effective_from date NOT NULL,
    effective_to date,
    reference_key text,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_leave_grants_tenant_employee_effective
    ON leave_grants (tenant_id, employee_id, effective_from DESC);

CREATE TABLE IF NOT EXISTS leave_ledger (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    policy_id uuid REFERENCES leave_policies(id) ON DELETE SET NULL,
    approval_document_id uuid REFERENCES approval_documents(id) ON DELETE SET NULL,
    legacy_leave_request_id uuid,
    entry_type text NOT NULL,
    direction text NOT NULL DEFAULT 'debit',
    unit text NOT NULL DEFAULT 'day',
    amount numeric(8,2) NOT NULL DEFAULT 0,
    effective_date date NOT NULL,
    reason text NOT NULL DEFAULT '',
    balance_after numeric(8,2),
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_leave_ledger_tenant_employee_effective
    ON leave_ledger (tenant_id, employee_id, effective_date DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_leave_ledger_approval_document
    ON leave_ledger (approval_document_id);

CREATE TABLE IF NOT EXISTS leave_balance_snapshots (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    employee_id uuid NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    policy_id uuid REFERENCES leave_policies(id) ON DELETE SET NULL,
    snapshot_date date NOT NULL,
    remaining_days numeric(8,2) NOT NULL DEFAULT 0,
    remaining_hours numeric(8,2) NOT NULL DEFAULT 0,
    source_revision text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, employee_id, policy_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS leave_blackout_rules (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    policy_id uuid REFERENCES leave_policies(id) ON DELETE CASCADE,
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    title text NOT NULL,
    starts_on date NOT NULL,
    ends_on date NOT NULL,
    rule_type text NOT NULL DEFAULT 'block',
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_leave_blackout_rules_tenant_site_date
    ON leave_blackout_rules (tenant_id, site_id, starts_on, ends_on);

CREATE TABLE IF NOT EXISTS holiday_calendar (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    holiday_date date NOT NULL,
    holiday_name text NOT NULL,
    region_code text NOT NULL DEFAULT 'KR',
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, holiday_date, region_code)
);

CREATE TABLE IF NOT EXISTS certificate_types (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type_key text NOT NULL,
    display_name text NOT NULL,
    requires_approval boolean NOT NULL DEFAULT true,
    auto_mail_enabled boolean NOT NULL DEFAULT false,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, type_key)
);

CREATE TABLE IF NOT EXISTS certificate_templates (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    certificate_type_id uuid NOT NULL REFERENCES certificate_types(id) ON DELETE CASCADE,
    version_no int NOT NULL,
    template_source text NOT NULL DEFAULT 'html',
    template_body text NOT NULL DEFAULT '',
    attachment_object_id uuid REFERENCES groupware_attachment_objects(id) ON DELETE SET NULL,
    is_active boolean NOT NULL DEFAULT false,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (certificate_type_id, version_no)
);

CREATE TABLE IF NOT EXISTS certificate_requests (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    certificate_type_id uuid REFERENCES certificate_types(id) ON DELETE SET NULL,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    requester_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    approval_document_id uuid REFERENCES approval_documents(id) ON DELETE SET NULL,
    purpose_code text,
    purpose_text text,
    status text NOT NULL DEFAULT 'requested',
    issued_attachment_object_id uuid REFERENCES groupware_attachment_objects(id) ON DELETE SET NULL,
    requested_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    issued_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_certificate_requests_tenant_status_requested
    ON certificate_requests (tenant_id, status, requested_at DESC);

CREATE TABLE IF NOT EXISTS certificate_issue_jobs (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    certificate_request_id uuid NOT NULL REFERENCES certificate_requests(id) ON DELETE CASCADE,
    job_state text NOT NULL DEFAULT 'queued',
    attempts int NOT NULL DEFAULT 0,
    last_error text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    locked_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_certificate_issue_jobs_state_created
    ON certificate_issue_jobs (tenant_id, job_state, created_at DESC);

CREATE TABLE IF NOT EXISTS mail_accounts (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    account_key text NOT NULL,
    provider text NOT NULL DEFAULT 'smtp',
    smtp_host text,
    smtp_port int,
    sender_email text,
    sender_name text,
    username text,
    secret_ref text,
    imap_host text,
    imap_port int,
    is_active boolean NOT NULL DEFAULT true,
    settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, account_key)
);

CREATE TABLE IF NOT EXISTS mail_sender_profiles (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mail_account_id uuid REFERENCES mail_accounts(id) ON DELETE CASCADE,
    profile_key text NOT NULL,
    display_name text NOT NULL,
    reply_to_email text,
    from_email text,
    is_default boolean NOT NULL DEFAULT false,
    settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, profile_key)
);

CREATE TABLE IF NOT EXISTS mail_templates (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    template_key text NOT NULL,
    subject_template text NOT NULL DEFAULT '',
    body_template text NOT NULL DEFAULT '',
    channel text NOT NULL DEFAULT 'email',
    is_active boolean NOT NULL DEFAULT true,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, template_key)
);

CREATE TABLE IF NOT EXISTS outbound_mail_jobs (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    mail_account_id uuid REFERENCES mail_accounts(id) ON DELETE SET NULL,
    sender_profile_id uuid REFERENCES mail_sender_profiles(id) ON DELETE SET NULL,
    template_id uuid REFERENCES mail_templates(id) ON DELETE SET NULL,
    source_type text,
    source_id text,
    recipient_email text NOT NULL,
    cc_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    bcc_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    subject text NOT NULL DEFAULT '',
    body_text text NOT NULL DEFAULT '',
    state text NOT NULL DEFAULT 'queued',
    attempts int NOT NULL DEFAULT 0,
    scheduled_for timestamptz,
    sent_at timestamptz,
    last_error text,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_outbound_mail_jobs_state_created
    ON outbound_mail_jobs (tenant_id, state, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_outbound_mail_jobs_source
    ON outbound_mail_jobs (tenant_id, source_type, source_id);

CREATE TABLE IF NOT EXISTS mail_delivery_events (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    outbound_mail_job_id uuid NOT NULL REFERENCES outbound_mail_jobs(id) ON DELETE CASCADE,
    event_type text NOT NULL,
    provider_message_id text,
    event_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    occurred_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_mail_delivery_events_job_occurred
    ON mail_delivery_events (outbound_mail_job_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_type text NOT NULL DEFAULT 'group',
    title text NOT NULL DEFAULT '',
    description text NOT NULL DEFAULT '',
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_chat_conversations_tenant_created
    ON chat_conversations (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_members (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    membership_role text NOT NULL DEFAULT 'member',
    joined_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    last_seen_at timestamptz,
    UNIQUE (conversation_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_chat_members_user_conversation
    ON chat_members (tenant_id, user_id, conversation_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    sender_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    sender_employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    parent_message_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
    message_type text NOT NULL DEFAULT 'text',
    body text NOT NULL DEFAULT '',
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    edited_at timestamptz,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
    ON chat_messages (conversation_id, created_at DESC);

CREATE TABLE IF NOT EXISTS chat_attachments (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id uuid NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    attachment_object_id uuid NOT NULL REFERENCES groupware_attachment_objects(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (message_id, attachment_object_id)
);

CREATE TABLE IF NOT EXISTS chat_reads (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    last_read_message_id uuid REFERENCES chat_messages(id) ON DELETE SET NULL,
    last_read_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (conversation_id, user_id)
);

CREATE TABLE IF NOT EXISTS chat_reactions (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id uuid NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    reaction text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (message_id, user_id, reaction)
);

CREATE TABLE IF NOT EXISTS chat_polls (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    message_id uuid NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
    question text NOT NULL,
    options_json jsonb NOT NULL DEFAULT '[]'::jsonb,
    state text NOT NULL DEFAULT 'open',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE IF NOT EXISTS presence_sessions (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE CASCADE,
    session_key text NOT NULL,
    status text NOT NULL DEFAULT 'offline',
    device_type text NOT NULL DEFAULT 'web',
    last_seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, session_key)
);

CREATE INDEX IF NOT EXISTS idx_presence_sessions_user_last_seen
    ON presence_sessions (tenant_id, user_id, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS announcement_rooms (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    room_key text NOT NULL,
    scope_type text NOT NULL DEFAULT 'tenant',
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, room_key)
);

CREATE TABLE IF NOT EXISTS meeting_rooms (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    title text NOT NULL,
    host_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    room_key text NOT NULL,
    state text NOT NULL DEFAULT 'scheduled',
    scheduled_for timestamptz,
    ended_at timestamptz,
    settings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (tenant_id, room_key)
);

CREATE INDEX IF NOT EXISTS idx_meeting_rooms_tenant_state_scheduled
    ON meeting_rooms (tenant_id, state, scheduled_for DESC);

CREATE TABLE IF NOT EXISTS meeting_participants (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    meeting_room_id uuid NOT NULL REFERENCES meeting_rooms(id) ON DELETE CASCADE,
    user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    employee_id uuid REFERENCES employees(id) ON DELETE SET NULL,
    participant_role text NOT NULL DEFAULT 'participant',
    invited_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    joined_at timestamptz,
    left_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_meeting_participants_room_joined
    ON meeting_participants (meeting_room_id, joined_at DESC);

CREATE TABLE IF NOT EXISTS meeting_sessions (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    meeting_room_id uuid NOT NULL REFERENCES meeting_rooms(id) ON DELETE CASCADE,
    session_key text NOT NULL,
    media_backend text NOT NULL DEFAULT 'pion',
    state text NOT NULL DEFAULT 'created',
    started_at timestamptz,
    ended_at timestamptz,
    meta_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (meeting_room_id, session_key)
);

CREATE TABLE IF NOT EXISTS meeting_events (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    meeting_room_id uuid NOT NULL REFERENCES meeting_rooms(id) ON DELETE CASCADE,
    session_id uuid REFERENCES meeting_sessions(id) ON DELETE SET NULL,
    actor_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    event_type text NOT NULL,
    payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_meeting_events_room_created
    ON meeting_events (meeting_room_id, created_at DESC);

CREATE TABLE IF NOT EXISTS meeting_chat_links (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    meeting_room_id uuid NOT NULL REFERENCES meeting_rooms(id) ON DELETE CASCADE,
    conversation_id uuid NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    link_type text NOT NULL DEFAULT 'primary',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    UNIQUE (meeting_room_id, conversation_id)
);
