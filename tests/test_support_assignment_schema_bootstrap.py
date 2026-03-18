from pathlib import Path
import unittest


ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "migrations" / "001_init.sql"


class SupportAssignmentSchemaBootstrapTest(unittest.TestCase):
    def test_support_assignment_base_schema_uses_period_slot_model(self):
        text = SCHEMA_PATH.read_text(encoding="utf-8")

        self.assertIn("support_period text NOT NULL DEFAULT 'day'", text)
        self.assertIn("slot_index int NOT NULL DEFAULT 1", text)
        self.assertIn("source_ticket_id bigint", text)
        self.assertIn("source_event_uid text", text)
        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_support_assignment_tenant_site_date_period_slot",
            text,
        )
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS idx_support_assignment_source_ticket",
            text,
        )
        self.assertIn(
            "CREATE INDEX IF NOT EXISTS idx_support_assignment_source_event",
            text,
        )

    def test_support_assignment_base_schema_no_longer_recreates_legacy_name_unique_index(self):
        text = SCHEMA_PATH.read_text(encoding="utf-8")

        self.assertNotIn(
            "CREATE INDEX IF NOT EXISTS uq_support_assignment_tenant_site_date_name",
            text,
        )
        self.assertIn(
            "DROP INDEX IF EXISTS uq_support_assignment_tenant_site_date_name;",
            text,
        )


if __name__ == "__main__":
    unittest.main()
