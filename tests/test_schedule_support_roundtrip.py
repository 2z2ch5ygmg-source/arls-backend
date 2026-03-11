from __future__ import annotations

from datetime import date
import unittest
from pathlib import Path

from openpyxl import load_workbook

from app.routers.v1.schedules import (
    ARLS_EXPORT_TEMPLATE_VERSION,
    ARLS_SHEET_NAME,
    ARLS_SUPPORT_METADATA_SHEET_NAME,
    GUARD_DAY_SHIFT_HOURS,
    SENTRIX_HQ_ROSTER_ASSIGNMENT_SOURCE,
    _apply_internal_support_roundtrip_assignments,
    _build_export_employee_blocks,
    _build_sentrix_hq_bridge_candidates,
    _build_arls_month_sheet,
    _build_employee_name_index,
    _build_sentrix_hq_snapshot_signature,
    _build_support_only_workbook,
    _build_support_roundtrip_employee_row_index,
    _extract_sentrix_ticket_hq_roster_status,
    _extract_arls_date_columns,
    _locate_support_section_rows,
    _normalize_sentrix_hq_roster_final_state,
    _parse_sentrix_hq_worker_cell,
    _read_support_roundtrip_metadata,
    _resolve_sentrix_support_materialized_shift_defaults,
)


TEMPLATE_PATH = Path("/Users/seoseong-won/Documents/rg-arls-dev/backend/app/templates/monthly_schedule_template.xlsx")


