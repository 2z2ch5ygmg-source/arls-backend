from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from app.routers.v1.integrations import (
    _apply_internal_support_schedule_targets,
    _resolve_support_assignment_materialization_action,
    _apply_support_assignment_for_ticket,
    _retract_overnight_for_ticket,
)
from app.schemas import SocEventIn


class SocSupportAssignmentBridgeTests(unittest.TestCase):
    def _build_payload(self, *, event_type: str, work_type: str, template_type: str) -> SocEventIn:
        return SocEventIn(
            event_uid="soc-evt-001",
            event_type=event_type,
            tenant_code="SRS_KOREA",
            employee_code="__SOC_MULTI__",
            site_code="R692",
            work_date=date(2026, 4, 1),
            payload={
                "request_date": "2026-04-01",
                "work_type": work_type,
                "internal_staff_employee_codes": ["R692-0007"],
                "internal_staff_workers": [
                    {
                        "employee_id": 7,
                        "employee_code": "R692-0007",
                        "worker_name": "조태환",
                        "worker_type": "INTERNAL",
                    }
                ],
            },
            metadata={"template_type": template_type},
        )

    def test_support_assignment_action_resolves_retract_from_payload_status(self):
        payload = self._build_payload(
            event_type="support_assignment_approved",
            work_type="NIGHT",
            template_type="야간 지원 요청",
        )
        payload.payload["status"] = "반려"
        self.assertEqual(_resolve_support_assignment_materialization_action(payload), "RETRACT")

    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_internal_support_schedule_sync_uses_requested_work_date_and_day_shift(self, mock_upsert_schedule, mock_resolve_targets):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-7",
                "employee_code": "R692-0007",
                "full_name": "조태환",
                "company_id": "comp-1",
                "site_id": "site-1",
            }
        ]
        mock_upsert_schedule.return_value = {
            "action": "inserted",
            "schedule_id": "schedule-1",
            "shift_type": "day",
            "schedule_date": "2026-04-01",
        }

        result = _apply_internal_support_schedule_targets(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="support_assignment_approved",
                work_type="DAY",
                template_type="주간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=42,
            event_type="support_assignment_approved",
            support_period="day",
        )

        self.assertTrue(result["schedule_sync"])
        self.assertEqual(result["target_count"], 1)
        self.assertEqual(result["targets"][0]["work_date"], "2026-04-01")
        self.assertEqual(result["targets"][0]["shift_type"], "day")
        self.assertEqual(mock_upsert_schedule.call_args.args[4]["id"], "emp-7")
        self.assertEqual(mock_upsert_schedule.call_args.args[5], date(2026, 4, 1))
        self.assertEqual(mock_upsert_schedule.call_args.args[6], "day")
        self.assertEqual(mock_upsert_schedule.call_args.kwargs["source_ticket_id"], 42)

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_applies_internal_schedule_sync(
        self,
        mock_upsert_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-7",
                "employee_code": "R692-0007",
                "full_name": "조태환",
                "company_id": "comp-1",
                "site_id": "site-1",
            }
        ]
        mock_upsert_schedule.return_value = {
            "action": "updated",
            "schedule_id": "schedule-2",
            "shift_type": "day",
            "schedule_date": "2026-04-01",
        }
        mock_upsert_support.return_value = (
            {
                "id": "support-row-1",
                "employee_id": "emp-7",
                "worker_name": "조태환",
                "work_date": date(2026, 4, 1),
                "support_period": "day",
            },
            True,
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="support_assignment_approved",
                work_type="DAY",
                template_type="주간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=42,
        )

        self.assertTrue(result["support_assignment"])
        self.assertEqual(result["internal_support_count"], 1)
        self.assertTrue(result["internal_schedule_sync"]["schedule_sync"])
        self.assertEqual(result["internal_schedule_sync"]["targets"][0]["employee_name"], "조태환")
        self.assertEqual(mock_upsert_schedule.call_args.args[6], "day")
        self.assertEqual(mock_delete_assignments.call_count, 2)

    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_night_support_schedule_sync_preserves_requested_date(self, mock_upsert_schedule, mock_resolve_targets):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-7",
                "employee_code": "R692-0007",
                "full_name": "조태환",
                "company_id": "comp-1",
                "site_id": "site-1",
            }
        ]
        mock_upsert_schedule.return_value = {
            "action": "updated",
            "schedule_id": "schedule-3",
            "shift_type": "night",
            "schedule_date": "2026-04-01",
        }

        result = _apply_internal_support_schedule_targets(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="overnight_approved",
                work_type="NIGHT",
                template_type="야간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=99,
            event_type="overnight_approved",
            support_period="night",
        )

        self.assertEqual(result["support_period"], "night")
        self.assertEqual(result["targets"][0]["work_date"], "2026-04-01")
        self.assertEqual(result["targets"][0]["shift_type"], "night")
        self.assertEqual(mock_upsert_schedule.call_args.args[5], date(2026, 4, 1))
        self.assertEqual(mock_upsert_schedule.call_args.args[6], "night")

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_respects_night_period_from_payload(
        self,
        mock_upsert_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-7",
                "employee_code": "R692-0007",
                "full_name": "조태환",
                "company_id": "comp-1",
                "site_id": "site-1",
                "duty_role": "GUARD",
                "soc_role": "officer",
            }
        ]
        mock_upsert_schedule.return_value = {
            "action": "inserted",
            "schedule_id": "schedule-4",
            "shift_type": "night",
            "schedule_date": "2026-04-01",
        }
        mock_upsert_support.return_value = (
            {
                "id": "support-row-night-1",
                "employee_id": "emp-7",
                "worker_name": "조태환",
                "work_date": date(2026, 4, 1),
                "support_period": "night",
            },
            True,
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="support_assignment_approved",
                work_type="NIGHT",
                template_type="야간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=77,
        )

        self.assertEqual(result["support_period"], "night")
        self.assertEqual(result["internal_schedule_sync"]["support_period"], "night")
        self.assertEqual(mock_upsert_schedule.call_args.args[6], "night")
        self.assertEqual(mock_upsert_support.call_args.kwargs["support_period"], "night")
        self.assertEqual(mock_delete_assignments.call_args.kwargs["support_period"], "night")

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_internal_support_schedule_targets")
    def test_support_assignment_ticket_retracts_when_status_is_rejected(
        self,
        mock_retract_schedule,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "schedule_sync": True,
            "ticket_id": 42,
            "work_date": "2026-04-01",
            "support_period": "night",
            "target_count": 1,
            "targets": [{"employee_name": "조태환"}],
            "source_keys": ["R692-0007"],
            "action": "RETRACT",
            "changed": True,
        }
        payload = self._build_payload(
            event_type="support_assignment_approved",
            work_type="NIGHT",
            template_type="야간 지원 요청",
        )
        payload.payload["status"] = "반려"

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=payload,
            work_date=date(2026, 4, 1),
            ticket_id=42,
        )

        self.assertEqual(result["action"], "RETRACT")
        self.assertEqual(result["target_count"], 1)
        self.assertEqual(mock_delete_assignments.call_count, 2)
        self.assertEqual(mock_retract_schedule.call_args.kwargs["support_period"], "night")

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_internal_support_schedule_targets")
    def test_support_assignment_ticket_retracts_for_cancelled_event_type(
        self,
        mock_retract_schedule,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "schedule_sync": True,
            "ticket_id": 88,
            "work_date": "2026-04-01",
            "support_period": "day",
            "target_count": 0,
            "targets": [],
            "source_keys": [],
            "action": "RETRACT",
            "changed": False,
        }
        payload = self._build_payload(
            event_type="support_assignment_cancelled",
            work_type="DAY",
            template_type="주간 지원 요청",
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=payload,
            work_date=date(2026, 4, 1),
            ticket_id=88,
        )

        self.assertEqual(result["action"], "RETRACT")
        self.assertEqual(result["target_count"], 0)
        self.assertEqual(mock_delete_assignments.call_count, 2)

    @patch("app.routers.v1.integrations.delete_apple_report_overnight_records_by_source_ticket")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._delete_overnight_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    def test_overnight_retract_removes_materialized_schedule_and_support_rows(
        self,
        mock_retract_schedule,
        mock_delete_overnight_assignments,
        mock_delete_assignments,
        mock_delete_apple_report,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "조태환"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 91,
        }
        mock_delete_assignments.return_value = {
            "deleted_count": 2,
            "rows": [{"worker_name": "외부A"}, {"worker_name": "외부B"}],
        }
        mock_delete_overnight_assignments.return_value = [{"ticket_id": 91, "requested_count": 1}]
        mock_delete_apple_report.return_value = [{"source_ticket_id": 91, "headcount": 1}]

        result = _retract_overnight_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="overnight_retracted",
                work_type="NIGHT",
                template_type="야간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=91,
        )

        self.assertEqual(result["action"], "RETRACT")
        self.assertTrue(result["changed"])
        self.assertEqual(result["schedule_retract"]["retracted_count"], 1)
        self.assertEqual(result["external_support_count"], 2)
        self.assertEqual(result["apple_report_record_count"], 1)


if __name__ == "__main__":
    unittest.main()
