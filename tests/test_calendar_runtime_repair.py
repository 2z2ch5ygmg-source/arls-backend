from __future__ import annotations

import unittest

from app.db import ensure_calendar_runtime_shape


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


class CalendarRuntimeRepairTests(unittest.TestCase):
    def test_ensure_calendar_runtime_shape_executes_phase_repairs(self):
        conn = _ConnectionStub()

        ensure_calendar_runtime_shape(conn)

        executed_sql = "\n".join(conn.cursor_ctx.executed)
        self.assertIn("ALTER TABLE calendar_events", executed_sql)
        self.assertIn("resource_id", executed_sql)
        self.assertIn("default_container_id", executed_sql)
        self.assertIn("selected_external_calendars_json", executed_sql)
        self.assertIn("approval_policy", executed_sql)
        self.assertIn("assignment_mode", executed_sql)
        self.assertIn("custom_fields_json", executed_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS calendar_comments", executed_sql)


if __name__ == "__main__":
    unittest.main()
