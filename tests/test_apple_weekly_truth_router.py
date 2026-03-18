from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from app.routers.v1 import apple_weekly_truth as truth_router


class AppleWeeklyTruthRouterTests(unittest.TestCase):
    def test_truth_route_accepts_non_apple_tenant_context(self):
        user = {
            "role": "developer",
            "tenant_code": "MASTER",
            "active_tenant_id": "tenant-master",
        }
        resolved_tenant = {
            "id": "tenant-srs",
            "tenant_code": "srs_korea",
            "tenant_name": "SRS Korea",
            "is_active": True,
            "is_deleted": False,
        }
        contract = {"contract_version": "test", "scope": {"site_code": "R692"}}
        with patch.object(truth_router, "resolve_scoped_tenant", return_value=resolved_tenant) as resolve_mock, patch.object(
            truth_router,
            "build_apple_weekly_truth_contract",
            return_value=contract,
        ) as build_mock:
            result = truth_router.get_apple_weekly_truth(
                week_start=date(2026, 3, 16),
                site_code="R692",
                tenant_code="srs_korea",
                conn=object(),
                user=user,
            )
        self.assertEqual(result, contract)
        resolve_mock.assert_called_once()
        build_mock.assert_called_once()
        build_args = build_mock.call_args.kwargs
        self.assertEqual(build_args["tenant_row"]["tenant_code"], "srs_korea")
        self.assertEqual(build_args["site_code"], "R692")


if __name__ == "__main__":
    unittest.main()
