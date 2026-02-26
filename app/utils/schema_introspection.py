from __future__ import annotations

import re
import threading
import time
from typing import Tuple

_CACHE_TTL_SECONDS = 300.0
_CACHE_LOCK = threading.Lock()
_COLUMN_EXISTS_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}
_SQL_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _normalize_identifier(raw: str | None) -> str:
    return str(raw or "").strip().lower()


def _is_safe_identifier(identifier: str) -> bool:
    return bool(_SQL_IDENTIFIER_RE.fullmatch(identifier))


def _query_column_exists_postgres(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return bool(cur.fetchone())


def _query_column_exists_sqlite(conn, table_name: str, column_name: str) -> bool:
    if not (_is_safe_identifier(table_name) and _is_safe_identifier(column_name)):
        return False
    with conn.cursor() as cur:
        cur.execute(f"PRAGMA table_info({table_name})")
        rows = cur.fetchall() or []
    for row in rows:
        name = ""
        if isinstance(row, dict):
            name = str(row.get("name") or "").strip().lower()
        elif isinstance(row, (list, tuple)) and len(row) > 1:
            name = str(row[1] or "").strip().lower()
        if name == column_name:
            return True
    return False


def table_column_exists(conn, table_name: str, column_name: str) -> bool:
    normalized_table = _normalize_identifier(table_name)
    normalized_column = _normalize_identifier(column_name)
    if not normalized_table or not normalized_column:
        return False

    cache_key = (normalized_table, normalized_column)
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _COLUMN_EXISTS_CACHE.get(cache_key)
        if cached and cached[0] > now:
            return cached[1]

    exists = False
    try:
        exists = _query_column_exists_postgres(conn, normalized_table, normalized_column)
    except Exception:
        try:
            exists = _query_column_exists_sqlite(conn, normalized_table, normalized_column)
        except Exception:
            exists = False

    with _CACHE_LOCK:
        _COLUMN_EXISTS_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, exists)
    return exists


def clear_table_column_exists_cache() -> None:
    with _CACHE_LOCK:
        _COLUMN_EXISTS_CACHE.clear()
