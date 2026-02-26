from __future__ import annotations

import re
from typing import Any, Iterable


_PLACEHOLDER_PATTERN = re.compile(r"(?<!%)%s|\?")


class SQLPlaceholderMismatchError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        placeholders: int,
        params_count: int,
        sql: str,
        params: tuple[Any, ...],
    ) -> None:
        super().__init__(f"SQL placeholder mismatch: {placeholders} vs {params_count}")
        self.stage = stage
        self.placeholders = placeholders
        self.params_count = params_count
        self.sql = sql
        self.params = params
        self.code = "SQL_MISMATCH"


def _normalize_params(params: Any) -> tuple[Any, ...]:
    if params is None:
        return tuple()
    if isinstance(params, tuple):
        return params
    if isinstance(params, list):
        return tuple(params)
    if isinstance(params, (str, bytes, bytearray)):
        return (params,)
    if isinstance(params, dict):
        return tuple(params.values())
    if isinstance(params, Iterable):
        return tuple(params)
    return (params,)


def count_sql_placeholders(sql: str) -> int:
    return len(_PLACEHOLDER_PATTERN.findall(str(sql or "")))


def exec_checked(cursor, sql: str, params: Any = None, *, stage: str = ""):
    param_tuple = _normalize_params(params)
    placeholders = count_sql_placeholders(sql)
    params_count = len(param_tuple)
    if placeholders != params_count:
        print(f"[SQL_MISMATCH] stage={stage} placeholders={placeholders} params={params_count}")
        print(f"[SQL_MISMATCH] sql={sql}")
        print(f"[SQL_MISMATCH] params={param_tuple}")
        raise SQLPlaceholderMismatchError(
            stage=stage,
            placeholders=placeholders,
            params_count=params_count,
            sql=str(sql),
            params=param_tuple,
        )

    try:
        return cursor.execute(sql, param_tuple)
    except Exception as exc:
        print(
            f"[SQL_EXEC_ERROR] stage={stage} placeholders={placeholders} params={params_count} "
            f"error={exc!r}"
        )
        print(f"[SQL_EXEC_ERROR] sql={sql}")
        print(f"[SQL_EXEC_ERROR] params={param_tuple}")
        raise
