from pathlib import Path
import unittest

from app.routers.v1.schedules import ALLOWED_SHIFT_TYPES


class MonthlyScheduleShiftTypeMigrationTests(unittest.TestCase):
    def test_runtime_shift_types_include_overtime(self):
        self.assertIn("overtime", ALLOWED_SHIFT_TYPES)

    def test_incremental_migration_allows_overtime(self):
        migration_sql = Path(__file__).resolve().parent.parent / "migrations" / "017_monthly_schedules_allow_overtime_shift_type.sql"
        sql = migration_sql.read_text(encoding="utf-8")
        self.assertIn("'overtime'", sql)


if __name__ == "__main__":
    unittest.main()
