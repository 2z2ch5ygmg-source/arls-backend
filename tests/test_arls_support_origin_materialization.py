from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from app.routers.v1.schedules import (
    SENTRIX_ARLS_BRIDGE_ACTION_RETRACT,
    SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
    SENTRIX_ARLS_BRIDGE_SOURCE,
    SENTRIX_HQ_ROSTER_FINAL_APPROVED_STATE,
    SENTRIX_HQ_ROSTER_PENDING_STATUS,
    SENTRIX_SUPPORT_MATERIALIZATION_MODE_LINKED,
    _apply_sentrix_support_bridge_action,
    _validate_sentrix_support_bridge_action_payload,
)


class _FakeCursor:
    def __init__(self) -> None:
        self.connection = object()
        self.executed: list[tuple[str, object]] = []
        self.rowcount = 0
        self._fetchone = None

    def execute(self, query: str, params=None) -> None:
        self.executed.append((query, params))
        self.rowcount = 0
        self._fetchone = None

    def fetchone(self):
        return self._fetchone


class ArlsSupportOriginMaterializationTests(unittest.TestCase):
    def _build_action_row(self, *, action: str, ticket_state: str, payload_overrides: dict | None = None) -> dict:
        payload = {
            "source": SENTRIX_ARLS_BRIDGE_SOURCE,
            "source_ticket_id": "ticket-1",
            "ticket_state": ticket_state,
            "site_id": "site-1",
            "site_code": "R692",
            "work_date": "2026-04-01",
            "shift_kind": "night",
            "employee_id": "emp-7",
            "employee_display_name": "조태환",
            "self_staff": True,
            "action": action,
            "snapshot_id": "snapshot-1",
        }
        if payload_overrides:
            payload.update(payload_overrides)
        return {
            "id": "bridge-1",
            "ticket_id": "ticket-1",
            "batch_id": "batch-1",
            "snapshot_id": "snapshot-1",
            "site_id": "site-1",
            "site_code": "R692",
            "work_date": date(2026, 4, 1),
            "shift_kind": "night",
            "employee_id": "emp-7",
            "employee_name": "조태환",
            "action": action,
            "ticket_state": ticket_state,
            "payload_json": payload,
        }

    def test_validate_sentrix_support_bridge_action_payload_rejects_non_self_staff_payload(self):
        action_row = self._build_action_row(
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            ticket_state=SENTRIX_HQ_ROSTER_FINAL_APPROVED_STATE,
            payload_overrides={"self_staff": False},
        )

        with self.assertRaisesRegex(RuntimeError, "self-staff"):
            _validate_sentrix_support_bridge_action_payload(
                action_row,
                payload=action_row["payload_json"],
                shift_kind="night",
                bridge_action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
                ticket_state=SENTRIX_HQ_ROSTER_FINAL_APPROVED_STATE,
                work_date=action_row["work_date"],
            )

    @patch("app.routers.v1.schedules._upsert_sentrix_support_materialization_row")
    @patch("app.routers.v1.schedules._insert_monthly_schedule_row")
    @patch("app.routers.v1.schedules._update_monthly_schedule_row")
    @patch("app.routers.v1.schedules._resolve_sentrix_support_materialized_shift_defaults")
    @patch("app.routers.v1.schedules._load_monthly_schedule_row_for_shift")
    @patch("app.routers.v1.schedules._load_sentrix_support_materialization_row")
    @patch("app.routers.v1.schedules._resolve_sentrix_support_bridge_employee")
    @patch("app.routers.v1.schedules._resolve_sentrix_support_bridge_site")
    def test_upsert_updates_same_ticket_lineage_without_duplicate(
        self,
        mock_resolve_site,
        mock_resolve_employee,
        mock_load_materialization,
        mock_load_schedule,
        mock_resolve_shift_defaults,
        mock_update_schedule,
        mock_insert_schedule,
        mock_upsert_materialization,
    ):
        cur = _FakeCursor()
        action_row = self._build_action_row(
            action=SENTRIX_ARLS_BRIDGE_ACTION_UPSERT,
            ticket_state=SENTRIX_HQ_ROSTER_FINAL_APPROVED_STATE,
        )
        mock_resolve_site.return_value = {"id": "site-1", "site_code": "R692", "company_id": "comp-1"}
        mock_resolve_employee.return_value = {"id": "emp-7", "employee_code": "R692-0007", "full_name": "조태환"}
        mock_load_materialization.return_value = None
        mock_load_schedule.return_value = {
            "id": "schedule-1",
            "source": SENTRIX_ARLS_BRIDGE_SOURCE,
            "source_ticket_uuid": "ticket-1",
            "schedule_note": None,
        }
        mock_resolve_shift_defaults.return_value = ("22:00:00", "08:00:00", 10.0)
        mock_upsert_materialization.return_value = "mat-1"

        result = _apply_sentrix_support_bridge_action(
            cur,
            tenant_id="tenant-1",
            action_row=action_row,
        )

        self.assertEqual(result["schedule_effect"], "updated")
        self.assertEqual(result["monthly_schedule_id"], "schedule-1")
        self.assertEqual(result["status"], "active")
        mock_update_schedule.assert_called_once()
        mock_insert_schedule.assert_not_called()
        mock_upsert_materialization.assert_called_once()

    @patch("app.routers.v1.schedules._upsert_sentrix_support_materialization_row")
    @patch("app.routers.v1.schedules._load_monthly_schedule_row_for_shift")
    @patch("app.routers.v1.schedules._load_sentrix_support_materialization_row")
    @patch("app.routers.v1.schedules._resolve_sentrix_support_bridge_employee")
    @patch("app.routers.v1.schedules._resolve_sentrix_support_bridge_site")
    def test_retract_preserves_linked_existing_base_row(
        self,
        mock_resolve_site,
        mock_resolve_employee,
        mock_load_materialization,
        mock_load_schedule,
        mock_upsert_materialization,
    ):
        cur = _FakeCursor()
        action_row = self._build_action_row(
            action=SENTRIX_ARLS_BRIDGE_ACTION_RETRACT,
            ticket_state=SENTRIX_HQ_ROSTER_PENDING_STATUS,
        )
        mock_resolve_site.return_value = {"id": "site-1", "site_code": "R692", "company_id": "comp-1"}
        mock_resolve_employee.return_value = {"id": "emp-7", "employee_code": "R692-0007", "full_name": "조태환"}
        mock_load_materialization.return_value = {
            "id": "mat-1",
            "coexistence_mode": SENTRIX_SUPPORT_MATERIALIZATION_MODE_LINKED,
            "monthly_schedule_id": "base-row-1",
        }
        mock_load_schedule.return_value = {
            "id": "base-row-1",
            "source": "manual",
            "source_ticket_uuid": None,
        }
        mock_upsert_materialization.return_value = "mat-1"

        result = _apply_sentrix_support_bridge_action(
            cur,
            tenant_id="tenant-1",
            action_row=action_row,
        )

        self.assertEqual(result["schedule_effect"], "noop_already_retracted")
        self.assertEqual(result["monthly_schedule_id"], "base-row-1")
        self.assertEqual(result["status"], "retracted")
        self.assertEqual(cur.executed, [])
        mock_upsert_materialization.assert_called_once()


if __name__ == "__main__":
    unittest.main()
