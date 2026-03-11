from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"
MIGRATIONS_DIR = SCHEMA_SQL_PATH.parent

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
