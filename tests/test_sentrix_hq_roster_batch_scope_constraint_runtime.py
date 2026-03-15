from pathlib import Path
import unittest

from app.db import SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL
from app.routers.v1.schedules import _ensure_sentrix_support_hq_roster_batch_scope_constraint


class SentrixHqRosterBatchScopeConstraintRuntimeTests(unittest.TestCase):
    def test_runtime_repair_sql_allows_selected_scope(self):
        self.assertIn("'selected'", SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL)
        self.assertIn(
            "chk_sentrix_support_hq_roster_batches_scope",
            SENTRIX_SUPPORT_HQ_BATCH_SCOPE_CONSTRAINT_SQL,
        )

    def test_incremental_schema_constraint_allows_selected_scope(self):
        sql = (
            Path(__file__).resolve().parent.parent / "migrations" / "012_sentrix_hq_roster_batches.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("CONSTRAINT chk_sentrix_support_hq_roster_batches_scope", sql)
        self.assertIn("'selected'", sql)

    def test_runtime_repair_executes_constraint_sql(self):
        class DummyCursor:
            def __init__(self):
                self.executed: list[str] = []

            def execute(self, sql, params=None):
                self.executed.append(sql)

        cur = DummyCursor()
        _ensure_sentrix_support_hq_roster_batch_scope_constraint(cur)
        self.assertEqual(len(cur.executed), 1)
        self.assertIn("chk_sentrix_support_hq_roster_batches_scope", cur.executed[0])
        self.assertIn("'selected'", cur.executed[0])


if __name__ == "__main__":
    unittest.main()
