
CREATE TABLE IF NOT EXISTS arls_users (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    username text NOT NULL,
    password_hash text NOT NULL,
    must_change_password boolean NOT NULL DEFAULT false,
    full_name text NOT NULL DEFAULT '',
    role text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    employee_id uuid NULL,
    phone text,
    site_id uuid,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    last_login_at timestamptz,
    CONSTRAINT arls_users_username_tenant_uniq UNIQUE (tenant_id, username)
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'arls_users'
  ) THEN
    WITH normalized AS (
      SELECT
        au.id,
        au.tenant_id,
        btrim(COALESCE(au.username, '')) AS current_username,
        regexp_replace(btrim(COALESCE(au.username, '')), '[-[:space:]]+', '', 'g') AS normalized_username
      FROM arls_users au
    ),
    duplicate_targets AS (
      SELECT tenant_id, normalized_username
      FROM normalized
      WHERE normalized_username <> ''
      GROUP BY tenant_id, normalized_username
      HAVING COUNT(*) > 1
    ),
    updatable AS (
      SELECT n.id, n.normalized_username
      FROM normalized n
      LEFT JOIN duplicate_targets d
        ON d.tenant_id = n.tenant_id
       AND d.normalized_username = n.normalized_username
      WHERE d.tenant_id IS NULL
        AND n.normalized_username <> ''
        AND n.current_username <> n.normalized_username
    )
    UPDATE arls_users au
    SET username = u.normalized_username,
        updated_at = timezone('utc', now())
    FROM updatable u
    WHERE au.id = u.id;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS api_idempotency_keys (
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    request_key text NOT NULL,
    method text NOT NULL,
    path text NOT NULL,
    request_hash text,
    first_seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    last_seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    call_count int NOT NULL DEFAULT 1,
    PRIMARY KEY (tenant_id, user_id, request_key)
);

CREATE INDEX IF NOT EXISTS idx_api_idempotency_keys_last_seen
    ON api_idempotency_keys (last_seen_at);

CREATE TABLE IF NOT EXISTS schedule_import_batches (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    created_by uuid NOT NULL,
    filename text,
    status text NOT NULL DEFAULT 'staged',
    total_rows int NOT NULL DEFAULT 0,
    valid_rows int NOT NULL DEFAULT 0,
    invalid_rows int NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    completed_at timestamptz,
    error_text text
);

