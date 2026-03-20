from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from app.routers.v1 import schedules


class AppleWeeklyTruthBridgeTests(unittest.TestCase):
    def test_bridge_truth_route_accepts_bearer_token(self):
        resolved_tenant = {
            "id": "tenant-srs",
            "tenant_code": "srs_korea",
            "tenant_name": "SRS Korea",
            "is_active": True,
            "is_deleted": False,
        }
        contract = {"contract_version": "test", "scope": {"site_code": "R692"}}
        with patch.object(schedules, "_require_sentrix_support_bridge_token") as require_mock, patch.object(
            schedules,
            "_resolve_sentrix_bridge_tenant",
            return_value=resolved_tenant,
        ) as resolve_mock, patch.object(
            schedules,
            "build_apple_weekly_truth_contract",
            return_value=contract,
        ) as build_mock:
            result = schedules.get_sentrix_hq_apple_weekly_truth_bridge(
                week_start=date(2026, 3, 19),
                site_code="R692",
                tenant_code="srs_korea",
                authorization="Bearer sentrix-service-token",
                x_sentrix_bridge_token=None,
                conn=object(),
            )
        self.assertEqual(result, contract)
        require_mock.assert_called_once_with("sentrix-service-token")
        resolve_mock.assert_called_once()
        build_mock.assert_called_once()
        build_kwargs = build_mock.call_args.kwargs
        self.assertEqual(build_kwargs["tenant_row"]["tenant_code"], "srs_korea")
        self.assertEqual(build_kwargs["site_code"], "R692")
        self.assertEqual(build_kwargs["week_start"], date(2026, 3, 16))

    def test_bridge_truth_route_prefers_explicit_bridge_header(self):
        resolved_tenant = {
            "id": "tenant-srs",
            "tenant_code": "srs_korea",
            "tenant_name": "SRS Korea",
            "is_active": True,
            "is_deleted": False,
        }
        with patch.object(schedules, "_require_sentrix_support_bridge_token") as require_mock, patch.object(
            schedules,
            "_resolve_sentrix_bridge_tenant",
            return_value=resolved_tenant,
        ), patch.object(
            schedules,
            "build_apple_weekly_truth_contract",
            return_value={"ok": True},
        ):
            schedules.get_sentrix_hq_apple_weekly_truth_bridge(
                week_start=date(2026, 3, 19),
                site_code="R692",
                tenant_code="srs_korea",
                authorization="Bearer ignored-token",
                x_sentrix_bridge_token="bridge-header-token",
                conn=object(),
            )
        require_mock.assert_called_once_with("bridge-header-token")


if __name__ == "__main__":
    unittest.main()
