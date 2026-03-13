from pathlib import Path
import unittest

from app.db import MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL


class MonthlyScheduleShiftTypeConstraintRuntimeTests(unittest.TestCase):
    def test_runtime_repair_sql_allows_overtime(self):
        self.assertIn("'overtime'", MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL)
        self.assertIn("monthly_schedules_shift_type_check", MONTHLY_SCHEDULE_SHIFT_TYPE_CONSTRAINT_SQL)

    def test_base_schema_constraint_allows_overtime(self):
        sql = (Path(__file__).resolve().parent.parent / "migrations" / "001_init.sql").read_text(encoding="utf-8")
        self.assertIn("CONSTRAINT monthly_schedules_shift_type_check CHECK", sql)
        self.assertIn("'overtime'", sql)


if __name__ == "__main__":
    unittest.main()
