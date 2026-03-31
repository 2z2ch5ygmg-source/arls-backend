from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"
MIGRATIONS_DIR = SCHEMA_SQL_PATH.parent

MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'monthly_schedules'
  ) THEN
    ALTER TABLE monthly_schedules
      DROP CONSTRAINT IF EXISTS monthly_schedules_shift_type_check;

    ALTER TABLE monthly_schedules
      ADD CONSTRAINT monthly_schedules_shift_type_check
      CHECK (
        lower(COALESCE(NULLIF(trim(shift_type), ''), 'day')) IN ('day', 'overtime', 'night', 'off', 'holiday')
      ) NOT VALID;
  END IF;
END
$$;
"""

SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'sentrix_support_hq_roster_batches'
  ) THEN
    ALTER TABLE sentrix_support_hq_roster_batches
      DROP CONSTRAINT IF EXISTS chk_sentrix_support_hq_roster_batches_scope;

    ALTER TABLE sentrix_support_hq_roster_batches
      ADD CONSTRAINT chk_sentrix_support_hq_roster_batches_scope
      CHECK (download_scope IN ('all', 'site', 'selected')) NOT VALID;
  END IF;
END
$$;
"""

SCHEDULE_IMPORT_RAW_WORKBOOK_COLUMNS_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'schedule_import_batches'
  ) THEN
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_bytes bytea;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_mime_type text;
    ALTER TABLE schedule_import_batches
      ADD COLUMN IF NOT EXISTS raw_workbook_sha256 text;
  END IF;
END
$$;
"""

CALENDAR_PHASE2_RESOURCE_COLUMN_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_events'
  ) AND EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_resources'
  ) THEN
    ALTER TABLE calendar_events
      ADD COLUMN IF NOT EXISTS resource_id uuid REFERENCES calendar_resources(id) ON DELETE SET NULL;

    CREATE INDEX IF NOT EXISTS idx_calendar_events_resource_window
      ON calendar_events (resource_id, starts_at, ends_at)
      WHERE resource_id IS NOT NULL;
  END IF;
END
$$;
"""

CALENDAR_PHASE4_SYNC_COLUMNS_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_sync_connections'
  ) AND EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_containers'
  ) THEN
    ALTER TABLE calendar_sync_connections
      ADD COLUMN IF NOT EXISTS default_container_id uuid NULL REFERENCES calendar_containers(id) ON DELETE SET NULL;

    ALTER TABLE calendar_sync_connections
      ADD COLUMN IF NOT EXISTS selected_external_calendars_json jsonb NOT NULL DEFAULT '[]'::jsonb;

    ALTER TABLE calendar_sync_connections
      ADD COLUMN IF NOT EXISTS last_sync_error text NULL;

    CREATE INDEX IF NOT EXISTS idx_calendar_sync_connections_default_container_id
      ON calendar_sync_connections(default_container_id);
  END IF;
END
$$;
"""

CALENDAR_PHASE5_OPS_COLUMNS_SQL = """
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_booking_links'
  ) THEN
    ALTER TABLE calendar_booking_links
      ADD COLUMN IF NOT EXISTS approval_policy text NOT NULL DEFAULT 'instant',
      ADD COLUMN IF NOT EXISTS assignment_mode text NOT NULL DEFAULT 'single_host';
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_events'
  ) THEN
    ALTER TABLE calendar_events
      ADD COLUMN IF NOT EXISTS custom_fields_json jsonb NOT NULL DEFAULT '[]'::jsonb;
  END IF;

  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'calendar_events'
  ) THEN
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
  END IF;
END
$$;
"""

_pool: ConnectionPool | None = None


def init_pool() -> ConnectionPool:
    global _pool
    if _pool is not None:
        return _pool

    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is required")

    _pool = ConnectionPool(conninfo=settings.database_url, max_size=15, min_size=1, kwargs={"autocommit": False})
    _migrate_and_seed()
    return _pool


def _migrate_and_seed() -> None:
    if not SCHEMA_SQL_PATH.exists():
        return

    conn = connect(settings.database_url, row_factory=dict_row)
    try:
        with conn:
            _apply_base_schema(conn)
            _apply_incremental_migrations(conn)
            _repair_runtime_constraints(conn)
            conn.commit()
    finally:
        conn.close()


def _apply_base_schema(conn) -> None:
    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    if not sql.strip():
        return
    with conn.cursor() as cur:
        cur.execute(sql)


def _ensure_migration_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name text PRIMARY KEY,
              applied_at timestamptz NOT NULL DEFAULT timezone('utc', now())
            )
            """
        )


def _applied_migration_names(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM schema_migrations")
        rows = cur.fetchall() or []
    return {str(row.get("name") or "").strip() for row in rows if str(row.get("name") or "").strip()}


def _list_incremental_migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    files = sorted(path for path in MIGRATIONS_DIR.glob("*.sql") if path.is_file())
    return [path for path in files if path.name != SCHEMA_SQL_PATH.name]


def _apply_incremental_migrations(conn) -> None:
    _ensure_migration_table(conn)
    applied = _applied_migration_names(conn)
    for path in _list_incremental_migration_files():
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        if sql.strip():
            with conn.cursor() as cur:
                cur.execute(sql)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO schema_migrations (name)
                VALUES (%s)
                ON CONFLICT (name) DO NOTHING
                """,
                (path.name,),
            )


def _repair_runtime_constraints(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEDULE_IMPORT_RAW_WORKBOOK_COLUMNS_SQL)
        cur.execute(MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL)
        cur.execute(SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL)
        cur.execute(CALENDAR_PHASE2_RESOURCE_COLUMN_SQL)
        cur.execute(CALENDAR_PHASE4_SYNC_COLUMNS_SQL)
        cur.execute(CALENDAR_PHASE5_OPS_COLUMNS_SQL)


def ensure_schedule_import_raw_workbook_columns(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEDULE_IMPORT_RAW_WORKBOOK_COLUMNS_SQL)


def ensure_calendar_runtime_shape(conn) -> None:
    if not hasattr(conn, "cursor"):
        return
    with conn.cursor() as cur:
        cur.execute(CALENDAR_PHASE2_RESOURCE_COLUMN_SQL)
        cur.execute(CALENDAR_PHASE4_SYNC_COLUMNS_SQL)
        cur.execute(CALENDAR_PHASE5_OPS_COLUMNS_SQL)


def get_pool() -> ConnectionPool:
    return init_pool()


@contextmanager
def get_connection():
    pool = get_pool()
    with pool.connection() as conn:
        conn.row_factory = dict_row
        with conn:
            yield conn


def fetch_one(conn, query: str, params: tuple = ()):  # pragma: no cover - convenience
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchone()


def fetch_all(conn, query: str, params: tuple = ()):  # pragma: no cover - convenience
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, params)
        return cur.fetchall()