class ScheduleSupportRoundtripTests(unittest.TestCase):
    def _build_export_ctx(self):
        workbook = load_workbook(TEMPLATE_PATH)
        rows = [
            {
                "employee_id": "emp-1",
                "employee_code": "R692-1",
                "employee_name": "이보한",
                "sequence_no": 1,
                "schedule_date": "2026-03-01",
                "duty_type": "day",
                "shift_type": "day",
                "paid_hours": 12,
                "shift_start_time": "10:00:00",
                "shift_end_time": "22:00:00",
                "soc_role": "Supervisor",
            }
        ]
        _build_arls_month_sheet(
            workbook,
            month_key="2026-03",
            rows=rows,
            tenant_code="srs_korea",
            site_code="R692",
            site_name="Apple_가로수길",
            site_address="서울시 강남구",
            daytime_need_rows=[],
            export_revision="rev-support-1",
            template_version=ARLS_EXPORT_TEMPLATE_VERSION,
            source_version="phase1",
        )
        return {
            "workbook": workbook,
            "template_version": ARLS_EXPORT_TEMPLATE_VERSION,
            "employee_blocks": [
                {
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "이보한",
                }
            ],
        }

    def test_build_support_only_workbook_preserves_site_sheet_and_hidden_metadata(self):
        export_ctx = self._build_export_ctx()
        workbook = _build_support_only_workbook(
            export_ctx=export_ctx,
            target_tenant={"tenant_code": "srs_korea"},
            site_row={"site_code": "R692", "site_name": "Apple_가로수길"},
            month_key="2026-03",
            source_revision="src-rev-001",
            active_assignments=[
                {
                    "work_date": date(2026, 3, 1),
                    "support_period": "day",
                    "slot_index": 1,
                    "worker_type": "EXTERNAL",
                    "worker_name": "BK 박준연",
                    "is_internal": False,
                }
            ],
        )

        self.assertIn("Apple_가로수길", workbook.sheetnames)
        self.assertIn(ARLS_SUPPORT_METADATA_SHEET_NAME, workbook.sheetnames)
        meta = _read_support_roundtrip_metadata(workbook)
        self.assertEqual(meta.get("tenant_code"), "srs_korea")
        self.assertEqual(meta.get("site_code"), "R692")
        self.assertEqual(meta.get("month"), "2026-03")
        self.assertEqual(meta.get("source_revision"), "src-rev-001")

    def test_internal_support_overlay_writes_employee_day_and_night_rows(self):
        export_ctx = self._build_export_ctx()
        workbook = export_ctx["workbook"]
        sheet = workbook[ARLS_SHEET_NAME]
        date_columns, _ = _extract_arls_date_columns(sheet)
        day_col = next(col for col, value in date_columns.items() if value.isoformat() == "2026-03-01")
        row_index = _build_support_roundtrip_employee_row_index(sheet, employee_blocks=export_ctx["employee_blocks"])

        _apply_internal_support_roundtrip_assignments(
            sheet,
            export_ctx=export_ctx,
            assignment_rows=[
                {
                    "is_internal": True,
                    "employee_id": "emp-1",
                    "work_date": date(2026, 3, 1),
                    "support_period": "day",
                    "internal_shift_type": "day",
                    "internal_paid_hours": 12,
                },
                {
                    "is_internal": True,
                    "employee_id": "emp-1",
                    "work_date": date(2026, 3, 1),
                    "support_period": "night",
                    "internal_shift_type": "night",
                    "internal_shift_start_time": "22:00:00",
                    "internal_shift_end_time": "08:00:00",
                },
            ],
        )

        self.assertEqual(sheet.cell(row=row_index[("emp-1", "day")], column=day_col).value, "12")
        self.assertEqual(sheet.cell(row=row_index[("emp-1", "night")], column=day_col).value, "10")

    def test_support_only_workbook_keeps_external_display_label_and_extends_slots(self):
        export_ctx = self._build_export_ctx()
        workbook = _build_support_only_workbook(
            export_ctx=export_ctx,
            target_tenant={"tenant_code": "srs_korea"},
            site_row={"site_code": "R692", "site_name": "Apple_가로수길"},
            month_key="2026-03",
            source_revision="src-rev-002",
            active_assignments=[
                {
                    "work_date": date(2026, 3, 1),
                    "support_period": "day",
                    "slot_index": index + 1,
                    "worker_type": "F",
                    "worker_name": "Apple_가로수길 박준연" if index == 0 else f"협력사{index} 지원자{index}",
                    "is_internal": False,
                }
                for index in range(7)
            ],
        )

        sheet = workbook["Apple_가로수길"]
        date_columns, _ = _extract_arls_date_columns(sheet)
        day_col = next(col for col, value in date_columns.items() if value.isoformat() == "2026-03-01")
        rows_meta = _locate_support_section_rows(sheet)

        self.assertGreaterEqual(len(rows_meta["weekly_rows"]), 7)
        self.assertEqual(sheet.cell(row=rows_meta["weekly_rows"][0], column=day_col).value, "Apple_가로수길 박준연")

    def test_parse_sentrix_hq_worker_cell_normalizes_external_and_internal(self):
        employee_index = _build_employee_name_index(
            [
                {
                    "id": "emp-1",
                    "employee_code": "R692-1",
                    "full_name": "조태환",
                    "hire_date": date(2025, 1, 1),
                    "leave_date": None,
                }
            ]
        )

        external = _parse_sentrix_hq_worker_cell(
            "bk   박준연",
            schedule_date=date(2026, 3, 1),
            employee_index=employee_index,
        )
        self.assertTrue(external["is_valid"])
        self.assertEqual(external["affiliation"], "BK")
        self.assertEqual(external["name"], "박준연")
        self.assertEqual(external["display_value"], "BK 박준연")
        self.assertEqual(external["worker_type"], "BK")

        internal = _parse_sentrix_hq_worker_cell(
            "자체 조태환",
            schedule_date=date(2026, 3, 1),
            employee_index=employee_index,
        )
        self.assertTrue(internal["is_valid"])
        self.assertTrue(internal["self_staff"])
        self.assertEqual(internal["employee_id"], "emp-1")
        self.assertEqual(internal["worker_type"], "INTERNAL")

    def test_parse_sentrix_hq_worker_cell_rejects_multi_person_and_invalid_self(self):
        employee_index = _build_employee_name_index(
            [
                {
                    "id": "emp-1",
                    "employee_code": "R692-1",
                    "full_name": "조태환",
                    "hire_date": date(2025, 1, 1),
                    "leave_date": None,
                },
                {
                    "id": "emp-2",
                    "employee_code": "R692-2",
                    "full_name": "조태환",
                    "hire_date": date(2025, 1, 1),
                    "leave_date": None,
                },
            ]
        )

        multi = _parse_sentrix_hq_worker_cell(
            "BK 박준연 / BK 김하늘",
            schedule_date=date(2026, 3, 1),
            employee_index=employee_index,
        )
        self.assertFalse(multi["is_valid"])
        self.assertEqual(multi["issue_code"], "MULTI_PERSON_CELL")

        invalid_self = _parse_sentrix_hq_worker_cell(
            "자체 bk 박준연",
            schedule_date=date(2026, 3, 1),
            employee_index=employee_index,
        )
        self.assertFalse(invalid_self["is_valid"])
        self.assertEqual(invalid_self["issue_code"], "SELF_STAFF_FORMAT_INVALID")

        ambiguous_self = _parse_sentrix_hq_worker_cell(
            "자체 조태환",
            schedule_date=date(2026, 3, 1),
            employee_index=employee_index,
        )
        self.assertFalse(ambiguous_self["is_valid"])
        self.assertEqual(ambiguous_self["issue_code"], "SELF_STAFF_EMPLOYEE_AMBIGUOUS")

    def test_extract_sentrix_ticket_hq_roster_status_prefers_detail_json(self):
        self.assertEqual(
            _extract_sentrix_ticket_hq_roster_status(
                {
                    "detail_json": {
                        "hq_roster": {
                            "status": "auto_approved",
                        }
                    }
                }
            ),
            "auto_approved",
        )
        self.assertEqual(
            _extract_sentrix_ticket_hq_roster_status(
                {
                    "detail_json": {
                        "hq_roster": {
                            "status": "approval_pending",
                        }
                    }
                }
            ),
            "approval_pending",
        )
        self.assertIsNone(_extract_sentrix_ticket_hq_roster_status({"detail_json": {}}))

    def test_normalize_sentrix_hq_roster_final_state_maps_auto_approved_to_approved(self):
        self.assertEqual(_normalize_sentrix_hq_roster_final_state("auto_approved"), "approved")
        self.assertEqual(_normalize_sentrix_hq_roster_final_state("approval_pending"), "approval_pending")
        self.assertEqual(_normalize_sentrix_hq_roster_final_state("APPROVED"), "approved")

    def test_build_sentrix_hq_bridge_candidates_keeps_unique_self_staff_employee(self):
        candidates = _build_sentrix_hq_bridge_candidates(
            [
                {
                    "slot_index": 1,
                    "self_staff": True,
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "조태환",
                    "display_value": "자체 조태환",
                    "validity_state": "valid",
                },
                {
                    "slot_index": 2,
                    "self_staff": True,
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "조태환",
                    "display_value": "자체 조태환",
                    "validity_state": "valid",
                },
                {
                    "slot_index": 3,
                    "self_staff": False,
                    "employee_id": None,
                    "display_value": "BK 박준연",
                    "validity_state": "valid",
                },
            ]
        )
        self.assertEqual(list(candidates.keys()), ["emp-1"])
        self.assertEqual(candidates["emp-1"]["employee_name"], "조태환")

    def test_sentrix_hq_snapshot_signature_changes_when_ticket_state_changes(self):
        base_entries = [
            {
                "slot_index": 1,
                "display_value": "자체 조태환",
                "self_staff": True,
                "employee_id": "emp-1",
                "employee_code": "R692-1",
                "employee_name": "조태환",
                "worker_type": "INTERNAL",
                "validity_state": "valid",
            }
        ]
        approved_signature = _build_sentrix_hq_snapshot_signature(
            entries=base_entries,
            request_count=1,
            valid_filled_count=1,
            invalid_filled_count=0,
            ticket_state="approved",
        )
        pending_signature = _build_sentrix_hq_snapshot_signature(
            entries=base_entries,
            request_count=1,
            valid_filled_count=1,
            invalid_filled_count=0,
            ticket_state="approval_pending",
        )
        self.assertNotEqual(approved_signature, pending_signature)

    def test_build_export_employee_blocks_skips_hq_roundtrip_internal_overlay(self):
        rows = []
        blocks = _build_export_employee_blocks(
            rows,
            support_rows=[
                {
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "조태환",
                    "work_date": date(2026, 3, 1),
                    "support_period": "day",
                    "is_internal": True,
                    "source": SENTRIX_HQ_ROSTER_ASSIGNMENT_SOURCE,
                    "soc_role": "guard",
                    "duty_role": "GUARD",
                }
            ],
        )
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["day"], {})

    def test_resolve_sentrix_support_materialized_shift_defaults_uses_day_and_night_rules(self):
        guard_employee = {
            "soc_role": "guard",
            "duty_role": "GUARD",
        }
        start_time, end_time, paid_hours = _resolve_sentrix_support_materialized_shift_defaults(
            guard_employee,
            shift_kind="day",
        )
        self.assertEqual(start_time, "10:00:00")
        self.assertEqual(end_time, "22:00:00")
        self.assertEqual(paid_hours, GUARD_DAY_SHIFT_HOURS)

        night_start, night_end, night_hours = _resolve_sentrix_support_materialized_shift_defaults(
            guard_employee,
            shift_kind="night",
        )
        self.assertEqual(night_start, "22:00:00")
        self.assertEqual(night_end, "08:00:00")
        self.assertEqual(night_hours, 10.0)


if __name__ == "__main__":
    unittest.main()
