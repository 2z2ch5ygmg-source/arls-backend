CREATE TABLE IF NOT EXISTS notice_attachments (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    file_name text NOT NULL,
    mime_type text NOT NULL,
    raw_bytes bytea NOT NULL,
    created_by uuid NOT NULL REFERENCES arls_users(id),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_notice_attachments_tenant_created
  ON notice_attachments (tenant_id, created_at DESC, id DESC);
