from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from app.routers.v1.integrations import (
    _apply_soc_event,
    _apply_internal_support_schedule_targets,
    _retract_internal_support_schedule_targets,
    _resolve_support_assignment_materialization_action,
    _apply_support_assignment_for_ticket,
    _apply_overnight_for_ticket,
    _retract_overnight_for_ticket,
    _resolve_soc_target_employees,
    _support_worker_dedupe_key,
    _to_internal_soc_event,
    _upsert_materialized_schedule_row,
)
from app.schemas import SocEventEnvelopeIn, SocEventIn


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

    @patch("app.routers.v1.integrations._resolve_employee_by_site_full_name")
    @patch("app.routers.v1.integrations._resolve_employee_by_external_key")
    def test_resolve_soc_targets_falls_back_to_same_site_internal_name(
        self,
        mock_resolve_by_key,
        mock_resolve_by_name,
    ):
        mock_resolve_by_key.return_value = None
        mock_resolve_by_name.return_value = {
            "id": "emp-99",
            "employee_code": "R738-0099",
            "full_name": "최유진",
            "company_id": "comp-1",
            "site_id": "site-1",
            "hire_date": None,
            "leave_date": None,
        }
        payload = SocEventIn(
            event_uid="soc-evt-self-1",
            event_type="overnight_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_OVERNIGHT__",
            site_code="R738",
            work_date=date(2026, 3, 5),
            payload={
                "request_date": "2026-03-05",
                "confirmed_workers": [
                    {
                        "affiliation": "자체",
                        "worker_name": "최유진",
                    }
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        resolved = _resolve_soc_target_employees(
            object(),
            tenant_id="tenant-1",
            site={"id": "site-1", "site_code": "R738"},
            payload=payload,
            event_type="overnight_approved",
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["full_name"], "최유진")
        mock_resolve_by_name.assert_called_once()

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_skips_external_row_for_self_staff_confirmed_worker(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-03-05",
            "source_ticket_id": 101,
        }
        mock_resolve_targets.return_value = [
            {
                "id": "emp-self-1",
                "employee_code": "R738-0009",
                "full_name": "최유진",
                "company_id": "comp-1",
                "site_id": "site-1",
                "duty_role": "GUARD",
                "soc_role": "officer",
            }
        ]
        mock_upsert_schedule.return_value = {
            "action": "inserted",
            "schedule_id": "schedule-self-1",
            "shift_type": "night",
            "schedule_date": "2026-03-05",
        }
        mock_upsert_support.return_value = (
            {
                "id": "support-row-self-1",
                "employee_id": "emp-self-1",
                "worker_name": "최유진",
                "work_date": date(2026, 3, 5),
                "support_period": "night",
            },
            True,
        )
        payload = SocEventIn(
            event_uid="soc-evt-self-2",
            event_type="support_assignment_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_MULTI__",
            site_code="R738",
            work_date=date(2026, 3, 5),
            payload={
                "request_date": "2026-03-05",
                "work_type": "NIGHT",
                "confirmed_workers": [
                    {
                        "affiliation": "자체",
                        "worker_name": "최유진",
                    }
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R738"},
            payload=payload,
            work_date=date(2026, 3, 5),
            ticket_id=101,
        )

        self.assertEqual(result["internal_support_count"], 1)
        self.assertEqual(result["external_support_count"], 0)
        self.assertEqual(mock_upsert_support.call_count, 1)
        self.assertEqual(mock_upsert_support.call_args.kwargs["worker_type"], "INTERNAL")
        self.assertEqual(mock_upsert_support.call_args.kwargs["name"], "최유진")
        self.assertEqual(mock_delete_assignments.call_count, 2)

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_bridges_only_self_subset_when_confirmed_workers_are_mixed(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "day",
            "work_date": "2026-04-01",
            "source_ticket_id": 202,
        }
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
            "schedule_id": "schedule-202",
            "shift_type": "day",
            "schedule_date": "2026-04-01",
        }
        mock_upsert_support.side_effect = [
            (
                {
                    "id": "support-row-external-1",
                    "worker_type": "BK",
                    "name": "외부A",
                    "work_date": date(2026, 4, 1),
                    "support_period": "day",
                },
                True,
            ),
            (
                {
                    "id": "support-row-internal-1",
                    "employee_id": "emp-7",
                    "worker_type": "INTERNAL",
                    "name": "조태환",
                    "work_date": date(2026, 4, 1),
                    "support_period": "day",
                },
                True,
            ),
        ]
        payload = SocEventIn(
            event_uid="soc-evt-mixed-1",
            event_type="support_assignment_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_MULTI__",
            site_code="R692",
            work_date=date(2026, 4, 1),
            payload={
                "request_date": "2026-04-01",
                "work_type": "DAY",
                "confirmed_workers": [
                    {
                        "affiliation": "자체",
                        "worker_name": "조태환",
                    },
                    {
                        "affiliation": "BK",
                        "worker_name": "외부A",
                    },
                ],
            },
            metadata={"template_type": "주간 지원 요청"},
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=payload,
            work_date=date(2026, 4, 1),
            ticket_id=202,
        )

        self.assertTrue(result["support_assignment"])
        self.assertEqual(result["internal_support_count"], 1)
        self.assertEqual(result["external_support_count"], 1)
        self.assertTrue(result["internal_schedule_sync"]["schedule_sync"])
        mock_resolve_targets.assert_called_once()
        mock_upsert_schedule.assert_called_once()
        self.assertEqual(mock_upsert_support.call_count, 2)
        self.assertEqual(mock_upsert_support.call_args_list[0].kwargs["worker_type"], "F")
        self.assertEqual(mock_upsert_support.call_args_list[0].kwargs["affiliation"], "BK")
        self.assertEqual(mock_upsert_support.call_args_list[1].kwargs["worker_type"], "INTERNAL")

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_external_only_skips_internal_schedule_sync(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 303,
        }
        mock_upsert_support.side_effect = [
            (
                {
                    "id": "support-row-external-1",
                    "worker_type": "BK",
                    "name": "외부A",
                    "work_date": date(2026, 4, 1),
                    "support_period": "night",
                },
                True,
            ),
            (
                {
                    "id": "support-row-external-2",
                    "worker_type": "F",
                    "name": "외부B",
                    "work_date": date(2026, 4, 1),
                    "support_period": "night",
                },
                True,
            ),
        ]
        payload = SocEventIn(
            event_uid="soc-evt-external-1",
            event_type="support_assignment_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_MULTI__",
            site_code="R692",
            work_date=date(2026, 4, 1),
            payload={
                "request_date": "2026-04-01",
                "work_type": "NIGHT",
                "internal_staff_employee_codes": [],
                "internal_staff_workers": [],
                "confirmed_workers": [
                    {
                        "affiliation": "BK",
                        "worker_name": "외부A",
                    },
                    {
                        "affiliation": "F",
                        "worker_name": "외부B",
                    },
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=payload,
            work_date=date(2026, 4, 1),
            ticket_id=303,
        )

        self.assertTrue(result["support_assignment"])
        self.assertEqual(result["internal_support_count"], 0)
        self.assertEqual(result["external_support_count"], 2)
        self.assertTrue(result["internal_schedule_sync"]["snapshot_empty"])
        mock_resolve_targets.assert_not_called()
        mock_upsert_schedule.assert_not_called()
        self.assertEqual(mock_upsert_support.call_count, 2)
        self.assertEqual(mock_upsert_support.call_args_list[0].kwargs["support_period"], "night")
        self.assertEqual(mock_delete_assignments.call_count, 2)

    @patch("app.routers.v1.integrations.upsert_support_assignment")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations.upsert_apple_report_overnight_record")
    @patch("app.routers.v1.integrations._upsert_overnight_assignment")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._apply_overnight")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_overnight_ticket_uses_self_staff_confirmed_worker_without_target_keys(
        self,
        mock_resolve_targets,
        mock_apply_overnight,
        mock_retract_materialized_rows,
        mock_upsert_overnight_assignment,
        mock_upsert_overnight_record,
        mock_delete_assignments,
        mock_upsert_support,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-night-1",
                "employee_code": "R738-0012",
                "full_name": "최유진",
                "company_id": "comp-1",
                "site_id": "site-1",
            }
        ]
        mock_apply_overnight.return_value = {
            "action": "inserted",
            "schedule_id": "schedule-night-1",
            "shift_type": "night",
            "schedule_date": "2026-03-05",
        }
        mock_retract_materialized_rows.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "기존내부"}],
            "shift_type": "night",
            "work_date": "2026-03-05",
            "source_ticket_id": 118,
        }
        mock_upsert_overnight_assignment.return_value = {
            "requested_count": 0,
        }
        mock_upsert_overnight_record.return_value = {
            "id": "overnight-record-1",
        }
        payload = SocEventIn(
            event_uid="soc-evt-self-3",
            event_type="overnight_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_OVERNIGHT__",
            site_code="R738",
            work_date=date(2026, 3, 5),
            payload={
                "request_date": "2026-03-05",
                "confirmed_workers": [
                    {
                        "worker_name": "자체 최유진",
                    }
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        result = _apply_overnight_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R738"},
            payload=payload,
            event_uid="soc-evt-self-3",
            work_date=date(2026, 3, 5),
            ticket_id=118,
        )

        self.assertEqual(result["target_count"], 1)
        self.assertEqual(result["external_support_count"], 0)
        self.assertEqual(result["schedule_retract_before_apply"]["retracted_count"], 1)
        mock_resolve_targets.assert_called_once()
        mock_retract_materialized_rows.assert_called_once()
        mock_apply_overnight.assert_called_once()
        mock_upsert_support.assert_not_called()
        mock_delete_assignments.assert_called_once()

    @patch("app.routers.v1.integrations._apply_support_assignment_for_ticket")
    @patch("app.routers.v1.integrations._apply_overnight_for_ticket")
    @patch("app.routers.v1.integrations._is_feature_enabled")
    @patch("app.routers.v1.integrations._resolve_site_by_code")
    def test_apply_soc_event_does_not_double_handle_overnight_as_support_assignment(
        self,
        mock_resolve_site,
        mock_is_feature_enabled,
        mock_apply_overnight,
        mock_apply_support_assignment,
    ):
        mock_resolve_site.return_value = {"id": "site-1", "site_code": "R692"}
        mock_is_feature_enabled.return_value = True
        mock_apply_overnight.return_value = {
            "overnight": True,
            "ticket_id": 55,
            "work_date": "2026-04-01",
            "target_count": 1,
            "targets": [{"employee_name": "조태환"}],
        }
        payload = self._build_payload(
            event_type="overnight_approved",
            work_type="NIGHT",
            template_type="야간 지원 요청",
        )
        payload.payload["ticket_status"] = "pending"

        result = _apply_soc_event(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            payload=payload,
            event_type="overnight_approved",
        )

        self.assertTrue(result["handled"])
        self.assertEqual(result["handlers"], ["overnight"])
        mock_apply_overnight.assert_called_once()
        mock_apply_support_assignment.assert_not_called()

    @patch("app.routers.v1.integrations._resolve_employee_by_site_full_name")
    def test_resolve_soc_targets_falls_back_to_internal_staff_worker_name(
        self,
        mock_resolve_by_name,
    ):
        mock_resolve_by_name.return_value = {
            "id": "emp-100",
            "employee_code": "R738-0100",
            "full_name": "최유진",
            "company_id": "comp-1",
            "site_id": "site-1",
            "hire_date": None,
            "leave_date": None,
        }
        payload = SocEventIn(
            event_uid="soc-evt-self-4",
            event_type="overnight_approved",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_OVERNIGHT__",
            site_code="R738",
            work_date=date(2026, 3, 6),
            payload={
                "request_date": "2026-03-06",
                "internal_staff_workers": [
                    {
                        "worker_name": "최유진",
                    }
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        resolved = _resolve_soc_target_employees(
            object(),
            tenant_id="tenant-1",
            site={"id": "site-1", "site_code": "R738"},
            payload=payload,
            event_type="overnight_approved",
        )

        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["employee_code"], "R738-0100")
        mock_resolve_by_name.assert_called_once()

    def test_support_worker_dedupe_key_handles_missing_affiliation(self):
        self.assertEqual(
            _support_worker_dedupe_key(affiliation=None, worker_name="자체 최유진"),
            ("", "자체 최유진".lower()),
        )

    def test_support_assignment_action_resolves_retract_from_payload_status(self):
        payload = self._build_payload(
            event_type="support_assignment_approved",
            work_type="NIGHT",
            template_type="야간 지원 요청",
        )
        payload.payload["status"] = "반려"
        self.assertEqual(_resolve_support_assignment_materialization_action(payload), "RETRACT")

    def test_support_assignment_action_keeps_explicit_upsert_event_even_when_ticket_pending(self):
        payload = self._build_payload(
            event_type="support_assignment_approved",
            work_type="DAY",
            template_type="주간 지원 요청",
        )
        payload.payload["ticket_status"] = "pending"
        payload.payload["support_request_status"] = "pending"
        self.assertEqual(_resolve_support_assignment_materialization_action(payload), "UPSERT")

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
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_applies_internal_schedule_sync(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "기존근무자"}],
            "shift_type": "day",
            "work_date": "2026-04-01",
            "source_ticket_id": 42,
        }
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
        self.assertEqual(result["schedule_retract_before_apply"]["retracted_count"], 1)
        self.assertEqual(mock_retract_schedule.call_args.kwargs["shift_type"], "day")
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
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_respects_night_period_from_payload(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_upsert_support,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 2,
            "rows": [{"employee_name": "기존야간1"}, {"employee_name": "기존야간2"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 77,
        }
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
        self.assertEqual(result["schedule_retract_before_apply"]["retracted_count"], 2)
        self.assertEqual(mock_retract_schedule.call_args.kwargs["shift_type"], "night")
        self.assertEqual(mock_upsert_schedule.call_args.args[6], "night")
        self.assertEqual(mock_upsert_support.call_args.kwargs["support_period"], "night")
        self.assertEqual(mock_delete_assignments.call_args.kwargs["support_period"], "night")

    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._upsert_materialized_schedule_row")
    def test_support_assignment_ticket_empty_snapshot_clears_existing_schedule_rows(
        self,
        mock_upsert_schedule,
        mock_retract_schedule,
        mock_resolve_targets,
        mock_delete_assignments,
    ):
        mock_retract_schedule.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "서성원"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 153,
        }
        payload = self._build_payload(
            event_type="support_assignment_approved",
            work_type="NIGHT",
            template_type="야간 지원 요청",
        )
        payload.payload["internal_staff_employee_codes"] = []
        payload.payload["internal_staff_workers"] = []
        payload.payload["confirmed_workers"] = []

        result = _apply_support_assignment_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=payload,
            work_date=date(2026, 4, 1),
            ticket_id=153,
        )

        self.assertTrue(result["support_assignment"])
        self.assertEqual(result["action"], "UPSERT")
        self.assertEqual(result["target_count"], 0)
        self.assertTrue(result["internal_schedule_sync"]["snapshot_empty"])
        self.assertEqual(result["schedule_retract_before_apply"]["retracted_count"], 1)
        self.assertEqual(mock_retract_schedule.call_args.kwargs["shift_type"], "night")
        mock_resolve_targets.assert_not_called()
        mock_upsert_schedule.assert_not_called()
        self.assertEqual(mock_delete_assignments.call_count, 2)

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

    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_support_retract_clears_targeted_night_rows_when_ticket_match_misses(
        self,
        mock_resolve_targets,
        mock_retract_ticket_rows,
        mock_retract_target_rows,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-night-2",
                "employee_code": "R692-0020",
                "full_name": "서성원",
            }
        ]
        mock_retract_ticket_rows.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 222,
        }
        mock_retract_target_rows.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "서성원"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "employee_ids": ["emp-night-2"],
        }

        result = _retract_internal_support_schedule_targets(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-1", "company_id": "comp-1", "site_code": "R692"},
            payload=self._build_payload(
                event_type="support_assignment_retracted",
                work_type="NIGHT",
                template_type="야간 지원 요청",
            ),
            work_date=date(2026, 4, 1),
            ticket_id=222,
            event_type="support_assignment_retracted",
            support_period="night",
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["support_period"], "night")
        self.assertEqual(result["ticket_retract"]["retracted_count"], 0)
        self.assertEqual(result["target_retract"]["retracted_count"], 1)
        self.assertEqual(mock_retract_target_rows.call_args.kwargs["employee_ids"], ["emp-night-2"])

    @patch("app.routers.v1.integrations.delete_apple_report_overnight_records_by_source_ticket")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._delete_overnight_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_overnight_retract_removes_materialized_schedule_and_support_rows(
        self,
        mock_resolve_targets,
        mock_retract_schedule,
        mock_retract_schedule_by_employee,
        mock_delete_overnight_assignments,
        mock_delete_assignments,
        mock_delete_apple_report,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-1",
                "employee_code": "R692-0007",
                "full_name": "조태환",
            }
        ]
        mock_retract_schedule.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "조태환"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 91,
        }
        mock_retract_schedule_by_employee.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "employee_ids": ["emp-1"],
        }
        mock_delete_assignments.return_value = 2
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
        self.assertEqual(result["target_schedule_retract"]["retracted_count"], 0)
        self.assertEqual(result["external_support_count"], 2)
        self.assertEqual(result["apple_report_record_count"], 1)
        self.assertEqual(mock_retract_schedule_by_employee.call_args.kwargs["employee_ids"], ["emp-1"])

    @patch("app.routers.v1.integrations.delete_apple_report_overnight_records_by_source_ticket")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._delete_overnight_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_overnight_retract_clears_targeted_night_rows_when_ticket_match_misses(
        self,
        mock_resolve_targets,
        mock_retract_schedule,
        mock_retract_schedule_by_employee,
        mock_delete_overnight_assignments,
        mock_delete_assignments,
        mock_delete_apple_report,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-night-1",
                "employee_code": "R692-0100",
                "full_name": "최미강",
            }
        ]
        mock_retract_schedule.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "source_ticket_id": 91,
        }
        mock_retract_schedule_by_employee.return_value = {
            "retracted_count": 1,
            "rows": [{"employee_name": "최미강"}],
            "shift_type": "night",
            "work_date": "2026-04-01",
            "employee_ids": ["emp-night-1"],
        }
        mock_delete_assignments.return_value = 0
        mock_delete_overnight_assignments.return_value = []
        mock_delete_apple_report.return_value = []

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

        self.assertTrue(result["changed"])
        self.assertEqual(result["schedule_retract"]["retracted_count"], 0)
        self.assertEqual(result["target_schedule_retract"]["retracted_count"], 1)

    def test_support_assignment_retract_accepts_missing_employee_code(self):
        envelope = SocEventEnvelopeIn.model_validate(
            {
                "event_id": "soc-evt-retract-support-1",
                "event_type": "SUPPORT_ASSIGNMENT_RETRACTED",
                "occurred_at": "2026-03-18T00:00:00Z",
                "ticket": {
                    "id": 153,
                    "tenant_id": "srs_korea",
                    "site_id": "R692",
                    "template_type": "주간 지원 요청",
                    "status": "pending",
                },
                "template_fields": {
                    "request_date": "2026-03-10",
                    "work_type": "DAY",
                },
            }
        )

        event = _to_internal_soc_event(envelope)

        self.assertEqual(event.event_type, "support_assignment_retracted")
        self.assertEqual(event.employee_code, "__SOC_MULTI__")
        self.assertEqual(event.site_code, "R692")

    def test_overnight_retract_accepts_missing_employee_code(self):
        envelope = SocEventEnvelopeIn.model_validate(
            {
                "event_id": "soc-evt-retract-overnight-1",
                "event_type": "OVERNIGHT_RETRACTED",
                "occurred_at": "2026-03-18T00:00:00Z",
                "ticket": {
                    "id": 153,
                    "tenant_id": "srs_korea",
                    "site_id": "R692",
                    "template_type": "야간 지원 요청",
                    "status": "pending",
                },
                "template_fields": {
                    "request_date": "2026-03-10",
                    "work_type": "NIGHT",
                },
            }
        )

        event = _to_internal_soc_event(envelope)

        self.assertEqual(event.event_type, "overnight_retracted")
        self.assertEqual(event.employee_code, "__SOC_OVERNIGHT__")
        self.assertEqual(event.site_code, "R692")

    @patch("app.routers.v1.integrations._resolve_employee_by_site_full_name")
    @patch("app.routers.v1.integrations._resolve_employee_by_external_key")
    def test_resolve_soc_targets_accepts_target_workers_only_for_retract(
        self,
        mock_resolve_by_key,
        mock_resolve_by_name,
    ):
        mock_resolve_by_key.return_value = None
        mock_resolve_by_name.return_value = {
            "id": "emp-r692-night-1",
            "employee_code": "R692-0100",
            "full_name": "최미강",
            "company_id": "comp-1",
            "site_id": "site-r692",
            "hire_date": None,
            "leave_date": None,
        }
        payload = SocEventIn(
            event_uid="soc-evt-retract-target-workers-1",
            event_type="overnight_retracted",
            tenant_code="SRS_KOREA",
            employee_code="__SOC_OVERNIGHT__",
            site_code="R692",
            work_date=date(2026, 3, 25),
            payload={
                "request_date": "2026-03-25",
                "work_type": "NIGHT",
                "target_workers": [
                    {
                        "employee_name": "최미강",
                        "worker_name": "최미강",
                    }
                ],
            },
            metadata={"template_type": "야간 지원 요청"},
        )

        resolved = _resolve_soc_target_employees(
            object(),
            tenant_id="tenant-1",
            site={"id": "site-r692", "site_code": "R692"},
            payload=payload,
            event_type="overnight_retracted",
        )

        self.assertEqual([row["full_name"] for row in resolved], ["최미강"])
        mock_resolve_by_name.assert_called_once()

    def test_upsert_materialized_schedule_row_marks_non_support_existing_match(self):
        class FakeCursor:
            def __init__(self):
                self.last_sql = ""
                self.last_params = ()
                self.existing_row = {
                    "id": "schedule-existing-1",
                    "source": "monthly_base_upload",
                    "source_ticket_id": None,
                    "shift_start_time": "22:00",
                    "shift_end_time": "08:00",
                    "paid_hours": 10,
                }

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params):
                self.last_sql = sql
                self.last_params = params

            def fetchone(self):
                if "SELECT id" in self.last_sql:
                    return self.existing_row
                return None

        class FakeConn:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def cursor(self):
                return self.cursor_obj

        conn = FakeConn()
        employee = {
            "id": "emp-r692-night-1",
            "company_id": "comp-1",
            "site_id": "site-r692",
            "employee_code": "R692-0100",
            "full_name": "최미강",
        }

        with patch("app.routers.v1.integrations._resolve_materialized_shift_defaults", return_value=("22:00", "08:00", 10)):
            result = _upsert_materialized_schedule_row(
                conn,
                "tenant-1",
                "comp-1",
                "site-r692",
                employee,
                date(2026, 3, 25),
                "night",
                source="SOC",
                source_ticket_id=153,
                schedule_note="SOC overnight assignment",
            )

        self.assertEqual(result["action"], "matched_existing_non_support")
        self.assertFalse(result["source_is_mutable"])
        self.assertEqual(result["existing_source"], "monthly_base_upload")
        self.assertIsNone(result["source_ticket_id"])

    @patch("app.routers.v1.integrations.delete_apple_report_overnight_records_by_source_ticket")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._delete_overnight_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_overnight_retract_r692_2026_03_25_choi_migang_falls_back_to_employee_match(
        self,
        mock_resolve_targets,
        mock_retract_ticket_rows,
        mock_retract_target_rows,
        mock_delete_overnight_assignments,
        mock_delete_support_assignments,
        mock_delete_apple_report,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "emp-r692-night-1",
                "employee_code": "R692-0100",
                "full_name": "최미강",
                "company_id": "comp-1",
                "site_id": "site-r692",
            }
        ]
        mock_retract_ticket_rows.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-03-25",
            "source_ticket_id": 153,
        }
        mock_retract_target_rows.return_value = {
            "retracted_count": 1,
            "rows": [{"id": "schedule-r692-night-1", "employee_name": "최미강"}],
            "shift_type": "night",
            "work_date": "2026-03-25",
            "employee_ids": ["emp-r692-night-1"],
        }
        mock_delete_overnight_assignments.return_value = []
        mock_delete_support_assignments.return_value = 0
        mock_delete_apple_report.return_value = []

        result = _retract_overnight_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-r692", "company_id": "comp-1", "site_code": "R692"},
            payload=SocEventIn(
                event_uid="soc-evt-r692-20260325-night-retract",
                event_type="overnight_retracted",
                tenant_code="SRS_KOREA",
                employee_code="__SOC_OVERNIGHT__",
                site_code="R692",
                work_date=date(2026, 3, 25),
                payload={
                    "request_date": "2026-03-25",
                    "work_type": "NIGHT",
                    "internal_staff_workers": [
                        {
                            "employee_id": "emp-r692-night-1",
                            "employee_code": "R692-0100",
                            "worker_name": "최미강",
                        }
                    ],
                },
                metadata={"template_type": "야간 지원 요청"},
            ),
            work_date=date(2026, 3, 25),
            ticket_id=153,
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["schedule_retract"]["retracted_count"], 0)
        self.assertEqual(result["target_schedule_retract"]["retracted_count"], 1)
        self.assertEqual(result["target_employees"][0]["employee_name"], "최미강")
        self.assertEqual(mock_retract_target_rows.call_args.kwargs["employee_ids"], ["emp-r692-night-1"])

    @patch("app.routers.v1.integrations.delete_apple_report_overnight_records_by_source_ticket")
    @patch("app.routers.v1.integrations.delete_support_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._delete_overnight_assignments_by_source_ticket")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_employees")
    @patch("app.routers.v1.integrations._retract_materialized_schedule_rows_for_ticket")
    @patch("app.routers.v1.integrations._resolve_soc_target_employees")
    def test_overnight_retract_handles_int_support_assignment_delete_result_for_r692_2026_03_25_choi_migang(
        self,
        mock_resolve_targets,
        mock_retract_ticket_rows,
        mock_retract_target_rows,
        mock_delete_overnight_assignments,
        mock_delete_support_assignments,
        mock_delete_apple_report,
    ):
        mock_resolve_targets.return_value = [
            {
                "id": "eb6ff058-d678-4417-9a4f-1c8b42dd80ec",
                "employee_code": "R692-100",
                "full_name": "최미강",
                "company_id": "comp-1",
                "site_id": "site-r692",
            }
        ]
        mock_retract_ticket_rows.return_value = {
            "retracted_count": 1,
            "rows": [{"id": "schedule-r692-night-1", "employee_name": "최미강"}],
            "shift_type": "night",
            "work_date": "2026-03-25",
            "source_ticket_id": 61,
        }
        mock_retract_target_rows.return_value = {
            "retracted_count": 0,
            "rows": [],
            "shift_type": "night",
            "work_date": "2026-03-25",
            "employee_ids": ["eb6ff058-d678-4417-9a4f-1c8b42dd80ec"],
        }
        mock_delete_overnight_assignments.return_value = [{"ticket_id": 61, "requested_count": 1}]
        mock_delete_support_assignments.return_value = 1
        mock_delete_apple_report.return_value = [{"source_ticket_id": 61, "headcount": 1}]

        result = _retract_overnight_for_ticket(
            object(),
            tenant={"id": "tenant-1", "tenant_code": "srs_korea"},
            site={"id": "site-r692", "company_id": "comp-1", "site_code": "R692"},
            payload=SocEventIn(
                event_uid="SOC-61-OVERNIGHT_RETRACTED-f7f6421b1b40",
                event_type="overnight_retracted",
                tenant_code="SRS_KOREA",
                employee_code="__SOC_OVERNIGHT__",
                site_code="R692",
                work_date=date(2026, 3, 25),
                payload={
                    "request_date": "2026-03-25",
                    "work_type": "NIGHT",
                    "internal_staff_workers": [
                        {
                            "employee_id": "eb6ff058-d678-4417-9a4f-1c8b42dd80ec",
                            "employee_code": "R692-100",
                            "worker_name": "최미강",
                        }
                    ],
                },
                metadata={"template_type": "야간 지원 요청"},
            ),
            work_date=date(2026, 3, 25),
            ticket_id=61,
        )

        self.assertTrue(result["changed"])
        self.assertEqual(result["schedule_retract"]["retracted_count"], 1)
        self.assertEqual(result["external_support_count"], 1)
        self.assertEqual(result["external_support_rows"], [])


if __name__ == "__main__":
    unittest.main()
