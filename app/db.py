from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings

SCHEMA_SQL_PATH = Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql"

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

    sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    if not sql.strip():
        return

    conn = connect(settings.database_url, row_factory=dict_row)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    finally:
        conn.close()


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
