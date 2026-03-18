from pathlib import Path
import unittest

from app.routers.v1.schedules import _build_schedule_import_mapping_summary


class ScheduleTemplateDeleteRuntimeTests(unittest.TestCase):
    def test_deleted_template_mapping_entry_requires_profile_rebuild_message(self):
        summary = _build_schedule_import_mapping_summary({
            "profile_id": "profile-1",
            "profile_name": "기본 월간 업로드 매핑",
            "is_active": False,
            "entries": [
                {
                    "row_type": "day",
                    "numeric_hours": 10,
                    "template_id": None,
                    "template_name": None,
                    "template_site_code": None,
                }
            ],
        })

        self.assertEqual(summary["entry_count"], 1)
        self.assertEqual(summary["entries"][0]["status"], "invalid")
        self.assertEqual(summary["entries"][0]["issue_code"], "CANNOT_RESOLVE_TEMPLATE")
        self.assertIn("삭제되어 프로필을 다시 설정", summary["entries"][0]["issue_message"])

    def test_template_delete_migration_relaxes_mapping_fk_to_set_null(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "011_schedule_template_delete_cascade.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("ALTER COLUMN template_id DROP NOT NULL", sql)
        self.assertIn("DROP CONSTRAINT IF EXISTS schedule_import_mapping_entries_template_id_fkey", sql)
        self.assertIn("ON DELETE SET NULL", sql)


if __name__ == "__main__":
    unittest.main()
