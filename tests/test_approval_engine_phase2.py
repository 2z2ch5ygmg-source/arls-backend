from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from app.services import approval_engine


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


class _FakeDispatcher:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    def dispatch_in_app(self, **kwargs):
        self.calls.append(kwargs)
        return "notification-1"


class _FakeAuditService:
    def __init__(self, conn) -> None:
        self.conn = conn
        self.calls: list[dict[str, object]] = []

    def write_event(self, **kwargs):
        self.calls.append(kwargs)


class ApprovalEnginePhase2Tests(unittest.TestCase):
    def test_approval_line_rules_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "026_approval_line_rules.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS approval_line_rules", sql)
        self.assertIn("uq_approval_line_rules_tenant_form_order", sql)
        self.assertIn("scope_type IN ('tenant', 'site', 'site_or_tenant')", sql)

    def test_create_document_inserts_document_steps_and_submit_action(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(approval_engine, "ensure_default_approval_forms"), \
             patch.object(approval_engine, "ensure_default_approval_line_rules"), \
             patch.object(
                 approval_engine,
                 "_fetch_form_bundle",
                 return_value={
                     "form_id": "form-1",
                     "form_version_id": "ver-1",
                     "display_name": "휴가신청",
                 },
             ), \
             patch.object(
                 approval_engine,
                 "_resolve_auto_approval_steps",
                 return_value=[
                     {
                         "step_order": 1,
                         "approver_user_id": "approver-1",
                         "approver_employee_id": "emp-approver-1",
                         "meta_json": {"scope_type": "tenant"},
                     }
                 ],
             ), \
             patch.object(
                 approval_engine,
                 "_fetch_first_pending_step",
                 return_value={"id": "step-1", "approver_user_id": "approver-1", "step_order": 1},
             ), \
             patch.object(
                 approval_engine,
                 "fetch_approval_document_detail",
                 return_value={"id": "doc-1", "status": "in_review", "title": "휴가신청"},
             ), \
             patch.object(
                 approval_engine,
                 "queue_approval_notification_mail",
                 return_value={"id": "mail-job-1"},
             ) as queue_mail, \
             patch.object(approval_engine, "GroupwareNotificationDispatcher", return_value=dispatcher), \
             patch.object(approval_engine, "GroupwareAuditService", return_value=audit):
            result = approval_engine.create_approval_document(
                conn,
                tenant_id="tenant-1",
                form_key="leave_request",
                title="휴가신청",
                requester_user_id="user-1",
                requester_role="officer",
                employee_id="emp-1",
                site_id="site-1",
                payload={"leave_type": "annual"},
                submit=True,
                legacy_source_type="leave_request",
                legacy_source_id="legacy-1",
            )

        self.assertEqual(result["status"], "in_review")
        self.assertTrue(any("INSERT INTO approval_documents" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO approval_steps" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO approval_actions" in sql for sql, _ in conn.executed))
        self.assertEqual(dispatcher.calls[0]["user_id"], "approver-1")
        queue_mail.assert_called_once()

    def test_record_approve_action_promotes_next_step(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(
            approval_engine,
            "_fetch_document_row",
            return_value={"id": "doc-1", "title": "근태정정", "status": "in_review"},
        ), \
             patch.object(
                 approval_engine,
                 "_fetch_first_pending_step",
                 side_effect=[
                     {"id": "step-1", "step_order": 1, "approver_user_id": "reviewer-1"},
                     {"id": "step-2", "step_order": 2, "approver_user_id": "reviewer-2"},
                 ],
             ), \
             patch.object(
                 approval_engine,
                 "_fetch_next_queued_step",
                 return_value={"id": "step-2", "step_order": 2, "approver_user_id": "reviewer-2"},
             ), \
             patch.object(
                 approval_engine,
                 "fetch_approval_document_detail",
                 return_value={"id": "doc-1", "status": "in_review", "title": "근태정정", "form_key": "attendance_correction"},
             ), \
             patch.object(
                 approval_engine,
                 "queue_approval_notification_mail",
                 return_value={"id": "mail-job-2"},
             ) as queue_mail, \
             patch.object(approval_engine, "GroupwareNotificationDispatcher", return_value=dispatcher), \
             patch.object(approval_engine, "GroupwareAuditService", return_value=audit):
            result = approval_engine.record_approval_action(
                conn,
                tenant_id="tenant-1",
                document_id="doc-1",
                actor_user_id="reviewer-1",
                actor_role="hq_admin",
                action_type="approve",
                comment_text="확인 완료",
            )

        self.assertEqual(result["status"], "in_review")
        self.assertTrue(any("UPDATE approval_steps" in sql for sql, _ in conn.executed))
        self.assertTrue(any("UPDATE approval_documents" in sql for sql, _ in conn.executed))
        self.assertEqual(dispatcher.calls[0]["user_id"], "reviewer-2")
        queue_mail.assert_called_once()

    def test_sync_legacy_status_updates_existing_document(self):
        conn = _FakeConn()
        audit = _FakeAuditService(conn)

        with patch.object(
            approval_engine,
            "_find_legacy_document",
            return_value={"id": "doc-legacy-1", "status": "in_review"},
        ), \
             patch.object(
                 approval_engine,
                 "_fetch_first_pending_step",
                 return_value={"id": "step-1", "approver_user_id": "reviewer-1"},
             ), \
             patch.object(
                 approval_engine,
                 "fetch_approval_document_detail",
                 return_value={"id": "doc-legacy-1", "status": "rejected"},
             ), \
             patch.object(approval_engine, "GroupwareAuditService", return_value=audit):
            result = approval_engine.sync_legacy_approval_status(
                conn,
                tenant_id="tenant-1",
                legacy_source_type="leave_request",
                legacy_source_id="legacy-1",
                status_value="rejected",
                actor_user_id="reviewer-1",
                actor_role="hq_admin",
                comment_text="반려",
            )

        self.assertEqual(result["status"], "rejected")
        self.assertTrue(any("UPDATE approval_documents" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO approval_actions" in sql for sql, _ in conn.executed))

    def test_record_approval_action_syncs_legacy_leave_and_ledger(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(
            approval_engine,
            "_fetch_document_row",
            return_value={
                "id": "doc-legacy-1",
                "title": "휴가신청",
                "status": "in_review",
                "legacy_source_type": "leave_request",
                "legacy_source_id": "leave-legacy-1",
                "tenant_id": "tenant-1",
            },
        ), patch.object(
            approval_engine,
            "_fetch_first_pending_step",
            side_effect=[
                {"id": "step-1", "step_order": 1, "approver_user_id": "reviewer-1"},
                None,
            ],
        ), patch.object(
            approval_engine,
            "_fetch_next_queued_step",
            return_value=None,
        ), patch.object(
            approval_engine,
            "_fetch_legacy_leave_row",
            return_value={
                "id": "leave-legacy-1",
                "tenant_id": "tenant-1",
                "employee_id": "emp-1",
                "leave_type": "annual",
                "status": "approved",
                "start_at": date(2026, 3, 1),
                "end_at": date(2026, 3, 1),
                "half_day_slot": None,
            },
        ), patch.object(
            approval_engine,
            "sync_leave_request_ledger",
            return_value={"remaining_days": 14.0},
        ) as sync_ledger, patch.object(
            approval_engine,
            "fetch_approval_document_detail",
            return_value={"id": "doc-legacy-1", "status": "approved", "title": "휴가신청", "form_key": "leave_request"},
        ), patch.object(
            approval_engine,
            "GroupwareNotificationDispatcher",
            return_value=dispatcher,
        ), patch.object(
            approval_engine,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = approval_engine.record_approval_action(
                conn,
                tenant_id="tenant-1",
                document_id="doc-legacy-1",
                actor_user_id="reviewer-1",
                actor_role="hq_admin",
                action_type="approve",
                comment_text="승인",
            )

        self.assertEqual(result["status"], "approved")
        self.assertTrue(any("UPDATE leave_requests" in sql for sql, _ in conn.executed))
        sync_ledger.assert_called_once()

    def test_record_final_approval_queues_requester_mail(self):
        conn = _FakeConn()
        dispatcher = _FakeDispatcher(conn)
        audit = _FakeAuditService(conn)

        with patch.object(
            approval_engine,
            "_fetch_document_row",
            return_value={
                "id": "doc-1",
                "title": "증명서발급",
                "status": "in_review",
                "legacy_source_type": "employment_certificate_request",
                "legacy_source_id": "legacy-cert-1",
                "tenant_id": "tenant-1",
                "requester_user_id": "requester-1",
            },
        ), patch.object(
            approval_engine,
            "_fetch_first_pending_step",
            side_effect=[
                {"id": "step-1", "step_order": 1, "approver_user_id": "reviewer-1"},
                None,
            ],
        ), patch.object(
            approval_engine,
            "_fetch_next_queued_step",
            return_value=None,
        ), patch.object(
            approval_engine,
            "_sync_legacy_leave_request_from_approval",
            return_value=None,
        ), patch.object(
            approval_engine,
            "fetch_approval_document_detail",
            return_value={
                "id": "doc-1",
                "status": "approved",
                "title": "증명서발급",
                "form_key": "employment_certificate",
                "form_display_name": "증명서발급",
            },
        ), patch.object(
            approval_engine,
            "queue_approval_notification_mail",
            return_value={"id": "mail-job-3"},
        ) as queue_mail, patch.object(
            approval_engine,
            "GroupwareNotificationDispatcher",
            return_value=dispatcher,
        ), patch.object(
            approval_engine,
            "GroupwareAuditService",
            return_value=audit,
        ):
            result = approval_engine.record_approval_action(
                conn,
                tenant_id="tenant-1",
                document_id="doc-1",
                actor_user_id="reviewer-1",
                actor_role="hq_admin",
                action_type="approve",
                comment_text="승인",
            )

        self.assertEqual(result["status"], "approved")
        queue_mail.assert_called_once()


if __name__ == "__main__":
    unittest.main()
