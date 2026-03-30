CREATE TABLE IF NOT EXISTS approval_line_rules (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    form_key text NOT NULL,
    rule_order int NOT NULL DEFAULT 1,
    rule_name text NOT NULL DEFAULT '',
    approver_role text,
    approver_user_id uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    scope_type text NOT NULL DEFAULT 'tenant',
    site_id uuid REFERENCES sites(id) ON DELETE SET NULL,
    is_active boolean NOT NULL DEFAULT true,
    conditions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid REFERENCES arls_users(id) ON DELETE SET NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_approval_line_rules_scope_type
        CHECK (scope_type IN ('tenant', 'site', 'site_or_tenant'))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_approval_line_rules_tenant_form_order
    ON approval_line_rules (tenant_id, form_key, rule_order);

CREATE INDEX IF NOT EXISTS idx_approval_line_rules_tenant_form_active
    ON approval_line_rules (tenant_id, form_key, is_active, rule_order);

CREATE INDEX IF NOT EXISTS idx_approval_line_rules_tenant_site_form
    ON approval_line_rules (tenant_id, site_id, form_key, is_active, rule_order);
