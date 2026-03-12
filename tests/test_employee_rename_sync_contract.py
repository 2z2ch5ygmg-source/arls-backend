import unittest

from fastapi import HTTPException

from app.routers.v1 import employees


class _DummyResponse:
    def __init__(self, status_code: int = 202, text: str = "accepted"):
        self.status_code = status_code
        self.text = text


class EmployeeRenameSyncContractTests(unittest.TestCase):
    def test_employee_rename_sync_payload_uses_stable_identity(self):
        captured: dict[str, object] = {}

        original_enabled = employees.settings.soc_integration_enabled
        original_url = employees.settings.soc_employee_sync_url
        original_post = employees.requests.post

        employees.settings.soc_integration_enabled = True
        employees.settings.soc_employee_sync_url = "https://soc.example.test/employees/sync"

        def _fake_post(url, json, timeout):
            captured["url"] = url
            captured["json"] = json
            captured["timeout"] = timeout
            return _DummyResponse()

        employees.requests.post = _fake_post
        try:
            ok, status_code, reason = employees._post_employee_sync_to_soc(
                tenant_id="tenant-1",
                tenant_code="APPLE",
                tenant_name="Apple Korea",
                site_id="site-1",
                site_code="R692",
                site_name="Apple Garosu",
                employee_uuid="emp-123",
                employee_code="R692-0042",
                full_name="최미강",
                phone="010-1111-2222",
                linked_user_id="user-77",
                username="choi.guard",
                user_role="officer",
                soc_login_id="choi.guard",
                soc_role="Officer",
                old_display_name="최미가",
                new_display_name="최미강",
                event_type="EMPLOYEE_UPDATED",
            )
        finally:
            employees.requests.post = original_post
            employees.settings.soc_integration_enabled = original_enabled
            employees.settings.soc_employee_sync_url = original_url

        self.assertTrue(ok)
        self.assertEqual(status_code, 202)
        self.assertIsNone(reason)

        payload = captured["json"]
        self.assertEqual(captured["url"], "https://soc.example.test/employees/sync")
        self.assertEqual(captured["timeout"], 5)
        self.assertEqual(payload["event_type"], "EMPLOYEE_UPDATED")
        self.assertEqual(payload["change_type"], "UPDATE")
        self.assertEqual(payload["sync_mode"], "UPSERT")
        self.assertEqual(payload["employee_id"], "emp-123")
        self.assertEqual(payload["old_display_name"], "최미가")
        self.assertEqual(payload["new_display_name"], "최미강")
        self.assertEqual(
            payload["tenant"],
            {
                "tenant_id": "tenant-1",
                "tenant_code": "APPLE",
                "tenant_name": "Apple Korea",
            },
        )
        self.assertEqual(
            payload["site"],
            {
                "site_id": "site-1",
                "site_code": "R692",
                "site_name": "Apple Garosu",
            },
        )
        self.assertEqual(
            payload["linked_user"],
            {
                "user_id": "user-77",
                "username": "choi.guard",
                "soc_login_id": "choi.guard",
                "user_role": "Officer",
                "soc_role": "Officer",
            },
        )
        self.assertEqual(payload["identity"]["employee_id"], "emp-123")
        self.assertEqual(payload["identity"]["employee_uuid"], "emp-123")
        self.assertEqual(payload["identity"]["employee_code"], "R692-0042")
        self.assertEqual(payload["identity"]["tenant_id"], "tenant-1")
        self.assertEqual(payload["identity"]["tenant_code"], "APPLE")
        self.assertEqual(payload["identity"]["site_id"], "site-1")
        self.assertEqual(payload["identity"]["site_code"], "R692")
        self.assertEqual(payload["identity"]["linked_user_id"], "user-77")
        self.assertEqual(payload["identity"]["identity_key"], "tenant-1:emp-123")
        self.assertEqual(payload["employee"]["employee_id"], "emp-123")
        self.assertEqual(payload["employee"]["employee_uuid"], "emp-123")
        self.assertEqual(payload["employee"]["employee_code"], "R692-0042")
        self.assertEqual(payload["employee"]["name"], "최미강")
        self.assertEqual(payload["employee"]["old_display_name"], "최미가")
        self.assertEqual(payload["employee"]["new_display_name"], "최미강")
        self.assertEqual(payload["employee"]["username"], "choi.guard")

    def test_require_employee_sync_success_raises_when_sync_fails(self):
        original_enabled = employees.settings.soc_integration_enabled
        original_url = employees.settings.soc_employee_sync_url
        employees.settings.soc_integration_enabled = True
        employees.settings.soc_employee_sync_url = "https://soc.example.test/employees/sync"
        try:
            with self.assertRaises(HTTPException) as exc_info:
                employees._require_employee_sync_success(
                    sync_ok=False,
                    status_code=503,
                    reason="sentrix unavailable",
                    action_label="수정",
                )
        finally:
            employees.settings.soc_integration_enabled = original_enabled
            employees.settings.soc_employee_sync_url = original_url

        exc = exc_info.exception
        self.assertEqual(exc.status_code, 502)
        self.assertEqual(exc.detail["error"], "SOC_EMPLOYEE_SYNC_FAILED")
        self.assertEqual(exc.detail["soc_status"], 503)
        self.assertEqual(exc.detail["soc_reason"], "sentrix unavailable")


if __name__ == "__main__":
    unittest.main()
