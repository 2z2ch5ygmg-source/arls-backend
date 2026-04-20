from pathlib import Path
import inspect
import unittest

from app.db import SCHEDULE_TEMPLATE_DELETE_CONSTRAINT_SQL
from app.routers.v1.schedules import _build_schedule_import_mapping_summary
from app.routers.v1.schedules import delete_schedule_work_template
from app.routers.v1.schedules import _unlink_schedule_template_mapping_entries


class _RecordingCursor:
    def __init__(self, *, fail_update: bool = False):
        self.fail_update = fail_update
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, sql, params=None):
        normalized_sql = " ".join(str(sql).split())
        self.calls.append((normalized_sql, params))
        if self.fail_update and normalized_sql.startswith(
            "UPDATE schedule_import_mapping_entries e"
        ):
            raise RuntimeError("template_id is not nullable")


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

    def test_template_delete_runtime_repair_relaxes_mapping_fk_to_set_null(self):
        self.assertIn("ALTER COLUMN template_id DROP NOT NULL", SCHEDULE_TEMPLATE_DELETE_CONSTRAINT_SQL)
        self.assertIn(
            "DROP CONSTRAINT IF EXISTS schedule_import_mapping_entries_template_id_fkey",
            SCHEDULE_TEMPLATE_DELETE_CONSTRAINT_SQL,
        )
        self.assertIn("ON DELETE SET NULL", SCHEDULE_TEMPLATE_DELETE_CONSTRAINT_SQL)

    def test_unlink_mapping_entries_nulls_template_before_delete(self):
        cur = _RecordingCursor()

        _unlink_schedule_template_mapping_entries(
            cur,
            tenant_id="tenant-1",
            template_id="template-1",
        )

        sql_calls = [call[0] for call in cur.calls]
        self.assertTrue(sql_calls[0].startswith("SAVEPOINT"))
        self.assertTrue(
            any(call.startswith("UPDATE schedule_import_mapping_entries e") for call in sql_calls)
        )
        self.assertTrue(sql_calls[-1].startswith("RELEASE SAVEPOINT"))
        self.assertFalse(
            any(call.startswith("DELETE FROM schedule_import_mapping_entries e") for call in sql_calls)
        )

    def test_unlink_mapping_entries_deletes_on_legacy_not_null_shape(self):
        cur = _RecordingCursor(fail_update=True)

        _unlink_schedule_template_mapping_entries(
            cur,
            tenant_id="tenant-1",
            template_id="template-1",
        )

        sql_calls = [call[0] for call in cur.calls]
        self.assertTrue(
            any(call.startswith("ROLLBACK TO SAVEPOINT") for call in sql_calls)
        )
        self.assertTrue(
            any(call.startswith("DELETE FROM schedule_import_mapping_entries e") for call in sql_calls)
        )

    def test_delete_profile_lookup_avoids_distinct_order_by_runtime_error(self):
        source = inspect.getsource(delete_schedule_work_template)

        self.assertNotIn("SELECT DISTINCT p.id, p.profile_name", source)
        self.assertIn("GROUP BY p.id, p.profile_name", source)
        self.assertIn("ORDER BY MAX(p.updated_at) DESC", source)


if __name__ == "__main__":
    unittest.main()
