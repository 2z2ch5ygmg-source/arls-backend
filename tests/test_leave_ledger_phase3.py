from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services import leave_ledger


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchone(self):
        if self.conn.fetchone_queue:
            return self.conn.fetchone_queue.pop(0)
        return None

    def fetchall(self):
        if self.conn.fetchall_queue:
            return self.conn.fetchall_queue.pop(0)
        return []


class _FakeConn:
    def __init__(self, *, fetchone_queue=None, fetchall_queue=None) -> None:
        self.fetchone_queue = list(fetchone_queue or [])
        self.fetchall_queue = list(fetchall_queue or [])
        self.executed: list[tuple[str, object]] = []

    def cursor(self):
        return _FakeCursor(self)


class _FakeAuditService:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    def write_event(self, **kwargs):
        self.calls.append(kwargs)


class LeaveLedgerPhase3Tests(unittest.TestCase):
    def test_reference_key_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "027_leave_ledger_reference_keys.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("ALTER TABLE leave_ledger ADD COLUMN reference_key", sql)
        self.assertIn("uq_leave_grants_tenant_employee_reference", sql)
        self.assertIn("uq_leave_ledger_tenant_employee_reference", sql)

    def test_bucket_leave_duration_by_year_handles_cross_year_and_half_day(self):
        self.assertEqual(
            leave_ledger.bucket_leave_duration_by_year(date(2026, 3, 1), date(2026, 3, 1), "am"),
            {2026: Decimal("0.5")},
        )
        self.assertEqual(
            leave_ledger.bucket_leave_duration_by_year(date(2026, 12, 31), date(2027, 1, 2), None),
            {2026: Decimal("1.0"), 2027: Decimal("2.0")},
        )

    def test_compute_balance_summary_is_deterministic(self):
        conn = _FakeConn()
        with patch.object(
            leave_ledger,
            "ensure_default_leave_policy",
            return_value={"id": "policy-1", "policy_key": "annual_default", "display_name": "기본 연차 정책"},
        ), patch.object(
            leave_ledger,
            "ensure_default_leave_grant",
            return_value={"id": "grant-1"},
        ), patch.object(
            leave_ledger,
            "_aggregate_leave_balance_components",
            return_value={
                "granted_days": Decimal("15.0"),
                "consumed_days": Decimal("3.0"),
                "restored_days": Decimal("1.0"),
                "granted_ledger_days": Decimal("0"),
            },
        ), patch.object(
            leave_ledger,
            "_upsert_leave_balance_snapshot",
            return_value=None,
        ):
            summary = leave_ledger.compute_employee_leave_balance_summary(
                conn,
                tenant_id="tenant-1",
                employee_id="emp-1",
                grant_year=2026,
                actor_user_id="user-1",
            )

        self.assertEqual(summary["granted_days"], 15.0)
        self.assertEqual(summary["used_days"], 2.0)
        self.assertEqual(summary["remaining_days"], 13.0)

    def test_approved_leave_request_creates_consume_entries(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)
        leave_row = {
            "id": "leave-1",
            "tenant_id": "tenant-1",
            "employee_id": "emp-1",
            "leave_type": "annual",
            "status": "approved",
            "start_at": date(2026, 3, 1),
            "end_at": date(2026, 3, 2),
            "half_day_slot": None,
        }

        with patch.object(
            leave_ledger,
            "ensure_default_leave_policy",
            return_value={"id": "policy-1"},
        ), patch.object(
            leave_ledger,
            "ensure_default_leave_grant",
            return_value={"id": "grant-1"},
        ), patch.object(
            leave_ledger,
            "_find_approval_document_id_for_leave",
            return_value="doc-1",
        ), patch.object(
            leave_ledger,
            "_leave_ledger_entry_exists",
            return_value=False,
        ), patch.object(
            leave_ledger,
            "compute_employee_leave_balance_summary",
            return_value={"remaining_days": 13.0, "used_days": 2.0},
        ), patch.object(
            leave_ledger,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = leave_ledger.sync_leave_request_ledger(
                conn,
                leave_row=leave_row,
                actor_user_id="user-1",
                actor_role="hq_admin",
            )

        self.assertEqual(result["remaining_days"], 13.0)
        self.assertTrue(any("INSERT INTO leave_ledger" in sql for sql, _ in conn.executed))
        _, params = next((sql, params) for sql, params in conn.executed if "INSERT INTO leave_ledger" in sql)
        self.assertEqual(params[6], "leave:leave-1:consume:2026")
        self.assertEqual(str(params[7]), "consume")

    def test_cancelled_leave_request_creates_restore_entries(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)
        leave_row = {
            "id": "leave-2",
            "tenant_id": "tenant-1",
            "employee_id": "emp-1",
            "leave_type": "annual",
            "status": "cancelled",
            "start_at": date(2026, 4, 10),
            "end_at": date(2026, 4, 10),
            "half_day_slot": "pm",
        }

        with patch.object(
            leave_ledger,
            "ensure_default_leave_policy",
            return_value={"id": "policy-1"},
        ), patch.object(
            leave_ledger,
            "_find_approval_document_id_for_leave",
            return_value="doc-2",
        ), patch.object(
            leave_ledger,
            "_leave_ledger_entry_exists",
            side_effect=[True, False],
        ), patch.object(
            leave_ledger,
            "compute_employee_leave_balance_summary",
            return_value={"remaining_days": 15.0, "used_days": 0.0},
        ), patch.object(
            leave_ledger,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = leave_ledger.sync_leave_request_ledger(
                conn,
                leave_row=leave_row,
                actor_user_id="user-1",
                actor_role="hq_admin",
            )

        self.assertEqual(result["remaining_days"], 15.0)
        self.assertTrue(any("INSERT INTO leave_ledger" in sql for sql, _ in conn.executed))
        _, params = next((sql, params) for sql, params in conn.executed if "INSERT INTO leave_ledger" in sql)
        self.assertEqual(params[6], "leave:leave-2:restore:2026")
        self.assertEqual(str(params[7]), "restore")


if __name__ == "__main__":
    unittest.main()
