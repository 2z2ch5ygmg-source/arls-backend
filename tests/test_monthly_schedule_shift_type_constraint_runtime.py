from pathlib import Path
import unittest

from app.db import MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL
from app.routers.v1.schedules import _ensure_monthly_schedule_shift_type_constraint


class MonthlyScheduleShiftTypeConstraintRuntimeTests(unittest.TestCase):
    def test_runtime_repair_sql_allows_overtime(self):
        self.assertIn("'overtime'", MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL)
        self.assertIn("monthly_schedules_shift_type_check", MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL)

    def test_base_schema_constraint_allows_overtime(self):
        sql = (Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql").read_text(encoding="utf-8")
        self.assertIn("CONSTRAINT monthly_schedules_shift_type_check CHECK", sql)
        self.assertIn("'overtime'", sql)

    def test_apply_path_can_force_constraint_repair_with_live_cursor(self):
        class DummyCursor:
            def __init__(self):
                self.executed: list[str] = []

            def execute(self, sql, params=None):
                self.executed.append(sql)

        cur = DummyCursor()
        _ensure_monthly_schedule_shift_type_constraint(cur)
        self.assertEqual(len(cur.executed), 1)
        self.assertIn("monthly_schedules_shift_type_check", cur.executed[0])
        self.assertIn("'overtime'", cur.executed[0])


if __name__ == "__main__":
    unittest.main()
