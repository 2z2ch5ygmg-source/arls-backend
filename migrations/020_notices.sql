CREATE TABLE IF NOT EXISTS notices (
    id uuid PRIMARY KEY DEFAULT arls_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    category text NOT NULL,
    title text NOT NULL,
    body_text text NOT NULL,
    is_pinned boolean NOT NULL DEFAULT false,
    published_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    created_by uuid NOT NULL REFERENCES arls_users(id),
    updated_by uuid NOT NULL REFERENCES arls_users(id),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_notices_category CHECK (category IN ('ops', 'attendance', 'schedule', 'hr', 'system', 'event'))
);

CREATE INDEX IF NOT EXISTS idx_notices_tenant_published
  ON notices (tenant_id, is_pinned DESC, published_at DESC, created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_notices_tenant_category_published
  ON notices (tenant_id, category, is_pinned DESC, published_at DESC, created_at DESC, id DESC);