CREATE TABLE IF NOT EXISTS schedule_import_rows (
    id uuid PRIMARY KEY,
    batch_id uuid NOT NULL REFERENCES schedule_import_batches(id) ON DELETE CASCADE,
    row_no int NOT NULL,
    tenant_code text NOT NULL,
    company_code text NOT NULL,
    site_code text NOT NULL,
    employee_code text NOT NULL,
    schedule_date date NOT NULL,
    shift_type text NOT NULL,
    validation_error text,
    employee_id uuid,
    company_id uuid,
    site_id uuid,
    tenant_id uuid,
    is_valid boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_schedule_import_rows_batch
    ON schedule_import_rows (batch_id, row_no);
CREATE INDEX IF NOT EXISTS idx_schedule_import_rows_invalid
    ON schedule_import_rows (batch_id, is_valid);

CREATE INDEX IF NOT EXISTS idx_schedule_import_rows_lookups
    ON schedule_import_rows (tenant_code, company_code, site_code, employee_code, schedule_date);

DO $$
BEGIN
  IF EXISTS (
  SELECT 1
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_rows'
      AND column_name = 'schedule_date'
      AND is_nullable = 'NO'
  ) THEN
    ALTER TABLE schedule_import_rows
      ALTER COLUMN schedule_date DROP NOT NULL;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS guard_roster_import_sessions (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    uploaded_by uuid NOT NULL,
    status text NOT NULL DEFAULT 'OPEN',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_guard_roster_import_sessions_tenant_status
    ON guard_roster_import_sessions (tenant_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS guard_roster_import_files (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    upload_session_id uuid,
    uploaded_by uuid NOT NULL,
    filename text NOT NULL,
    mime_type text NOT NULL DEFAULT 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    file_bytes bytea NOT NULL,
    photo_bytes bytea,
    photo_mime_type text,
    photo_filename text,
    import_status text NOT NULL DEFAULT 'STAGED',
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

ALTER TABLE guard_roster_import_files
    ADD COLUMN IF NOT EXISTS upload_session_id uuid;
ALTER TABLE guard_roster_import_files
    ADD COLUMN IF NOT EXISTS import_status text NOT NULL DEFAULT 'STAGED';
ALTER TABLE guard_roster_import_files
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT timezone('utc', now());

CREATE INDEX IF NOT EXISTS idx_guard_roster_import_files_tenant_created
    ON guard_roster_import_files (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_guard_roster_import_files_tenant_session
    ON guard_roster_import_files (tenant_id, upload_session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sites_match_index (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    site_id text NOT NULL,
    site_name text NOT NULL,
    address_text text NOT NULL,
    address_norm text NOT NULL,
    updated_at text NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_sites_match_index_tenant_site
    ON sites_match_index (tenant_id, site_id);
CREATE INDEX IF NOT EXISTS idx_sites_match_index_tenant
    ON sites_match_index (tenant_id);
CREATE INDEX IF NOT EXISTS idx_sites_match_index_tenant_address_norm
    ON sites_match_index (tenant_id, address_norm);


-- [AUTOMATION TRACK v1] Apple 보고 자동화 전용 정책/기록 테이블
CREATE TABLE IF NOT EXISTS site_apple_daytime_policy (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    weekday_headcount int NOT NULL DEFAULT 2 CHECK (weekday_headcount >= 0),
    weekend_headcount int NOT NULL DEFAULT 1 CHECK (weekend_headcount >= 0),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_site_apple_daytime_policy UNIQUE (tenant_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_site_apple_daytime_policy_tenant_site
    ON site_apple_daytime_policy (tenant_id, site_id);

CREATE TABLE IF NOT EXISTS apple_report_overnight_records (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    headcount int NOT NULL DEFAULT 0 CHECK (headcount >= 0),
    time_range text NOT NULL DEFAULT '22:00-08:00',
    hours numeric(4, 2) NOT NULL DEFAULT 10.0,
    source_ticket_id bigint,
    source_event_uid text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_apple_report_overnight_tenant_site_date UNIQUE (tenant_id, site_id, work_date)
);

CREATE INDEX IF NOT EXISTS idx_apple_report_overnight_tenant_date
    ON apple_report_overnight_records (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_apple_report_overnight_tenant_site_date
    ON apple_report_overnight_records (tenant_id, site_id, work_date DESC);

CREATE TABLE IF NOT EXISTS apple_daytime_ot (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    leader_user_id uuid NOT NULL,
    reason text,
    status text NOT NULL DEFAULT 'PENDING_REASON',
    hours numeric(4, 2) NOT NULL DEFAULT 1.0,
    closer_user_id uuid,
    source text NOT NULL DEFAULT 'APPLE_DAYTIME_OT',
    source_event_uid text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_apple_daytime_ot_tenant_site_date_leader UNIQUE (tenant_id, site_id, work_date, leader_user_id),
    CONSTRAINT chk_apple_daytime_ot_reason CHECK (reason IS NULL OR reason IN ('complaint', 'repair', 'inquiry')),
    CONSTRAINT chk_apple_daytime_ot_status CHECK (status IN ('PENDING_REASON', 'APPROVED', 'CANCELLED'))
);

CREATE INDEX IF NOT EXISTS idx_apple_daytime_ot_tenant_date
    ON apple_daytime_ot (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_apple_daytime_ot_tenant_site_date
    ON apple_daytime_ot (tenant_id, site_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_apple_daytime_ot_tenant_status_date
    ON apple_daytime_ot (tenant_id, status, work_date DESC);

CREATE TABLE IF NOT EXISTS apple_late_shift (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    employee_id uuid,
    employee_name text NOT NULL,
    note text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_apple_late_shift_tenant_date
    ON apple_late_shift (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_apple_late_shift_tenant_site_date
    ON apple_late_shift (tenant_id, site_id, work_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_apple_late_shift_tenant_site_date_name
    ON apple_late_shift (tenant_id, site_id, work_date, lower(employee_name));

CREATE TABLE IF NOT EXISTS site_shift_policy (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    weekday_headcount int NOT NULL DEFAULT 2 CHECK (weekday_headcount >= 0),
    weekend_headcount int NOT NULL DEFAULT 1 CHECK (weekend_headcount >= 0),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_site_shift_policy UNIQUE (tenant_id, site_id)
);

CREATE INDEX IF NOT EXISTS idx_site_shift_policy_tenant_site
    ON site_shift_policy (tenant_id, site_id);

CREATE TABLE IF NOT EXISTS apple_overtime_log (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    leader_user_id uuid NOT NULL,
    reason text NOT NULL,
    hours numeric(4, 2) NOT NULL DEFAULT 1.0,
    source text NOT NULL DEFAULT 'APPLE_DAYTIME_OT',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_apple_overtime_log_tenant_date
    ON apple_overtime_log (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_apple_overtime_log_tenant_site_date
    ON apple_overtime_log (tenant_id, site_id, work_date DESC);

CREATE TABLE IF NOT EXISTS late_shift_log (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    employee_id uuid NOT NULL,
    minutes_late int NOT NULL CHECK (minutes_late >= 0),
    note text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_late_shift_log_tenant_date
    ON late_shift_log (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_late_shift_log_tenant_site_date
    ON late_shift_log (tenant_id, site_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_late_shift_log_tenant_employee_date
    ON late_shift_log (tenant_id, employee_id, work_date DESC);

CREATE TABLE IF NOT EXISTS external_support_workers (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid,
    worker_type text NOT NULL,
    worker_name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_external_support_worker_type
      CHECK (worker_type IN ('F', 'BK', 'INTERNAL'))
);

CREATE INDEX IF NOT EXISTS idx_external_support_workers_tenant_name
    ON external_support_workers (tenant_id, lower(worker_name));

CREATE TABLE IF NOT EXISTS support_assignment (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    worker_type text NOT NULL,
    employee_id uuid,
    name text NOT NULL,
    source text NOT NULL DEFAULT 'SHEET',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_support_assignment_worker_type
      CHECK (worker_type IN ('F', 'BK', 'INTERNAL'))
);

CREATE INDEX IF NOT EXISTS idx_support_assignment_tenant_date
    ON support_assignment (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_support_assignment_tenant_site_date
    ON support_assignment (tenant_id, site_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_support_assignment_tenant_employee_date
    ON support_assignment (tenant_id, employee_id, work_date DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_support_assignment_tenant_site_date_name
    ON support_assignment (tenant_id, site_id, work_date, lower(name));

CREATE TABLE IF NOT EXISTS daily_event_log (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    type text NOT NULL,
    description text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_daily_event_log_type CHECK (type IN ('EVENT', 'ADDITIONAL'))
);

CREATE INDEX IF NOT EXISTS idx_daily_event_log_tenant_date
    ON daily_event_log (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_daily_event_log_tenant_site_date
    ON daily_event_log (tenant_id, site_id, work_date DESC);

DO $$
BEGIN
  IF EXISTS (
  SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'employees'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'duty_role'
    ) THEN
      ALTER TABLE employees ADD COLUMN duty_role text NOT NULL DEFAULT 'GUARD';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'external_employee_key'
    ) THEN
      ALTER TABLE employees ADD COLUMN external_employee_key text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'linked_employee_id'
    ) THEN
      ALTER TABLE employees ADD COLUMN linked_employee_id text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'sequence_no'
    ) THEN
      ALTER TABLE employees ADD COLUMN sequence_no int;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'employee_uuid'
    ) THEN
      ALTER TABLE employees ADD COLUMN employee_uuid text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'birth_date'
    ) THEN
      ALTER TABLE employees ADD COLUMN birth_date date;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'hire_date'
    ) THEN
      ALTER TABLE employees ADD COLUMN hire_date date;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'guard_training_cert_no'
    ) THEN
      ALTER TABLE employees ADD COLUMN guard_training_cert_no text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'note'
    ) THEN
      ALTER TABLE employees ADD COLUMN note text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'worker_role'
    ) THEN
      ALTER TABLE employees ADD COLUMN worker_role text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'soc_login_id'
    ) THEN
      ALTER TABLE employees ADD COLUMN soc_login_id text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'soc_role'
    ) THEN
      ALTER TABLE employees ADD COLUMN soc_role text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'management_no_str'
    ) THEN
      ALTER TABLE employees ADD COLUMN management_no_str text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'username'
    ) THEN
      ALTER TABLE employees ADD COLUMN username text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'password_hash'
    ) THEN
      ALTER TABLE employees ADD COLUMN password_hash text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'must_change_password'
    ) THEN
      ALTER TABLE employees ADD COLUMN must_change_password boolean NOT NULL DEFAULT true;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'role'
    ) THEN
      ALTER TABLE employees ADD COLUMN role text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'address'
    ) THEN
      ALTER TABLE employees ADD COLUMN address text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'leave_date'
    ) THEN
      ALTER TABLE employees ADD COLUMN leave_date date;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'roster_docx_attachment_id'
    ) THEN
      ALTER TABLE employees ADD COLUMN roster_docx_attachment_id text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'employees' AND column_name = 'photo_attachment_id'
    ) THEN
      ALTER TABLE employees ADD COLUMN photo_attachment_id text;
    END IF;

    -- sequence_no 재정렬(충돌 방지):
    -- 기존 값이 일부 남아있으면 uq_employees_tenant_site_sequence와 충돌할 수 있으므로
    -- 전체를 NULL로 비운 뒤 tenant/site 단위 ROW_NUMBER로 일괄 재부여한다.
    UPDATE employees
    SET sequence_no = NULL;

    WITH numbered AS (
      SELECT e.id,
             ROW_NUMBER() OVER (
               PARTITION BY e.tenant_id, e.site_id
               ORDER BY e.created_at NULLS LAST, e.id
             ) AS seq
      FROM employees e
    )
    UPDATE employees e
    SET sequence_no = n.seq
    FROM numbered n
    WHERE e.id = n.id;

    CREATE INDEX IF NOT EXISTS idx_employees_tenant_site_linked
      ON employees (tenant_id, site_id, linked_employee_id);
    CREATE INDEX IF NOT EXISTS idx_employees_tenant_site_external
      ON employees (tenant_id, site_id, external_employee_key);
    CREATE INDEX IF NOT EXISTS idx_employees_tenant_site_duty_role
      ON employees (tenant_id, site_id, duty_role);
    CREATE INDEX IF NOT EXISTS idx_employees_tenant_site
      ON employees (tenant_id, site_id);
    CREATE INDEX IF NOT EXISTS idx_employees_tenant_employee_code
      ON employees (tenant_id, employee_code);
    CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_tenant_site_sequence
      ON employees (tenant_id, site_id, sequence_no)
      WHERE sequence_no IS NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS uq_employees_employee_uuid
      ON employees (employee_uuid)
      WHERE employee_uuid IS NOT NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'sites'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'employee_sequence_seed'
    ) THEN
      ALTER TABLE sites ADD COLUMN employee_sequence_seed int NOT NULL DEFAULT 0;
    END IF;

    -- 기존 직원 데이터가 있으면 site 시드값을 최대 순번으로 보정한다.
    UPDATE sites s
    SET employee_sequence_seed = GREATEST(
      COALESCE(s.employee_sequence_seed, 0),
      COALESCE(seq.max_seq, 0)
    )
    FROM (
      SELECT site_id, MAX(COALESCE(sequence_no, 0)) AS max_seq
      FROM employees
      GROUP BY site_id
    ) AS seq
    WHERE s.id = seq.site_id;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'monthly_schedules'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'monthly_schedules' AND column_name = 'source'
    ) THEN
      ALTER TABLE monthly_schedules ADD COLUMN source text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'monthly_schedules' AND column_name = 'source_ticket_id'
    ) THEN
      ALTER TABLE monthly_schedules ADD COLUMN source_ticket_id bigint;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'monthly_schedules' AND column_name = 'schedule_note'
    ) THEN
      ALTER TABLE monthly_schedules ADD COLUMN schedule_note text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'monthly_schedules' AND column_name = 'leader_user_id'
    ) THEN
      ALTER TABLE monthly_schedules ADD COLUMN leader_user_id uuid;
    END IF;

    CREATE INDEX IF NOT EXISTS idx_monthly_schedules_tenant_site_date_leader
      ON monthly_schedules (tenant_id, site_id, schedule_date, leader_user_id);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'ticket_id'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN ticket_id bigint;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'overtime_source'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN overtime_source text NOT NULL DEFAULT 'SOC_TICKET';
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'raw_minutes_total'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN raw_minutes_total int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'overtime_hours_step'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN overtime_hours_step numeric(6, 2) NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'overtime_policy'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN overtime_policy text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'soc_overtime_approvals' AND column_name = 'closer_user_id'
    ) THEN
      ALTER TABLE soc_overtime_approvals ADD COLUMN closer_user_id uuid;
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS overnight_assignments (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid,
    work_date date NOT NULL,
    shift_start_at timestamptz NOT NULL,
    shift_end_at timestamptz NOT NULL,
    shift_hours numeric(6, 2) NOT NULL DEFAULT 10,
    requested_count int NOT NULL DEFAULT 0,
    source text NOT NULL DEFAULT 'SOC',
    ticket_id bigint,
    source_event_uid text UNIQUE,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_overnight_assignments_tenant_date
    ON overnight_assignments (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_overnight_assignments_tenant_site_date
    ON overnight_assignments (tenant_id, site_id, work_date DESC);

CREATE TABLE IF NOT EXISTS integration_event_log (
    id uuid PRIMARY KEY,
    source text NOT NULL DEFAULT 'SOC',
    event_id text NOT NULL UNIQUE,
    event_type text NOT NULL,
    tenant_id uuid,
    site_id text,
    ticket_id bigint,
    occurred_at timestamptz,
    payload_digest text NOT NULL,
    status text NOT NULL DEFAULT 'FAIL',
    error_message text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_integration_event_log_status CHECK (status IN ('SUCCESS', 'FAIL'))
);

CREATE INDEX IF NOT EXISTS idx_integration_event_log_tenant_created
    ON integration_event_log (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_integration_event_log_event_type_created
    ON integration_event_log (event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS audit_log (
    id uuid PRIMARY KEY,
    tenant_id uuid,
    actor_type text NOT NULL,
    actor_id text,
    action_type text NOT NULL,
    entity_type text NOT NULL,
    entity_id text,
    before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_audit_log_actor_type CHECK (actor_type IN ('SOC', 'HR_USER', 'SYSTEM')),
    CONSTRAINT chk_audit_log_entity_type CHECK (entity_type IN ('SCHEDULE', 'ATTENDANCE', 'OVERTIME', 'LEAVE', 'REPORT'))
);

CREATE INDEX IF NOT EXISTS idx_audit_log_tenant_created
    ON audit_log (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action_created
    ON audit_log (action_type, created_at DESC);

CREATE TABLE IF NOT EXISTS sheets_sync_log (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    profile_id uuid,
    direction text NOT NULL,
    status text NOT NULL,
    error_message text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sheets_sync_log_direction CHECK (direction IN ('DB_TO_SHEET', 'SHEET_TO_DB')),
    CONSTRAINT chk_sheets_sync_log_status CHECK (status IN ('SUCCESS', 'FAIL'))
);

CREATE INDEX IF NOT EXISTS idx_sheets_sync_log_tenant_created
    ON sheets_sync_log (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sheets_sync_log_profile_created
    ON sheets_sync_log (profile_id, created_at DESC);

CREATE TABLE IF NOT EXISTS sheets_sync_retry_queue (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    tenant_code text NOT NULL,
    profile_id uuid NOT NULL,
    request_key text NOT NULL UNIQUE,
    trigger_event_type text,
    profile_scope text NOT NULL,
    dispatch_input jsonb NOT NULL DEFAULT '{}'::jsonb,
    retry_count int NOT NULL DEFAULT 0,
    max_retries int NOT NULL DEFAULT 3,
    next_retry_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    status text NOT NULL DEFAULT 'pending',
    last_error text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT chk_sheets_sync_retry_status CHECK (status IN ('pending', 'success', 'dead'))
);

CREATE INDEX IF NOT EXISTS idx_sheets_sync_retry_tenant_next
    ON sheets_sync_retry_queue (tenant_id, status, next_retry_at ASC);

CREATE TABLE IF NOT EXISTS integration_feature_flags (
    tenant_id uuid NOT NULL,
    flag_key text NOT NULL,
    enabled boolean NOT NULL DEFAULT false,
    updated_by uuid,
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    PRIMARY KEY (tenant_id, flag_key)
);

CREATE INDEX IF NOT EXISTS idx_integration_feature_flags_tenant
    ON integration_feature_flags (tenant_id, flag_key, enabled);

CREATE TABLE IF NOT EXISTS integration_audit_logs (
    id uuid PRIMARY KEY,
    tenant_id uuid,
    action_type text NOT NULL,
    source text NOT NULL DEFAULT 'hr',
    actor_user_id uuid,
    actor_role text,
    target_type text,
    target_id text,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_integration_audit_logs_tenant_created
    ON integration_audit_logs (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_integration_audit_logs_action_created
    ON integration_audit_logs (action_type, created_at DESC);

CREATE TABLE IF NOT EXISTS soc_event_ingests (
    id uuid PRIMARY KEY,
    event_uid text NOT NULL UNIQUE,
    tenant_id uuid,
    tenant_code text,
    source text NOT NULL DEFAULT 'soc',
    event_type text NOT NULL,
    idempotency_key text,
    status text NOT NULL DEFAULT 'received',
    error_text text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    applied_changes jsonb NOT NULL DEFAULT '{}'::jsonb,
    signature_valid boolean NOT NULL DEFAULT false,
    received_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    processed_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_soc_event_ingests_tenant_received
    ON soc_event_ingests (tenant_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_soc_event_ingests_status_received
    ON soc_event_ingests (status, received_at DESC);

CREATE TABLE IF NOT EXISTS soc_overtime_approvals (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    site_id uuid,
    work_date date NOT NULL,
    approved_minutes int NOT NULL DEFAULT 0,
    overtime_units numeric(6, 2) NOT NULL DEFAULT 0,
    reason text,
    source_event_uid text UNIQUE,
    source text NOT NULL DEFAULT 'soc',
    ticket_id bigint,
    overtime_source text NOT NULL DEFAULT 'SOC_TICKET',
    overtime_policy text,
    closer_user_id uuid,
    raw_minutes_total int NOT NULL DEFAULT 0,
    overtime_hours_step numeric(6, 2) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_soc_overtime_approvals_tenant_date
    ON soc_overtime_approvals (tenant_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_soc_overtime_approvals_tenant_employee_date
    ON soc_overtime_approvals (tenant_id, employee_id, work_date DESC);
CREATE INDEX IF NOT EXISTS idx_soc_overtime_approvals_tenant_emp_date_source
    ON soc_overtime_approvals (tenant_id, employee_id, work_date DESC, overtime_source);

CREATE TABLE IF NOT EXISTS apple_overnight_reports (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    site_id uuid,
    work_date date NOT NULL,
    overnight_approved boolean NOT NULL DEFAULT true,
    source_event_uid text UNIQUE,
    source text NOT NULL DEFAULT 'soc',
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_apple_overnight_reports UNIQUE (tenant_id, employee_id, work_date, source)
);

CREATE INDEX IF NOT EXISTS idx_apple_overnight_reports_tenant_date
    ON apple_overnight_reports (tenant_id, work_date DESC);

CREATE TABLE IF NOT EXISTS site_daily_closing_ot (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    site_id uuid NOT NULL,
    work_date date NOT NULL,
    employee_id uuid NOT NULL,
    checkout_at timestamptz NOT NULL,
    overtime_minutes int NOT NULL DEFAULT 0,
    source_event_uid text,
    policy_priority int NOT NULL DEFAULT 0,
    closer_selection_rule text,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_site_daily_closing_ot UNIQUE (tenant_id, site_id, work_date)
);

CREATE INDEX IF NOT EXISTS idx_site_daily_closing_ot_tenant_date
    ON site_daily_closing_ot (tenant_id, work_date DESC);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'site_daily_closing_ot'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'site_daily_closing_ot' AND column_name = 'policy_priority'
    ) THEN
      ALTER TABLE site_daily_closing_ot ADD COLUMN policy_priority int NOT NULL DEFAULT 0;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'site_daily_closing_ot' AND column_name = 'closer_selection_rule'
    ) THEN
      ALTER TABLE site_daily_closing_ot ADD COLUMN closer_selection_rule text;
    END IF;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS google_sheet_profiles (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    profile_name text NOT NULL,
    is_active boolean NOT NULL DEFAULT false,
    spreadsheet_id text,
    worksheet_schedule text,
    worksheet_overtime text,
    worksheet_overnight text,
    webhook_url text,
    auth_mode text NOT NULL DEFAULT 'webhook',
    credential_ref text,
    mapping_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    options_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_by uuid,
    updated_by uuid,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    CONSTRAINT uq_google_sheet_profiles_name UNIQUE (tenant_id, profile_name)
);

CREATE INDEX IF NOT EXISTS idx_google_sheet_profiles_tenant_active
    ON google_sheet_profiles (tenant_id, is_active, updated_at DESC);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tenants'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'is_active'
    ) THEN
      ALTER TABLE tenants ADD COLUMN is_active boolean NOT NULL DEFAULT true;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'created_at'
    ) THEN
      ALTER TABLE tenants ADD COLUMN created_at timestamptz NOT NULL DEFAULT timezone('utc', now());
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'updated_at'
    ) THEN
      ALTER TABLE tenants ADD COLUMN updated_at timestamptz NOT NULL DEFAULT timezone('utc', now());
    END IF;

    CREATE INDEX IF NOT EXISTS idx_tenants_active_code
      ON tenants (is_active, tenant_code);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'tenants'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'is_deleted'
    ) THEN
      ALTER TABLE tenants ADD COLUMN is_deleted boolean NOT NULL DEFAULT false;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'deleted_at'
    ) THEN
      ALTER TABLE tenants ADD COLUMN deleted_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'tenants' AND column_name = 'deleted_by'
    ) THEN
      ALTER TABLE tenants ADD COLUMN deleted_by uuid;
    END IF;

    CREATE INDEX IF NOT EXISTS idx_tenants_active_deleted_code
      ON tenants (is_active, is_deleted, tenant_code);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'arls_users'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'arls_users' AND column_name = 'is_deleted'
    ) THEN
      ALTER TABLE arls_users ADD COLUMN is_deleted boolean NOT NULL DEFAULT false;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'arls_users' AND column_name = 'must_change_password'
    ) THEN
      ALTER TABLE arls_users ADD COLUMN must_change_password boolean NOT NULL DEFAULT false;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'arls_users' AND column_name = 'deleted_at'
    ) THEN
      ALTER TABLE arls_users ADD COLUMN deleted_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'arls_users' AND column_name = 'deleted_by'
    ) THEN
      ALTER TABLE arls_users ADD COLUMN deleted_by uuid;
    END IF;

    CREATE INDEX IF NOT EXISTS idx_arls_users_tenant_active_deleted
      ON arls_users (tenant_id, is_active, is_deleted, role);
    CREATE INDEX IF NOT EXISTS idx_arls_users_tenant_employee_active_recent
      ON arls_users (tenant_id, employee_id, is_active, updated_at DESC, created_at DESC);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS attendance_requests (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    site_id uuid NOT NULL,
    request_type text NOT NULL DEFAULT 'check_in',
    reason_code text NOT NULL,
    reason_detail text,
    requested_at timestamptz NOT NULL,
    latitude double precision NOT NULL,
    longitude double precision NOT NULL,
    accuracy_meters double precision NOT NULL,
    distance_meters double precision NOT NULL,
    radius_meters double precision NOT NULL,
    device_info text,
    photo_names text[] NOT NULL DEFAULT '{}',
    status text NOT NULL DEFAULT 'pending',
    review_note text,
    reviewed_by uuid,
    reviewed_at timestamptz,
    cancelled_at timestamptz,
    approved_attendance_id uuid,
    created_by uuid,
    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_attendance_requests_tenant_created
    ON attendance_requests (tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_requests_tenant_employee
    ON attendance_requests (tenant_id, employee_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_requests_tenant_status
    ON attendance_requests (tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attendance_requests_tenant_site_status
    ON attendance_requests (tenant_id, site_id, status, requested_at DESC);

CREATE TABLE IF NOT EXISTS leave_requests (
    id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL,
    employee_id uuid NOT NULL,
    leave_type text NOT NULL,
    half_day_slot text,
    start_at date NOT NULL,
    end_at date NOT NULL,
    attachment_names text[] NOT NULL DEFAULT ARRAY[]::text[],
    reason text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending',
    requested_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
    review_note text,
    reviewed_by uuid,
    reviewed_at timestamptz,
    cancelled_at timestamptz
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'leave_requests'
  ) THEN
    -- Legacy schemas may enforce leave_type without 'early_leave'.
    ALTER TABLE leave_requests DROP CONSTRAINT IF EXISTS leave_requests_leave_type_check;
    ALTER TABLE leave_requests
      ADD CONSTRAINT leave_requests_leave_type_check
      CHECK (leave_type IN ('annual', 'half', 'sick', 'other', 'early_leave'));
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_leave_requests_tenant_status
    ON leave_requests (tenant_id, status, requested_at DESC);
CREATE INDEX IF NOT EXISTS idx_leave_requests_tenant_employee
    ON leave_requests (tenant_id, employee_id, requested_at DESC);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'leave_requests'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'requested_at'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN requested_at timestamptz NOT NULL DEFAULT timezone('utc', now());
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'review_note'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN review_note text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'reviewed_by'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN reviewed_by uuid;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'reviewed_at'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN reviewed_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'half_day_slot'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN half_day_slot text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'attachment_names'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN attachment_names text[] NOT NULL DEFAULT ARRAY[]::text[];
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'leave_requests' AND column_name = 'cancelled_at'
    ) THEN
      ALTER TABLE leave_requests ADD COLUMN cancelled_at timestamptz;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM pg_constraint
      WHERE conname = 'chk_leave_requests_half_day_slot'
        AND conrelid = 'leave_requests'::regclass
    ) THEN
      ALTER TABLE leave_requests
        ADD CONSTRAINT chk_leave_requests_half_day_slot
          CHECK (half_day_slot IS NULL OR half_day_slot IN ('am', 'pm'));
    END IF;
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'sites'
  ) THEN
    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'address'
    ) THEN
      ALTER TABLE sites ADD COLUMN address text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'place_id'
    ) THEN
      ALTER TABLE sites ADD COLUMN place_id text;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'is_active'
    ) THEN
      ALTER TABLE sites ADD COLUMN is_active boolean NOT NULL DEFAULT true;
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'created_at'
    ) THEN
      ALTER TABLE sites ADD COLUMN created_at timestamptz NOT NULL DEFAULT timezone('utc', now());
    END IF;

    IF NOT EXISTS (
      SELECT 1
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'sites' AND column_name = 'updated_at'
    ) THEN
      ALTER TABLE sites ADD COLUMN updated_at timestamptz NOT NULL DEFAULT timezone('utc', now());
    END IF;

    CREATE INDEX IF NOT EXISTS idx_sites_tenant_active
      ON sites (tenant_id, is_active, site_code);
    CREATE INDEX IF NOT EXISTS idx_sites_tenant_site_code
      ON sites (tenant_id, site_code);
    CREATE INDEX IF NOT EXISTS idx_sites_tenant_company
      ON sites (tenant_id, company_id, site_code);
  END IF;
END $$;
