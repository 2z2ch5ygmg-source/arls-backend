from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.v1 import groupware_foundation as groupware_foundation_router
from app.services.groupware_foundation import (
    GroupwareNotificationDispatcher,
    build_groupware_foundation_status,
)

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

class GroupwareFoundationPhase1Tests(unittest.TestCase):
    def test_groupware_foundation_migration_defines_surviving_phase1_tables(self):
        migration_sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "025_groupware_foundation.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS groupware_attachment_objects", migration_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS approval_documents", migration_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS leave_ledger", migration_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS certificate_requests", migration_sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS outbound_mail_jobs", migration_sql)

    def test_status_contract_excludes_retired_chat_and_meetings_groups(self):
        conn = _FakeConn(fetchall_queue=[[]])

        payload = build_groupware_foundation_status(conn)

        database_groups = payload["database"]["groups"]
        self.assertNotIn("chat", database_groups)
        self.assertNotIn("meetings", database_groups)
        self.assertEqual(
            sorted(database_groups),
            ["approvals", "attachments", "certificates", "leave", "mail"],
        )
        phase_names = [phase["name"] for phase in payload["rollout_phases"]]
        self.assertNotIn("messenger", phase_names)
        self.assertNotIn("video-and-rollout", phase_names)
        self.assertEqual([boundary["service"] for boundary in payload["service_boundaries"]], ["core-api"])
        self.assertEqual(list(payload["deployment_topology"].keys()), ["core_api"])

    def test_build_status_reports_ready_and_missing_groups(self):
        conn = _FakeConn(
            fetchall_queue=[
                [
                    {"table_name": "groupware_attachment_objects"},
                    {"table_name": "approval_forms"},
                    {"table_name": "approval_form_versions"},
                    {"table_name": "leave_policies"},
                    {"table_name": "leave_grants"},
                    {"table_name": "leave_ledger"},
                    {"table_name": "leave_balance_snapshots"},
                    {"table_name": "leave_blackout_rules"},
                    {"table_name": "holiday_calendar"},
                ]
            ]
        )

        payload = build_groupware_foundation_status(conn)

        self.assertEqual(payload["phase"], 1)
        self.assertTrue(payload["database"]["groups"]["attachments"]["ready"])
        self.assertFalse(payload["database"]["groups"]["approvals"]["ready"])
        self.assertIn(
            "approval_documents",
            payload["database"]["groups"]["approvals"]["missing_tables"],
        )
        self.assertTrue(payload["database"]["groups"]["leave"]["ready"])

    def test_notification_dispatcher_writes_in_app_notification(self):
        conn = _FakeConn(fetchone_queue=[None])
        dispatcher = GroupwareNotificationDispatcher(conn)

        notification_id = dispatcher.dispatch_in_app(
            tenant_id="tenant-1",
            user_id="user-1",
            message="결재 문서가 도착했습니다.",
            category="approval",
            dedupe_key="approval:doc-1",
            payload={"document_id": "doc-1"},
        )

        self.assertTrue(notification_id)
        self.assertEqual(len(conn.executed), 2)
        sql, params = conn.executed[1]
        self.assertIn("INSERT INTO in_app_notifications", sql)
        self.assertEqual(params[1], "tenant-1")
        self.assertEqual(params[2], "user-1")
        self.assertEqual(params[3], "결재 문서가 도착했습니다.")
        self.assertEqual(params[4], "approval")

    def test_notification_dispatcher_updates_existing_notification_without_on_conflict(self):
        conn = _FakeConn(fetchone_queue=[{"id": "notif-1"}])
        dispatcher = GroupwareNotificationDispatcher(conn)

        notification_id = dispatcher.dispatch_in_app(
            tenant_id="tenant-1",
            user_id="user-1",
            message="이미 있는 알림을 갱신합니다.",
            category="approval",
            dedupe_key="approval:doc-1",
            payload={"document_id": "doc-1"},
        )

        self.assertEqual(notification_id, "notif-1")
        self.assertEqual(len(conn.executed), 2)
        lookup_sql, lookup_params = conn.executed[0]
        update_sql, update_params = conn.executed[1]
        self.assertIn("SELECT id", lookup_sql)
        self.assertEqual(lookup_params, ("tenant-1", "user-1", "approval:doc-1"))
        self.assertIn("UPDATE in_app_notifications", update_sql)
        self.assertEqual(update_params[0], "이미 있는 알림을 갱신합니다.")
        self.assertEqual(update_params[1], "approval")
        self.assertEqual(update_params[3], "notif-1")

    def test_status_route_rejects_non_admin_user(self):
        with self.assertRaises(HTTPException) as exc_info:
            groupware_foundation_router.get_groupware_foundation_status(
                conn=_FakeConn(),
                user={"role": "officer"},
            )

        self.assertEqual(exc_info.exception.status_code, 403)

    def test_compatibility_route_returns_payload_for_admin(self):
        stub = {"phase": 1, "legacy_compatibility_routes": [{"legacy_prefix": "/api/v1/leaves"}]}
        with patch.object(
            groupware_foundation_router,
            "build_groupware_compatibility_payload",
            return_value=stub,
        ) as build_payload:
            result = groupware_foundation_router.get_groupware_foundation_compatibility(
                conn=_FakeConn(),
                user={"role": "hq_admin"},
            )

        build_payload.assert_called_once()
        self.assertEqual(result["phase"], 1)
        self.assertEqual(result["legacy_compatibility_routes"][0]["legacy_prefix"], "/api/v1/leaves")

if __name__ == "__main__":
    unittest.main()
