from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from app.routers.v1 import integrations
from app.schemas import SocEventIn


class SocEmployeeSyncScopeResolutionTests(unittest.TestCase):
    def test_resolve_soc_sync_uses_site_scope_for_employee_code_lookup(self):
        tenant_id = "tenant-1"
        conn = object()
        with patch(
            "app.routers.v1.integrations._resolve_employee_by_uuid",
            return_value=None,
        ) as mock_resolve_by_uuid, patch(
            "app.routers.v1.integrations._resolve_employee_by_external_key",
            return_value=None,
        ) as mock_resolve_by_key, patch(
            "app.routers.v1.integrations._resolve_employee",
        ) as mock_resolve_employee:
            mock_resolve_employee.return_value = {
                "id": "emp-site-a",
                "site_id": "site-a",
                "employee_code": "R001-007",
            }

            result = integrations._resolve_employee_for_soc_sync(
                conn=conn,
                tenant_id=tenant_id,
                employee_uuid="uuid-site-a",
                employee_code="R001-007",
                external_key="",
                linked_employee_id="",
                site_id="site-a",
                has_employee_uuid=True,
            )

        self.assertEqual(result, {"id": "emp-site-a", "site_id": "site-a", "employee_code": "R001-007"})
        self.assertEqual(mock_resolve_by_uuid.call_count, 1)
        self.assertEqual(mock_resolve_by_key.call_count, 0)
        self.assertIs(mock_resolve_employee.call_args.args[0], conn)
        self.assertEqual(mock_resolve_employee.call_args.args[1], tenant_id)
        self.assertEqual(mock_resolve_employee.call_args.args[2], "R001-007")
        self.assertEqual(mock_resolve_employee.call_args.kwargs, {"site_id": "site-a"})

    @patch("app.routers.v1.integrations._sync_attendance_event")
    @patch("app.routers.v1.integrations._resolve_employee")
    @patch("app.routers.v1.integrations._resolve_site_by_code")
    @patch("app.routers.v1.integrations._get_feature_flag_snapshot", return_value={})
    def test_attendance_event_resolves_employee_with_site_filter(
        self,
        mock_get_feature_flags,
        mock_resolve_site_by_code,
        mock_resolve_employee,
        mock_sync_attendance,
    ):
        conn = object()
        mock_resolve_site_by_code.return_value = {
            "id": "site-a",
            "site_code": "R692",
            "company_id": "company-1",
        }
        mock_resolve_employee.return_value = {
            "id": "emp-site-a",
            "site_id": "site-a",
            "employee_code": "R692-007",
        }
        mock_sync_attendance.return_value = {
            "status": "ok",
        }

        payload = SocEventIn(
            event_uid="soc-att-001",
            event_type="attendance_check_in",
            tenant_code="SRS_KOREA",
            employee_code="R692-007",
            site_code="R692",
            work_date=date(2026, 6, 1),
            payload={},
        )

        result = integrations._apply_soc_event(
            conn=conn,
            tenant={"id": "tenant-1", "tenant_code": "SRS_KOREA"},
            payload=payload,
            event_type="attendance_check_in",
        )

        self.assertTrue(result.get("handled"))
        self.assertIs(mock_resolve_site_by_code.call_args.args[0], conn)
        self.assertEqual(mock_resolve_site_by_code.call_args.args[1], "tenant-1")
        self.assertEqual(mock_resolve_site_by_code.call_args.args[2], "R692")
        self.assertIs(mock_resolve_employee.call_args.args[0], conn)
        self.assertEqual(mock_resolve_employee.call_args.args[1], "tenant-1")
        self.assertEqual(mock_resolve_employee.call_args.args[2], "R692-007")
        self.assertEqual(mock_resolve_employee.call_args.kwargs, {"site_id": "site-a"})
        mock_sync_attendance.assert_called_once()
        self.assertEqual(result.get("employee_code"), "R692-007")


if __name__ == "__main__":
    unittest.main()
