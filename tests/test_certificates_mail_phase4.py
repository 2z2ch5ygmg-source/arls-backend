from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import patch

from app.services import certificates_mail


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


class CertificatesMailPhase4Tests(unittest.TestCase):
    def test_generic_certificate_phase4_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "031_certificates_generic_phase4.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("employment_status", sql)
        self.assertIn("loa_start_date", sql)
        self.assertIn("loa_end_date", sql)
        self.assertIn("submit_to", sql)
        self.assertIn("copy_count", sql)
        self.assertIn("mail_company_sent_at", sql)

    def test_phase4_migration_exists(self):
        sql = (
            Path(__file__).resolve().parent.parent
            / "migrations"
            / "028_certificate_mail_legacy_sync.sql"
        ).read_text(encoding="utf-8")

        self.assertIn("legacy_source_type", sql)
        self.assertIn("legacy_source_id", sql)
        self.assertIn("uq_certificate_requests_tenant_legacy_source", sql)
        self.assertIn("uq_certificate_issue_jobs_request", sql)

    def test_generic_certificate_type_definitions_are_live(self):
        definitions = {
            item["type_key"]: item
            for item in certificates_mail.CERTIFICATE_TYPE_DEFINITIONS
        }

        self.assertFalse(definitions["employment_certificate"]["requires_approval"])
        self.assertFalse(definitions["career_certificate"]["requires_approval"])
        self.assertTrue(definitions["retirement_certificate"]["requires_approval"])
        self.assertTrue(definitions["leave_of_absence_certificate"]["requires_approval"])
        self.assertFalse(definitions["employment_certificate"]["auto_mail_enabled"])
        self.assertFalse(definitions["career_certificate"]["auto_mail_enabled"])
        self.assertFalse(definitions["retirement_certificate"]["auto_mail_enabled"])
        self.assertFalse(definitions["leave_of_absence_certificate"]["auto_mail_enabled"])
        self.assertEqual(definitions["career_certificate"]["meta_json"].get("rollout"), "live")
        self.assertEqual(definitions["retirement_certificate"]["meta_json"].get("rollout"), "live")

    def test_certificate_type_eligibility_checks_status_only(self):
        employee_row = {
            "hire_date": "2024-01-01",
            "leave_date": "2026-03-01",
            "employment_status": "leave_of_absence",
            "loa_start_date": "2026-03-20",
            "loa_end_date": "2026-04-20",
        }
        available, reason = certificates_mail._certificate_type_eligibility(
            type_key="leave_of_absence_certificate",
            employee_row=employee_row,
            employee_email="user@example.com",
            company_archive_email="company@example.com",
        )
        self.assertTrue(available)
        self.assertIn(reason, (None, ""))

        unavailable, unavailable_reason = certificates_mail._certificate_type_eligibility(
            type_key="retirement_certificate",
            employee_row={"hire_date": "2024-01-01", "employment_status": "active"},
            employee_email="user@example.com",
            company_archive_email="company@example.com",
        )
        self.assertFalse(unavailable)
        self.assertIn("퇴직", unavailable_reason)

        no_mail, no_mail_reason = certificates_mail._certificate_type_eligibility(
            type_key="employment_certificate",
            employee_row={"hire_date": "2024-01-01", "employment_status": "active"},
            employee_email=None,
            company_archive_email=None,
        )
        self.assertTrue(no_mail)
        self.assertIn(no_mail_reason, (None, ""))

    def test_certificate_type_eligibility_positive_paths_for_career_and_retirement(self):
        career_available, career_reason = certificates_mail._certificate_type_eligibility(
            type_key="career_certificate",
            employee_row={"hire_date": "2024-01-01", "employment_status": "active"},
            employee_email=None,
            company_archive_email=None,
        )
        self.assertTrue(career_available)
        self.assertIn(career_reason, (None, ""))

        retirement_available, retirement_reason = certificates_mail._certificate_type_eligibility(
            type_key="retirement_certificate",
            employee_row={
                "hire_date": "2024-01-01",
                "leave_date": "2026-03-20",
                "employment_status": "terminated",
            },
            employee_email=None,
            company_archive_email=None,
        )
        self.assertTrue(retirement_available)
        self.assertIn(retirement_reason, (None, ""))

    def test_ensure_certificate_mail_foundation_seeds_defaults(self):
        fetchone_queue = []
        fetchone_queue.extend(
            {"id": f"cert-{index}", "display_name": definition["display_name"], "requires_approval": definition["requires_approval"], "auto_mail_enabled": definition["auto_mail_enabled"], "meta_json": definition["meta_json"]}
            for index, definition in enumerate(certificates_mail.CERTIFICATE_TYPE_DEFINITIONS, start=1)
        )
        fetchone_queue.append(
            {
                "id": "account-1",
                "account_key": "default_smtp",
                "provider": "smtp",
                "sender_email": "no-reply@example.com",
                "sender_name": "ARLS",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "username": "mailer",
                "secret_ref": "env:SMTP_PASSWORD",
                "is_active": True,
                "settings_json": {"managed_by": "phase4_seed"},
            }
        )
        fetchone_queue.append(
            {
                "id": "profile-1",
                "profile_key": "default_company",
                "display_name": "기본 회사 발신",
                "reply_to_email": "no-reply@example.com",
                "from_email": "no-reply@example.com",
                "is_default": True,
                "mail_account_id": "account-1",
                "settings_json": {"managed_by": "phase4_seed"},
            }
        )
        fetchone_queue.extend(
            {
                "id": f"template-{index}",
                "template_key": definition["template_key"],
                "subject_template": definition["subject_template"],
                "body_template": definition["body_template"],
                "channel": "email",
                "is_active": True,
            }
            for index, definition in enumerate(certificates_mail.MAIL_TEMPLATE_DEFINITIONS, start=1)
        )
        conn = _FakeConn(fetchone_queue=fetchone_queue)

        with patch.object(certificates_mail.settings, "mail_enabled", True), \
             patch.object(certificates_mail.settings, "smtp_host", "smtp.example.com"), \
             patch.object(certificates_mail.settings, "smtp_port", 587), \
             patch.object(certificates_mail.settings, "mail_from", "no-reply@example.com"), \
             patch.object(certificates_mail.settings, "smtp_username", "mailer"), \
             patch.object(certificates_mail.settings, "smtp_ssl", False), \
             patch.object(certificates_mail.settings, "smtp_starttls", True):
            result = certificates_mail.ensure_certificate_mail_foundation(
                conn,
                tenant_id="tenant-1",
                actor_user_id="user-1",
            )

        self.assertEqual(len(result["certificate_types"]), len(certificates_mail.CERTIFICATE_TYPE_DEFINITIONS))
        self.assertEqual(result["mail_account"]["account_key"], "default_smtp")
        self.assertEqual(result["mail_profile"]["profile_key"], "default_company")
        self.assertEqual(len(result["mail_templates"]), len(certificates_mail.MAIL_TEMPLATE_DEFINITIONS))
        self.assertTrue(any("INSERT INTO certificate_types" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO mail_accounts" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO mail_sender_profiles" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO mail_templates" in sql for sql, _ in conn.executed))

    def test_sync_legacy_employment_certificate_request_upserts_certificate_request(self):
        conn = _FakeConn(
            fetchone_queue=[
                None,
                {
                    "id": "certificate-request-1",
                    "status": "issued",
                    "issue_number": "CERT-20260330-0001",
                    "requested_at": "2026-03-30T00:00:00Z",
                    "issued_at": "2026-03-30T01:00:00Z",
                    "approval_document_id": "approval-doc-1",
                }
            ]
        )
        audit = _FakeAuditService(conn)

        with patch.object(certificates_mail, "ensure_certificate_mail_foundation", return_value={}), \
             patch.object(
                 certificates_mail,
                 "_fetch_legacy_document_request_row",
                 return_value={
                     "id": "legacy-1",
                     "tenant_id": "tenant-1",
                     "employee_id": "emp-1",
                     "purpose_code": "BANK",
                     "purpose_text": None,
                     "status": "issued",
                     "requested_at": "2026-03-30T00:00:00Z",
                     "generated_at": "2026-03-30T01:00:00Z",
                     "issue_number": "CERT-20260330-0001",
                     "document_type": "employment_certificate",
                 },
             ), \
             patch.object(
                 certificates_mail,
                 "_resolve_certificate_type_row",
                 return_value={"id": "type-1"},
             ), \
             patch.object(
                 certificates_mail,
                 "_fetch_approval_document_id_for_legacy_request",
                 return_value="approval-doc-1",
             ), \
             patch.object(
                 certificates_mail,
                 "_ensure_certificate_attachment_object",
                 return_value="attachment-1",
             ), \
             patch.object(certificates_mail, "GroupwareAuditService", return_value=audit):
            result = certificates_mail.sync_legacy_employment_certificate_request(
                conn,
                tenant_id="tenant-1",
                legacy_request_id="legacy-1",
                actor_user_id="user-1",
                actor_role="hq_admin",
            )

        self.assertEqual(result["status"], "issued")
        self.assertEqual(result["approval_document_id"], "approval-doc-1")
        self.assertTrue(any("INSERT INTO certificate_requests" in sql for sql, _ in conn.executed))
        insert_sql, insert_params = next((sql, params) for sql, params in conn.executed if "INSERT INTO certificate_requests" in sql)
        self.assertIn("legacy_source_type", insert_sql)
        self.assertIn("legacy-1", insert_params)
        self.assertEqual(audit.calls[0]["event_type"], "certificate_request_synced")

    def test_sync_issue_job_upserts_current_job_state(self):
        conn = _FakeConn(
            fetchone_queue=[
                None,
                {
                    "id": "issue-job-1",
                    "certificate_request_id": "certificate-request-1",
                    "job_state": "processing",
                    "attempts": 1,
                    "last_error": None,
                    "completed_at": None,
                }
            ]
        )

        with patch.object(
            certificates_mail,
            "sync_legacy_employment_certificate_request",
            return_value={"id": "certificate-request-1", "status": "generating", "issue_number": None},
        ):
            result = certificates_mail.sync_legacy_employment_certificate_issue_job(
                conn,
                tenant_id="tenant-1",
                legacy_request_id="legacy-1",
                job_state="processing",
                payload_extra={"stage": "pdf_generation"},
                increment_attempts=True,
            )

        self.assertEqual(result["job_state"], "processing")
        self.assertEqual(result["attempts"], 1)
        self.assertTrue(any("INSERT INTO certificate_issue_jobs" in sql for sql, _ in conn.executed))

    def test_record_certificate_mail_delivery_writes_job_and_event(self):
        conn = _FakeConn(
            fetchone_queue=[
                {"id": "job-1", "state": "sent", "sent_at": "2026-03-30T01:10:00Z", "last_error": None},
                {"id": "event-1"},
            ]
        )

        with patch.object(
            certificates_mail,
            "sync_legacy_employment_certificate_request",
            return_value={"id": "certificate-request-1", "status": "issued", "issue_number": "CERT-1"},
        ), patch.object(
            certificates_mail,
            "ensure_certificate_mail_foundation",
            return_value={
                "mail_account": {"id": "account-1"},
                "mail_profile": {"id": "profile-1"},
            },
        ), patch.object(
            certificates_mail,
            "_fetch_mail_template_by_key",
            return_value={"id": "template-1"},
        ), patch.object(
            certificates_mail,
            "_fetch_mail_profile_by_key",
            return_value={"id": "profile-1"},
        ), patch.object(
            certificates_mail,
            "_fetch_mail_account_by_key",
            return_value={"id": "account-1"},
        ):
            result = certificates_mail.record_certificate_mail_delivery(
                conn,
                tenant_id="tenant-1",
                legacy_request_id="legacy-1",
                recipient_role="employee",
                recipient_email="user@example.com",
                subject="재직증명서 발급 - 홍길동",
                body_text="직원 전달용 재직증명서가 발급되었습니다.",
                attachment_name="employment_certificate_CERT-1.pdf",
                sent=True,
                error=None,
            )

        self.assertEqual(result["state"], "sent")
        self.assertTrue(any("INSERT INTO outbound_mail_jobs" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO mail_delivery_events" in sql for sql, _ in conn.executed))

    def test_queue_approval_notification_mail_inserts_queued_job(self):
        conn = _FakeConn(
            fetchone_queue=[
                {"id": "queued-job-1", "state": "queued", "subject": "결재 검토 요청 - 휴가신청", "recipient_email": "approver@example.com", "payload_json": {}, "created_at": "2026-03-30T01:00:00Z"},
                {"id": "queued-event-1", "occurred_at": "2026-03-30T01:00:00Z"},
            ]
        )

        with patch.object(
            certificates_mail,
            "_resolve_user_mail_target",
            return_value={"user_id": "user-1", "email": "approver@example.com", "full_name": "결재자"},
        ), patch.object(
            certificates_mail,
            "ensure_certificate_mail_foundation",
            return_value={"mail_account": {"id": "account-1"}, "mail_profile": {"id": "profile-1"}},
        ), patch.object(
            certificates_mail,
            "_fetch_mail_template_by_key",
            return_value={
                "id": "template-1",
                "template_key": "approval_review_requested",
                "subject_template": "결재 검토 요청 - {{ title }}",
                "body_template": "새 결재 문서가 도착했습니다.",
                "channel": "email",
                "is_active": True,
            },
        ), patch.object(
            certificates_mail,
            "_fetch_mail_profile_by_key",
            return_value={"id": "profile-1"},
        ), patch.object(
            certificates_mail,
            "_fetch_mail_account_by_key",
            return_value={"id": "account-1", "is_active": True},
        ):
            result = certificates_mail.queue_approval_notification_mail(
                conn,
                tenant_id="tenant-1",
                template_key="approval_review_requested",
                document_id="doc-1",
                recipient_user_id="user-1",
                render_context={"title": "휴가신청"},
            )

        self.assertEqual(result["state"], "queued")
        self.assertEqual(result["recipient_email"], "approver@example.com")
        self.assertTrue(any("INSERT INTO outbound_mail_jobs" in sql for sql, _ in conn.executed))

    def test_backfill_legacy_employment_certificate_requests_syncs_rows(self):
        conn = _FakeConn(fetchall_queue=[[{"id": "legacy-1"}, {"id": "legacy-2"}]])
        audit = _FakeAuditService(conn)

        with patch.object(certificates_mail, "ensure_certificate_mail_foundation", return_value={}), \
             patch.object(
                 certificates_mail,
                 "sync_legacy_employment_certificate_request",
                 side_effect=[
                     {"id": "cert-1", "status": "requested"},
                     {"id": "cert-2", "status": "issued"},
                 ],
             ), \
             patch.object(
                 certificates_mail,
                 "sync_legacy_employment_certificate_issue_job",
                 side_effect=[
                     {"id": "job-1", "job_state": "queued"},
                     {"id": "job-2", "job_state": "completed"},
                 ],
             ), \
             patch.object(certificates_mail, "GroupwareAuditService", return_value=audit):
            result = certificates_mail.backfill_legacy_employment_certificate_requests(
                conn,
                tenant_id="tenant-1",
                actor_user_id="user-1",
                actor_role="hq_admin",
                limit=20,
            )

        self.assertEqual(result["requested_count"], 2)
        self.assertEqual(result["synced_requests"], 2)
        self.assertEqual(result["synced_jobs"], 2)
        self.assertEqual(audit.calls[0]["action_type"], "legacy_backfill_requested")

    def test_retry_certificate_issue_job_requeues_job(self):
        conn = _FakeConn(
            fetchone_queue=[
                {
                    "id": "issue-job-1",
                    "certificate_request_id": "cert-1",
                    "job_state": "failed",
                    "legacy_source_type": "employment_certificate_request",
                    "legacy_source_id": "legacy-1",
                    "certificate_status": "failed",
                }
            ]
        )
        audit = _FakeAuditService(conn)

        with patch.object(
            certificates_mail,
            "sync_legacy_employment_certificate_issue_job",
            return_value={"job_state": "queued"},
        ), patch.object(certificates_mail, "GroupwareAuditService", return_value=audit):
            result = certificates_mail.retry_certificate_issue_job(
                conn,
                tenant_id="tenant-1",
                issue_job_id="issue-job-1",
                actor_user_id="user-1",
                actor_role="hq_admin",
            )

        self.assertEqual(result["job_state"], "queued")
        self.assertEqual(result["legacy_source_id"], "legacy-1")
        self.assertEqual(audit.calls[0]["action_type"], "issue_job_retried")

    def test_retry_outbound_mail_job_requeues_and_logs_event(self):
        conn = _FakeConn(
            fetchone_queue=[
                {
                    "id": "job-1",
                    "source_type": "approval_notification",
                    "source_id": "doc-1:approval_review_requested:user-1",
                    "recipient_email": "approver@example.com",
                    "state": "queued",
                    "attempts": 1,
                },
                {"id": "retry-event-1", "occurred_at": "2026-03-30T02:00:00Z"},
            ]
        )
        audit = _FakeAuditService(conn)

        with patch.object(certificates_mail, "GroupwareAuditService", return_value=audit):
            result = certificates_mail.retry_outbound_mail_job(
                conn,
                tenant_id="tenant-1",
                job_id="job-1",
                actor_user_id="user-1",
                actor_role="hq_admin",
            )

        self.assertEqual(result["state"], "queued")
        self.assertTrue(any("UPDATE outbound_mail_jobs" in sql for sql, _ in conn.executed))
        self.assertTrue(any("INSERT INTO mail_delivery_events" in sql for sql, _ in conn.executed))
        self.assertEqual(audit.calls[0]["action_type"], "outbound_mail_retried")


if __name__ == "__main__":
    unittest.main()
