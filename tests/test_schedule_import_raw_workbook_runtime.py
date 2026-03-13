from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.db import ensure_schedule_import_raw_workbook_columns
from app.routers.v1.schedules import _load_schedule_import_batch_raw_workbook


class _CursorContext:
    def __init__(self):
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.executed.append(str(sql))


class _ConnectionStub:
    def __init__(self):
        self.cursor_ctx = _CursorContext()

    def cursor(self):
        return self.cursor_ctx


class ScheduleImportRawWorkbookRuntimeTests(unittest.TestCase):
    def test_ensure_schedule_import_raw_workbook_columns_executes_runtime_repair_sql(self):
        conn = _ConnectionStub()

        ensure_schedule_import_raw_workbook_columns(conn)

        executed_sql = "\n".join(conn.cursor_ctx.executed)
        self.assertIn("ALTER TABLE schedule_import_batches", executed_sql)
        self.assertIn("raw_workbook_bytes", executed_sql)
        self.assertIn("raw_workbook_mime_type", executed_sql)
        self.assertIn("raw_workbook_sha256", executed_sql)

    def test_load_raw_workbook_repairs_columns_before_column_check(self):
        conn = MagicMock()

        with patch("app.routers.v1.schedules.ensure_schedule_import_raw_workbook_columns") as ensure_columns, patch(
            "app.routers.v1.schedules.table_column_exists",
            return_value=False,
        ):
            result = _load_schedule_import_batch_raw_workbook(conn, tenant_id="tenant-1", batch_id="batch-1")

        self.assertIsNone(result)
        ensure_columns.assert_called_once_with(conn)


if __name__ == "__main__":
    unittest.main()
