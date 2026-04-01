ALTER TABLE employees
    ADD COLUMN IF NOT EXISTS email text;

CREATE INDEX IF NOT EXISTS idx_employees_tenant_email
    ON employees (tenant_id, lower(email))
    WHERE email IS NOT NULL;
