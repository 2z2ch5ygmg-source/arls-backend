from __future__ import annotations

from datetime import date
import unittest
from pathlib import Path

from openpyxl import load_workbook

from app.routers.v1.schedules import (
    ARLS_EXPORT_SOURCE_VERSION,
    ARLS_EXPORT_TEMPLATE_VERSION,
    ARLS_SHEET_NAME,
    _build_arls_month_sheet,
    _build_schedule_import_mapping_lookup,
    _locate_support_section_rows,
    _parse_arls_canonical_import_sheet,
    _parse_daytime_need_value,
    _parse_support_worker_cell,
    _read_arls_export_metadata,
    _resolve_import_body_value,
    _resolve_shift_type_from_duty_type,
    _validate_mapping_profile_requirements,
    _validate_arls_import_metadata,
)


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "app" / "templates" / "monthly_schedule_template.xlsx"


class MonthlyScheduleCanonicalImportTests(unittest.TestCase):
    def _build_sample_workbook(self):
        workbook = load_workbook(TEMPLATE_PATH)
        _build_arls_month_sheet(
            workbook,
            month_key="2026-03",
            rows=[
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
                },
                {
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "이보한",
                    "sequence_no": 1,
                    "schedule_date": "2026-03-01",
                    "duty_type": "night",
                    "shift_type": "night",
                    "paid_hours": 10,
                    "shift_start_time": "22:00:00",
                    "shift_end_time": "08:00:00",
                    "soc_role": "Supervisor",
                },
                {
                    "employee_id": "emp-2",
                    "employee_code": "R692-2",
                    "employee_name": "서성원",
                    "sequence_no": 2,
                    "schedule_date": "2026-03-02",
                    "duty_type": "day",
                    "shift_type": "day",
                    "paid_hours": 10,
                    "shift_start_time": "08:00:00",
                    "shift_end_time": "18:00:00",
                    "soc_role": "Officer",
                },
            ],
            tenant_code="srs_korea",
            site_code="R692",
            site_name="Apple_가로수길",
            site_address="서울시 강남구",
            daytime_need_rows=[
                {
                    "work_date": date(2026, 3, 1),
                    "required_count": 4,
                    "raw_text": "4",
                }
            ],
            export_revision="rev-20260309",
            template_version=ARLS_EXPORT_TEMPLATE_VERSION,
            source_version=ARLS_EXPORT_SOURCE_VERSION,
        )
        return workbook

    def test_metadata_validation_accepts_matching_export(self):
        workbook = self._build_sample_workbook()
        metadata = _read_arls_export_metadata(workbook)
        errors = _validate_arls_import_metadata(
            metadata,
            expected_tenant_code="srs_korea",
            expected_site_code="R692",
            expected_month="2026-03",
        )
        self.assertEqual(errors, [])

    def test_metadata_validation_rejects_mismatch(self):
        workbook = self._build_sample_workbook()
        metadata = _read_arls_export_metadata(workbook)
        errors = _validate_arls_import_metadata(
            metadata,
            expected_tenant_code="srs_korea",
            expected_site_code="R999",
            expected_month="2026-03",
        )
        self.assertIn("metadata_mismatch:site_code", errors)

    def test_parse_canonical_sheet_reads_body_need_and_protected_sections(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        rows_meta = _locate_support_section_rows(sheet)
        sheet["D6"] = "연차"
        sheet.cell(row=rows_meta["day_need_row"], column=4, value="5")
        sheet.cell(row=rows_meta["night_need_row"], column=4, value="3")
        sheet.cell(row=rows_meta["night_rows"][0], column=4, value="홍길동")
        sheet.cell(row=rows_meta["work_note_row"], column=4, value="정기 점검")

        parsed = _parse_arls_canonical_import_sheet(sheet)
        body = parsed["body_cells"]
        need_cells = parsed["need_cells"]
        support_cells = parsed["support_cells"]

        leave_cell = next(
            row for row in body
            if row["employee_name"] == "이보한"
            and row["duty_type"] == "overtime"
            and row["schedule_date"].isoformat() == "2026-03-01"
        )
        need_cell = next(row for row in need_cells if row["schedule_date"].isoformat() == "2026-03-01")
        protected_cell = next(
            row for row in support_cells
            if row["schedule_date"].isoformat() == "2026-03-01"
            and row["section_label"] == "야간 지원 근무자"
        )
        support_block = next(
            row for row in parsed["support_blocks"]
            if row["target_date"].isoformat() == "2026-03-01"
            and row["block_type"] == "night_support"
        )
        night_need_cell = next(
            row for row in need_cells
            if row["schedule_date"].isoformat() == "2026-03-01"
            and row["source_block"] == "night_support_required_count"
        )

        self.assertEqual(leave_cell["work_value"], "연차")
        self.assertEqual(need_cell["work_value"], "5")
        self.assertEqual(night_need_cell["work_value"], "3")
        self.assertEqual(protected_cell["work_value"], "홍길동")
        self.assertEqual(support_block["valid_filled_count"], 1)
        self.assertEqual(support_block["invalid_filled_count"], 0)
        self.assertEqual(support_block["required_count_numeric"], 3)
        self.assertEqual(support_block["purpose_text"], "정기 점검")

    def test_parse_daytime_need_value_supports_numeric_and_text(self):
        self.assertEqual(_parse_daytime_need_value("4"), (4, "4"))
        self.assertEqual(_parse_daytime_need_value("5인"), (5, "5인"))
        self.assertEqual(_parse_daytime_need_value("섭외 2인 요청"), (2, "섭외 2인 요청"))
        self.assertEqual(_parse_daytime_need_value("-"), (0, "-"))
        self.assertEqual(_parse_daytime_need_value("미정"), (None, "미정"))

    def test_resolve_import_body_value_uses_leave_marker_convention(self):
        resolved, code, message = _resolve_import_body_value(
            templates=[],
            duty_type="overtime",
            workbook_value="연차",
        )
        self.assertIsNone(code)
        self.assertIsNone(message)
        self.assertEqual(resolved["shift_type"], "off")
        self.assertEqual(resolved["work_value"], "연차")

    def test_resolve_import_body_value_matches_template_for_numeric_hours(self):
        templates = [
            {
                "id": "tpl-day-12",
                "template_name": "주간 12시간",
                "duty_type": "day",
                "start_time": "10:00:00",
                "end_time": "22:00:00",
                "paid_hours": 12,
            },
            {
                "id": "tpl-night-10",
                "template_name": "야간 10시간",
                "duty_type": "night",
                "start_time": "22:00:00",
                "end_time": "08:00:00",
                "paid_hours": 10,
            },
        ]
        mapping_profile = {
            "entries": [
                {
                    "row_type": "night",
                    "numeric_hours": 10,
                    "template_id": "tpl-night-10",
                    "template_name": "야간 10시간",
                    "template_is_active": True,
                }
            ]
        }
        resolved, code, message = _resolve_import_body_value(
            templates=templates,
            mapping_lookup=_build_schedule_import_mapping_lookup(mapping_profile),
            duty_type="night",
            workbook_value="10",
        )
        self.assertIsNone(code)
        self.assertIsNone(message)
        self.assertEqual(resolved["template_id"], "tpl-night-10")
        self.assertEqual(resolved["shift_type"], "night")

    def test_resolve_import_body_value_requires_mapping_when_lookup_is_supplied(self):
        templates = [
            {
                "id": "tpl-day-12",
                "template_name": "주간 12시간",
                "duty_type": "day",
                "start_time": "10:00:00",
                "end_time": "22:00:00",
                "paid_hours": 12,
            }
        ]
        resolved, code, message = _resolve_import_body_value(
            templates=templates,
            mapping_lookup={},
            duty_type="day",
            workbook_value="12",
        )
        self.assertEqual(resolved, {})
        self.assertEqual(code, "TEMPLATE_MAPPING_MISSING")
        self.assertEqual(message, "매핑 가능한 근무 템플릿이 없습니다.")

    def test_validate_mapping_profile_requirements_requires_active_profile_for_numeric_hours(self):
        workbook = self._build_sample_workbook()
        parsed = _parse_arls_canonical_import_sheet(workbook[ARLS_SHEET_NAME])
        issues, blocked_reasons, missing_entries = _validate_mapping_profile_requirements(
            body_cells=parsed["body_cells"],
            mapping_profile=None,
            mapping_lookup={},
        )
        self.assertTrue(issues)
        self.assertTrue(blocked_reasons)
        self.assertTrue(missing_entries)

    def test_parse_support_worker_cell_rejects_multi_person_input(self):
        parsed = _parse_support_worker_cell("BK 박준연 / BK 김민수")
        self.assertEqual(parsed["issue_code"], "MULTI_PERSON_CELL")
        self.assertTrue(parsed["is_filled"])

    def test_locate_support_section_rows_separates_day_and_night_meta_rows(self):
        workbook = self._build_sample_workbook()
        rows_meta = _locate_support_section_rows(workbook[ARLS_SHEET_NAME])
        self.assertEqual(rows_meta["day_vendor_count_row"], 54)
        self.assertEqual(rows_meta["day_need_row"], 55)
        self.assertEqual(rows_meta["night_vendor_count_row"], 64)
        self.assertEqual(rows_meta["night_need_row"], 65)
        self.assertEqual(rows_meta["work_note_row"], 66)

    def test_resolve_shift_type_from_duty_type_keeps_overtime_distinct(self):
        self.assertEqual(_resolve_shift_type_from_duty_type("overtime"), "overtime")

    def test_parse_canonical_sheet_ignores_placeholder_zero_employee_rows(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        sheet["B5"] = "0"
        sheet["B8"] = 0

        parsed = _parse_arls_canonical_import_sheet(sheet)

        self.assertEqual(parsed["body_cells"], [])
        self.assertFalse(any(row.get("employee_name") in {"0", 0} for row in parsed["body_cells"]))

    def test_support_section_label_normalization_accepts_newlines_and_spacing(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        rows_meta = _locate_support_section_rows(sheet)
        sheet.cell(row=rows_meta["weekly_rows"][0], column=2, value="주간\n추가 근무자")
        sheet.cell(row=rows_meta["night_rows"][0], column=2, value="야간\n추가 근무자")
        sheet.cell(row=rows_meta["day_vendor_count_row"], column=3, value="외부인원 \n투입 수")
        sheet.cell(row=rows_meta["work_note_row"], column=3, value="작업 내용")
        sheet.cell(row=rows_meta["work_note_row"], column=4, value="정기 점검")

        relocated = _locate_support_section_rows(sheet)
        parsed = _parse_arls_canonical_import_sheet(sheet)
        night_block = next(
            row for row in parsed["support_blocks"]
            if row["target_date"].isoformat() == "2026-03-01"
            and row["block_type"] == "night_support"
        )

        self.assertEqual(relocated["weekly_rows"], rows_meta["weekly_rows"])
        self.assertEqual(relocated["night_rows"], rows_meta["night_rows"])
        self.assertEqual(relocated["day_vendor_count_row"], rows_meta["day_vendor_count_row"])
        self.assertEqual(relocated["work_note_row"], rows_meta["work_note_row"])
        self.assertEqual(night_block["purpose_text"], "정기 점검")

    def test_blank_support_required_count_with_no_demand_is_non_blocking(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        rows_meta = _locate_support_section_rows(sheet)
        sheet.cell(row=rows_meta["day_need_row"], column=4).value = None
        sheet.cell(row=rows_meta["day_vendor_count_row"], column=4).value = None

        parsed = _parse_arls_canonical_import_sheet(sheet)
        block = next(
            row for row in parsed["support_blocks"]
            if row["target_date"].isoformat() == "2026-03-01"
            and row["block_type"] == "day_support"
        )
        need_cell = next(
            row for row in parsed["need_cells"]
            if row["schedule_date"].isoformat() == "2026-03-01"
            and row["source_block"] == "day_support_required_count"
        )

        self.assertEqual(block["required_count_state"], "no_demand")
        self.assertEqual(block["required_count_numeric"], 0)
        self.assertEqual(need_cell["parsed_semantic_type"], "no_demand")
        self.assertIsNone(need_cell["issue_code"])
        self.assertNotIn("SUPPORT_BLOCK_REQUIRED_COUNT_INVALID", block["issues"])

    def test_blank_support_required_count_with_meaningful_payload_is_blocking(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        rows_meta = _locate_support_section_rows(sheet)
        sheet.cell(row=rows_meta["day_need_row"], column=4).value = None
        sheet.cell(row=rows_meta["weekly_rows"][0], column=4, value="홍길동")

        parsed = _parse_arls_canonical_import_sheet(sheet)
        block = next(
            row for row in parsed["support_blocks"]
            if row["target_date"].isoformat() == "2026-03-01"
            and row["block_type"] == "day_support"
        )
        need_cell = next(
            row for row in parsed["need_cells"]
            if row["schedule_date"].isoformat() == "2026-03-01"
            and row["source_block"] == "day_support_required_count"
        )

        self.assertEqual(block["required_count_state"], "invalid_blank")
        self.assertIsNone(block["required_count_numeric"])
        self.assertEqual(need_cell["issue_code"], "SUPPORT_BLOCK_REQUIRED_COUNT_INVALID")
        self.assertIn("SUPPORT_BLOCK_REQUIRED_COUNT_INVALID", block["issues"])


if __name__ == "__main__":
    unittest.main()
