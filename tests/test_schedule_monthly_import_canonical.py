from __future__ import annotations

from datetime import date, datetime, timedelta
import unittest
from pathlib import Path
from unittest.mock import patch

from openpyxl import load_workbook

from app.routers.v1.schedules import (
    ARLS_MONTHLY_BASE_UPLOAD_SOURCE,
    ARLS_EXPORT_SOURCE_VERSION,
    ARLS_EXPORT_TEMPLATE_VERSION,
    ARLS_SHEET_NAME,
    _build_support_request_rows_from_import_payloads,
    _classify_import_preview_visibility,
    _build_arls_month_sheet,
    _build_import_current_body_index_from_existing_schedule_rows,
    _format_schedule_import_mapping_requirement_label,
    _build_schedule_import_mapping_lookup,
    _collect_monthly_export_context,
    _extract_arls_date_columns,
    _leader_candidate_role_label,
    _leader_candidate_role_priority,
    _locate_support_section_rows,
    _parse_arls_canonical_import_sheet,
    _parse_daytime_need_value,
    _parse_support_worker_cell,
    _read_monthly_support_request_rows_for_export,
    _read_arls_export_metadata,
    _resolve_leader_candidate_role_key,
    _resolve_import_body_value,
    _resolve_schedule_display_meta,
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

    def test_extract_date_columns_prefers_actual_header_dates_over_stale_month_label(self):
        workbook = self._build_sample_workbook()
        sheet = workbook[ARLS_SHEET_NAME]
        sheet.cell(row=2, column=2, value="2026년 3월")
        start_day = datetime(2026, 2, 1)
        for offset in range(31):
            sheet.cell(row=2, column=4 + offset, value=start_day + timedelta(days=offset))

        date_columns, month_ctx = _extract_arls_date_columns(sheet)

        self.assertEqual(month_ctx, (2026, 2))
        self.assertEqual(date_columns[4].isoformat(), "2026-02-01")
        self.assertEqual(date_columns[5].isoformat(), "2026-02-02")

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

    def test_preview_visibility_marks_base_review_rows_as_actionable(self):
        visibility_class, actionable, protected_info_only = _classify_import_preview_visibility({
            "source_block": "body",
            "parsed_semantic_type": "numeric_hours",
            "diff_category": "review",
            "is_blocking": False,
            "is_protected": False,
            "is_valid": True,
        })
        self.assertEqual(visibility_class, "review_actionable")
        self.assertTrue(actionable)
        self.assertFalse(protected_info_only)

    def test_preview_visibility_hides_support_metadata_rows_from_default_preview(self):
        visibility_class, actionable, protected_info_only = _classify_import_preview_visibility({
            "source_block": "day_support_worker",
            "parsed_semantic_type": "protected_support_names",
            "diff_category": "ignored_protected",
            "is_blocking": False,
            "is_protected": True,
            "is_valid": True,
        })
        self.assertEqual(visibility_class, "protected_info_only")
        self.assertFalse(actionable)
        self.assertTrue(protected_info_only)

    def test_preview_visibility_keeps_blocked_support_rows_actionable(self):
        visibility_class, actionable, protected_info_only = _classify_import_preview_visibility({
            "source_block": "night_support_required_count",
            "parsed_semantic_type": "support_demand",
            "diff_category": "invalid",
            "is_blocking": True,
            "is_protected": False,
            "is_valid": False,
        })
        self.assertEqual(visibility_class, "blocked")
        self.assertTrue(actionable)
        self.assertFalse(protected_info_only)

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
        self.assertIn("주간근무 10시간", " ".join(blocked_reasons))

    def test_format_schedule_import_mapping_requirement_label_is_operator_friendly(self):
        self.assertEqual(
            _format_schedule_import_mapping_requirement_label("day", 10),
            "주간근무 10시간",
        )
        self.assertEqual(
            _format_schedule_import_mapping_requirement_label("night", "10.00"),
            "야간근무 10시간",
        )

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

    def test_build_support_request_rows_from_import_payloads_keeps_meaningful_day_and_night_scopes(self):
        rows = _build_support_request_rows_from_import_payloads(
            [
                {
                    "source_block": "sentrix_support_ticket",
                    "schedule_date": date(2026, 3, 2),
                    "shift_type": "day",
                    "request_count": 2,
                    "work_value": "섭외 2인 요청",
                    "purpose_text": "",
                    "detail_json": {"external_count_raw": "1"},
                },
                {
                    "source_block": "sentrix_support_ticket",
                    "schedule_date": date(2026, 3, 2),
                    "shift_type": "night",
                    "request_count": 3,
                    "work_value": "섭외 3인 요청",
                    "purpose_text": "프로젝트",
                    "detail_json": {"required_row_no": 65},
                },
                {
                    "source_block": "sentrix_support_ticket",
                    "schedule_date": date(2026, 3, 3),
                    "shift_type": "day",
                    "request_count": 0,
                    "work_value": "",
                    "detail_json": {},
                },
                {
                    "source_block": "sentrix_support_ticket",
                    "schedule_date": date(2026, 3, 4),
                    "shift_type": "day",
                    "request_count": 1,
                    "is_blocking": True,
                    "work_value": "1",
                    "detail_json": {},
                },
            ]
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["shift_kind"], "day")
        self.assertEqual(rows[0]["request_count"], 2)
        self.assertEqual(rows[0]["detail_json"]["required_count_raw"], "섭외 2인 요청")
        self.assertEqual(rows[1]["shift_kind"], "night")
        self.assertEqual(rows[1]["work_purpose"], "프로젝트")

    @patch("app.routers.v1.schedules._load_schedule_import_payload_rows")
    def test_read_monthly_support_request_rows_for_export_prefers_source_batch_payloads(self, mock_load_payload_rows):
        mock_load_payload_rows.return_value = [
            {
                "source_block": "sentrix_support_ticket",
                "schedule_date": date(2026, 3, 15),
                "shift_type": "night",
                "request_count": 2,
                "work_value": "섭외 2인 요청",
                "purpose_text": "야간 작업",
                "detail_json": {"external_count_raw": "0"},
            }
        ]

        rows = _read_monthly_support_request_rows_for_export(
            None,
            tenant_id="tenant-1",
            site_id="site-1",
            month_key="2026-03",
            source_batch_id="batch-123",
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["work_date"].isoformat(), "2026-03-15")
        self.assertEqual(rows[0]["shift_kind"], "night")
        self.assertEqual(rows[0]["request_count"], 2)
        self.assertEqual(rows[0]["work_purpose"], "야간 작업")

    def test_schedule_display_meta_distinguishes_off_holiday_and_annual_leave(self):
        self.assertEqual(
            _resolve_schedule_display_meta({"shift_type": "off", "schedule_note": "연차"})["type"],
            "annual_leave",
        )
        self.assertEqual(
            _resolve_schedule_display_meta({"shift_type": "off", "schedule_note": "반차"})["type"],
            "half_leave",
        )
        self.assertEqual(
            _resolve_schedule_display_meta({"shift_type": "off", "schedule_note": ""})["label"],
            "휴무",
        )
        self.assertEqual(
            _resolve_schedule_display_meta({"shift_type": "holiday", "schedule_note": None})["label"],
            "공휴일",
        )

    def test_leader_role_resolution_preserves_admin_labels(self):
        self.assertEqual(_resolve_leader_candidate_role_key("GUARD", "hq_admin"), "HQ_ADMIN")
        self.assertEqual(_resolve_leader_candidate_role_key("TEAM_MANAGER", "supervisor"), "SUPERVISOR")
        self.assertEqual(_resolve_leader_candidate_role_key("GUARD", "vice_supervisor"), "VICE_SUPERVISOR")
        self.assertEqual(_resolve_leader_candidate_role_key("GUARD", "officer"), "GUARD")
        self.assertEqual(_leader_candidate_role_label("HQ_ADMIN"), "HQ Admin")
        self.assertEqual(_leader_candidate_role_label("SUPERVISOR"), "Supervisor")
        self.assertEqual(_leader_candidate_role_label("VICE_SUPERVISOR"), "Vice Supervisor")
        self.assertEqual(_leader_candidate_role_priority("HQ_ADMIN"), 0)
        self.assertEqual(_leader_candidate_role_priority("GUARD"), 3)

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

    def test_build_import_current_body_index_uses_base_rows_only(self):
        index = _build_import_current_body_index_from_existing_schedule_rows(
            [
                {
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "이보한",
                    "schedule_date": date(2026, 3, 1),
                    "shift_type": "day",
                    "duty_type": "day",
                    "shift_start_time": "08:00:00",
                    "shift_end_time": "18:00:00",
                    "paid_hours": 10,
                    "source": ARLS_MONTHLY_BASE_UPLOAD_SOURCE,
                },
                {
                    "employee_id": "emp-1",
                    "employee_code": "R692-1",
                    "employee_name": "이보한",
                    "schedule_date": date(2026, 3, 1),
                    "shift_type": "day",
                    "duty_type": "day",
                    "shift_start_time": "10:00:00",
                    "shift_end_time": "22:00:00",
                    "paid_hours": 12,
                    "source": "manual_override",
                },
            ]
        )

        current_row = index[("이보한", "day", "2026-03-01")]
        self.assertEqual(current_row["work_value"], "10")

    @patch("app.routers.v1.schedules._build_schedule_export_revision", return_value="rev-preview")
    @patch("app.routers.v1.schedules._read_monthly_support_request_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_daytime_need_rows_for_export")
    @patch("app.routers.v1.schedules._read_monthly_employee_overnight_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_overnight_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_support_assignment_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._build_export_rows_from_board_payload", return_value=[])
    @patch("app.routers.v1.schedules.monthly_board_lite", return_value={})
    @patch("app.routers.v1.schedules._read_monthly_board_rows_for_export", return_value=[])
    def test_collect_monthly_export_context_allows_empty_employee_blocks_for_preview(
        self,
        _mock_board_rows,
        _mock_board_payload,
        _mock_export_rows,
        _mock_support_rows,
        _mock_overnight_rows,
        _mock_employee_overnight_rows,
        mock_daytime_need_rows,
        _mock_support_request_rows,
        _mock_export_revision,
    ):
        mock_daytime_need_rows.return_value = [
            {
                "work_date": date(2026, 3, 1),
                "required_count": 2,
                "raw_text": "2",
            }
        ]

        export_ctx = _collect_monthly_export_context(
            None,
            target_tenant={"id": "tenant-1", "tenant_code": "TENANT"},
            site_row={"id": "site-1", "site_code": "R692", "site_name": "Apple_가로수길", "address": "서울시 강남구"},
            month_key="2026-03",
            user={},
            allow_empty_employee_blocks=True,
        )

        self.assertEqual(export_ctx["employee_blocks"], [])
        self.assertEqual(export_ctx["export_revision"], "rev-preview")
        need_cell = next(
            row for row in export_ctx["parsed_sheet"]["need_cells"]
            if row["source_block"] == "day_support_required_count"
            and row["schedule_date"].isoformat() == "2026-03-01"
        )
        self.assertEqual(need_cell["work_value"], "2")

    @patch("app.routers.v1.schedules._build_schedule_export_revision", return_value="rev-empty-preview")
    @patch("app.routers.v1.schedules._read_monthly_support_request_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_daytime_need_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_employee_overnight_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_overnight_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._read_monthly_support_assignment_rows_for_export", return_value=[])
    @patch("app.routers.v1.schedules._build_export_rows_from_board_payload", return_value=[])
    @patch("app.routers.v1.schedules.monthly_board_lite", return_value={})
    @patch("app.routers.v1.schedules._read_monthly_board_rows_for_export", return_value=[])
    def test_collect_monthly_export_context_returns_empty_current_context_when_no_export_data_for_preview(
        self,
        _mock_board_rows,
        _mock_board_payload,
        _mock_export_rows,
        _mock_support_rows,
        _mock_overnight_rows,
        _mock_employee_overnight_rows,
        _mock_daytime_need_rows,
        _mock_support_request_rows,
        _mock_export_revision,
    ):
        export_ctx = _collect_monthly_export_context(
            None,
            target_tenant={"id": "tenant-1", "tenant_code": "TENANT"},
            site_row={"id": "site-2", "site_code": "M001", "site_name": "명동", "address": "서울시 중구"},
            month_key="2026-03",
            user={},
            allow_empty_employee_blocks=True,
        )

        self.assertEqual(export_ctx["rows"], [])
        self.assertEqual(export_ctx["employee_blocks"], [])
        self.assertEqual(export_ctx["export_revision"], "rev-empty-preview")
        self.assertEqual(export_ctx["parsed_sheet"]["body_cells"], [])
        self.assertEqual(export_ctx["parsed_sheet"]["need_cells"], [])
        self.assertEqual(export_ctx["parsed_sheet"]["support_cells"], [])


if __name__ == "__main__":
    unittest.main()
