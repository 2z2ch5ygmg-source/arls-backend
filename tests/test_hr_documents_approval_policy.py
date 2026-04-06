from __future__ import annotations

import unittest
from unittest.mock import patch

from app.routers.v1 import hr_documents


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


class HrDocumentsApprovalPolicyTests(unittest.TestCase):
    def test_resolve_document_approval_policy_state_marks_retirement_editable(self):
        state = hr_documents._resolve_document_approval_policy_state(
            hr_documents.DOCUMENT_TYPE_RETIREMENT_CERTIFICATE
        )

        self.assertTrue(state["editable"])
        self.assertEqual(
            state["rule_form_key"],
            "certificate_request:retirement_certificate",
        )
        self.assertEqual(state["fallback_form_key"], "certificate_request")

    def test_resolve_document_approval_policy_state_blocks_employment_certificate(self):
        state = hr_documents._resolve_document_approval_policy_state(
            hr_documents.DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE
        )

        self.assertFalse(state["editable"])
        self.assertIn("즉시 발급", state["unsupported_reason"])

    def test_build_document_approval_policy_response_falls_back_to_generic_rules(self):
        conn = _FakeConn(
            fetchall_queue=[
                [],
                [
                    {
                        "id": "rule-1",
                        "rule_order": 1,
                        "rule_name": "기본 결재선 1",
                        "approver_role": "supervisor",
                        "approver_user_id": None,
                        "scope_type": "site_or_tenant",
                        "site_id": None,
                        "conditions_json": {},
                    }
                ],
                [
                    {
                        "id": "user-1",
                        "username": "boss",
                        "full_name": "Boss",
                        "role": "hq_admin",
                    }
                ],
                [
                    {
                        "id": "site-1",
                        "site_code": "S1",
                        "site_name": "Main Site",
                    }
                ],
            ]
        )

        with patch.object(hr_documents, "ensure_default_approval_line_rules"):
            result = hr_documents._build_document_approval_policy_response(
                conn,
                tenant_id="tenant-1",
                document_type=hr_documents.DOCUMENT_TYPE_RETIREMENT_CERTIFICATE,
            )

        self.assertTrue(result["editable"])
        self.assertEqual(result["resolved_form_key"], "certificate_request")
        self.assertEqual(result["items"][0]["step_kind"], "site_supervisor")
        self.assertEqual(result["user_options"][0]["id"], "user-1")
        self.assertEqual(result["site_options"][0]["id"], "site-1")

    def test_update_document_approval_policy_inserts_type_specific_rules(self):
        conn = _FakeConn()
        payload = hr_documents.DocumentApprovalPolicyUpdateRequest(
            document_type=hr_documents.DOCUMENT_TYPE_RETIREMENT_CERTIFICATE,
            items=[
                hr_documents.DocumentApprovalPolicyStepIn(
                    step_kind="site_supervisor",
                    label="1차 승인",
                    site_role="supervisor",
                ),
                hr_documents.DocumentApprovalPolicyStepIn(
                    step_kind="explicit_user",
                    label="최종 승인",
                    explicit_user_id="11111111-1111-1111-1111-111111111111",
                ),
            ],
        )
        user = {
            "id": "actor-1",
            "role": "hq_admin",
            "tenant_id": "tenant-1",
            "tenant_code": "TENANT_1",
        }

        with patch.object(hr_documents, "ensure_default_approval_line_rules"), patch.object(
            hr_documents,
            "_build_document_approval_policy_response",
            return_value={"ok": True, "items": []},
        ):
            result = hr_documents.update_document_approval_policy(
                payload,
                x_tenant_id=None,
                conn=conn,
                user=user,
            )

        self.assertEqual(result["ok"], True)
        delete_sql, delete_params = conn.executed[0]
        self.assertIn("DELETE FROM approval_line_rules", delete_sql)
        self.assertEqual(
            delete_params,
            ("tenant-1", "certificate_request:retirement_certificate"),
        )
        insert_params = [params for sql, params in conn.executed if "INSERT INTO approval_line_rules" in sql]
        self.assertEqual(len(insert_params), 2)
        self.assertEqual(insert_params[0][2], "certificate_request:retirement_certificate")
        self.assertEqual(insert_params[1][5], None)
        self.assertEqual(insert_params[1][6], "11111111-1111-1111-1111-111111111111")


if __name__ == "__main__":
    unittest.main()
