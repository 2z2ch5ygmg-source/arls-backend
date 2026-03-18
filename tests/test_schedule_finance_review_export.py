from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.routers.v1.schedules import (
    ARLS_METADATA_SHEET_NAME,
    _build_monthly_export_workbook_from_contexts,
    _collect_finance_review_export_context,
    _extract_arls_date_columns,
    _locate_support_section_rows,
)


def _build_site_context(
    *,
    site_code: str,
    site_name: str,
    rows: list[dict],
    support_rows: list[dict] | None = None,
    support_request_rows: list[dict] | None = None,
    employee_overnight_rows: list[dict] | None = None,
    daytime_need_rows: list[dict] | None = None,
    overnight_rows: list[dict] | None = None,
    export_revision: str = "test-revision",
) -> dict:
    return {
        "site_id": f"{site_code}-id",
        "site_code": site_code,
        "site_name": site_name,
        "site_address": f"{site_name} 주소",
        "rows": rows,
        "support_rows": support_rows or [],
        "support_request_rows": support_request_rows or [],
        "overnight_rows": overnight_rows or [],
        "employee_overnight_rows": employee_overnight_rows or [],
        "daytime_need_rows": daytime_need_rows or [],
        "employee_blocks": [{"employee_id": "placeholder"}],
        "export_revision": export_revision,
    }


class FinanceReviewExportTests(unittest.TestCase):
    def _date_col(self, sheet, iso_date: str) -> int:
        date_columns, _month_ctx = _extract_arls_date_columns(sheet)
        for col_idx, current_date in date_columns.items():
            if current_date.isoformat() == iso_date:
                return col_idx
        raise AssertionError(f"missing date column for {iso_date}")

    def test_finance_review_workbook_fills_main_schedule_area_only(self) -> None:
        workbook, template_path, template_version = _build_monthly_export_workbook_from_contexts(
            export_contexts=[
                _build_site_context(
                    site_code="R692",
                    site_name="Apple_가로수길",
                    rows=[
                        {
                            "employee_id": "emp-1",
                            "employee_code": "R692-1",
                            "employee_name": "민경민",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-01",
                            "duty_type": "day",
                            "shift_type": "day",
                            "shift_start_time": "08:00:00",
                            "shift_end_time": "18:00:00",
                            "template_start_time": "08:00:00",
                            "template_end_time": "18:00:00",
                            "paid_hours": None,
                            "soc_role": "Officer",
                        },
                        {
                            "employee_id": "emp-1",
                            "employee_code": "R692-1",
                            "employee_name": "민경민",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-05",
                            "duty_type": "night",
                            "shift_type": "night",
                            "shift_start_time": "22:00:00",
                            "shift_end_time": "08:00:00",
                            "template_start_time": "22:00:00",
                            "template_end_time": "08:00:00",
                            "paid_hours": None,
                            "soc_role": "Officer",
                        },
                    ],
                    support_rows=[
                        {
                            "work_date": date(2026, 3, 1),
                            "support_period": "day",
                            "slot_index": 1,
                            "worker_type": "F",
                            "name": "외부지원",
                            "employee_id": None,
                            "employee_code": None,
                            "employee_name": None,
                            "is_internal": False,
                        }
                    ],
                    support_request_rows=[
                        {
                            "work_date": date(2026, 3, 1),
                            "shift_kind": "night",
                            "request_count": 2,
                            "work_purpose": "테스트 작업",
                            "detail_json": {
                                "required_count_raw": "2",
                                "external_count_raw": "1",
                            },
                        }
                    ],
                    daytime_need_rows=[
                        {
                            "work_date": date(2026, 3, 1),
                            "required_count": 3,
                            "raw_text": "섭외 3인 요청",
                        }
                    ],
                    export_revision="review-revision-1",
                )
            ],
            month_key="2026-03",
            tenant_code="SRS_KOR",
            source_version="finance-review-test",
            include_summary_sections=False,
            include_support_assignment_sections=False,
        )

        self.assertTrue(str(template_path).endswith(".xlsx"))
        self.assertIn("monthly_schedule_template.xlsx", str(template_path))
        self.assertIn("monthly_schedule_template.xlsx", template_version)

        visible_sheet_names = [
            name for name in workbook.sheetnames if workbook[name].sheet_state == "visible"
        ]
        self.assertEqual(visible_sheet_names, ["Apple_가로수길"])

        sheet = workbook["Apple_가로수길"]
        march_1_col = self._date_col(sheet, "2026-03-01")
        march_5_col = self._date_col(sheet, "2026-03-05")

        self.assertEqual(sheet["B2"].value, "2026년 3월")
        self.assertIn("Apple_가로수길", str(sheet["B3"].value or ""))
        self.assertEqual(sheet.cell(row=5, column=march_1_col).value, 10)
        self.assertEqual(sheet.cell(row=7, column=march_5_col).value, 10)

        rows_meta = _locate_support_section_rows(sheet)
        self.assertIsNone(sheet.cell(row=rows_meta["weekly_rows"][0], column=march_1_col).value)
        self.assertIsNone(sheet.cell(row=rows_meta["night_rows"][0], column=march_5_col).value)
        if rows_meta.get("day_need_row"):
            self.assertIsNone(sheet.cell(row=rows_meta["day_need_row"], column=march_1_col).value)
        if rows_meta.get("night_need_row"):
            self.assertIsNone(sheet.cell(row=rows_meta["night_need_row"], column=march_1_col).value)
        if rows_meta.get("work_note_row"):
            self.assertIsNone(sheet.cell(row=rows_meta["work_note_row"], column=march_1_col).value)

        self.assertIn(ARLS_METADATA_SHEET_NAME, workbook.sheetnames)
        meta_sheet = workbook[ARLS_METADATA_SHEET_NAME]
        self.assertEqual(meta_sheet["B1"].value, "SRS_KOR")
        self.assertEqual(meta_sheet["B2"].value, "R692")
        self.assertEqual(meta_sheet["B6"].value, "review-revision-1")

    def test_finance_review_workbook_builds_one_sheet_per_site_for_all(self) -> None:
        workbook, _template_path, _template_version = _build_monthly_export_workbook_from_contexts(
            export_contexts=[
                _build_site_context(
                    site_code="R738",
                    site_name="Apple_명동",
                    rows=[
                        {
                            "employee_id": "emp-1",
                            "employee_code": "R738-1",
                            "employee_name": "김민지",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-02",
                            "duty_type": "day",
                            "shift_type": "day",
                            "shift_start_time": "10:00:00",
                            "shift_end_time": "22:00:00",
                            "template_start_time": "10:00:00",
                            "template_end_time": "22:00:00",
                            "paid_hours": None,
                            "soc_role": "Supervisor",
                        }
                    ],
                    export_revision="review-revision-a",
                ),
                _build_site_context(
                    site_code="R739",
                    site_name="Apple_명동",
                    rows=[
                        {
                            "employee_id": "emp-2",
                            "employee_code": "R739-1",
                            "employee_name": "조태환",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-03",
                            "duty_type": "night",
                            "shift_type": "night",
                            "shift_start_time": "22:00:00",
                            "shift_end_time": "08:00:00",
                            "template_start_time": "22:00:00",
                            "template_end_time": "08:00:00",
                            "paid_hours": None,
                            "soc_role": "Officer",
                        }
                    ],
                    export_revision="review-revision-b",
                ),
            ],
            month_key="2026-03",
            tenant_code="SRS_KOR",
            source_version="finance-review-test:all-sites",
            include_summary_sections=False,
            include_support_assignment_sections=False,
        )

        visible_sheet_names = [
            name for name in workbook.sheetnames if workbook[name].sheet_state == "visible"
        ]
        self.assertEqual(visible_sheet_names, ["Apple_명동", "Apple_명동_2"])
        self.assertEqual(workbook["Apple_명동"]["B2"].value, "2026년 3월")
        self.assertEqual(workbook["Apple_명동_2"]["B2"].value, "2026년 3월")

        meta_sheet = workbook[ARLS_METADATA_SHEET_NAME]
        self.assertEqual(meta_sheet["B2"].value, "ALL")
        self.assertEqual(meta_sheet["B3"].value, "전체 지점")

    @patch("app.routers.v1.schedules._collect_monthly_export_context")
    def test_finance_review_export_uses_422_for_employee_mapping_error(self, collect_export_context) -> None:
        collect_export_context.return_value = {
            "rows": [{"employee_id": "emp-1"}],
            "support_rows": [],
            "employee_overnight_rows": [],
            "employee_blocks": [],
        }

        with self.assertRaises(HTTPException) as ctx:
            _collect_finance_review_export_context(
                None,
                target_tenant={"id": "tenant-1"},
                site_row={"id": "site-1", "site_code": "R692", "site_name": "Apple_가로수길"},
                month_key="2026-03",
                user={"role": "developer"},
            )

        self.assertEqual(ctx.exception.status_code, 422)
        self.assertEqual(str(ctx.exception.detail), "employee mapping unavailable for monthly export")

    def test_finance_review_workbook_populates_support_blocks_from_sentrix_status(self) -> None:
        workbook, _template_path, _template_version = _build_monthly_export_workbook_from_contexts(
            export_contexts=[
                _build_site_context(
                    site_code="R692",
                    site_name="Apple_가로수길",
                    rows=[
                        {
                            "employee_id": "emp-1",
                            "employee_code": "R692-1",
                            "employee_name": "민경민",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-05",
                            "duty_type": "day",
                            "shift_type": "day",
                            "shift_start_time": "08:00:00",
                            "shift_end_time": "18:00:00",
                            "template_start_time": "08:00:00",
                            "template_end_time": "18:00:00",
                            "paid_hours": None,
                            "soc_role": "Officer",
                        }
                    ],
                    export_revision="review-revision-support",
                )
            ],
            month_key="2026-03",
            tenant_code="SRS_KOR",
            source_version="finance-review-test:support",
            include_summary_sections=False,
            include_support_assignment_sections=False,
            support_status_rows_by_site_code={
                "R692": [
                    {
                        "site_code": "R692",
                        "work_date": date(2026, 3, 5),
                        "shift_kind": "day",
                        "request_count": 3,
                        "work_purpose": None,
                        "assignments": [
                            {"slot_index": 1, "worker_type": "BK", "display_value": "BK 서성원", "affiliation": "BK"},
                            {"slot_index": 2, "worker_type": "INTERNAL", "display_value": "자체 민경민", "affiliation": None},
                            {"slot_index": 3, "worker_type": "F", "display_value": "F 안현철", "affiliation": "F"},
                        ],
                    },
                    {
                        "site_code": "R692",
                        "work_date": date(2026, 3, 6),
                        "shift_kind": "night",
                        "request_count": 8,
                        "work_purpose": "매장 리뉴얼 대응",
                        "assignments": [
                            {"slot_index": 1, "worker_type": "BK", "display_value": "BK 서성원", "affiliation": "BK"},
                            {"slot_index": 2, "worker_type": "F", "display_value": "F 안현철", "affiliation": "F"},
                            {"slot_index": 3, "worker_type": "INTERNAL", "display_value": "자체 민경민", "affiliation": None},
                            {"slot_index": 4, "worker_type": "RK", "display_value": "RK 김민지", "affiliation": "RK"},
                            {"slot_index": 5, "worker_type": "KS", "display_value": "KS 조태환", "affiliation": "KS"},
                            {"slot_index": 6, "worker_type": "BK", "display_value": "BK 박준연", "affiliation": "BK"},
                            {"slot_index": 7, "worker_type": "INTERNAL", "display_value": "자체 김현진", "affiliation": None},
                        ],
                    },
                ]
            },
        )

        sheet = workbook["Apple_가로수길"]
        march_5_col = self._date_col(sheet, "2026-03-05")
        march_6_col = self._date_col(sheet, "2026-03-06")
        rows_meta = _locate_support_section_rows(sheet)

        self.assertEqual(len(rows_meta["night_rows"]), 7)
        self.assertGreater(rows_meta["night_vendor_count_row"], rows_meta["night_rows"][-1])

        self.assertEqual(sheet.cell(row=rows_meta["weekly_rows"][0], column=march_5_col).value, "BK 서성원")
        self.assertEqual(sheet.cell(row=rows_meta["weekly_rows"][1], column=march_5_col).value, "자체 민경민")
        self.assertEqual(sheet.cell(row=rows_meta["weekly_rows"][2], column=march_5_col).value, "F 안현철")
        self.assertEqual(sheet.cell(row=rows_meta["day_need_row"], column=march_5_col).value, "섭외 3인 요청")
        self.assertEqual(sheet.cell(row=rows_meta["day_vendor_count_row"], column=march_5_col).value, "BK 1인 투입\nF 1인 투입")

        self.assertEqual(sheet.cell(row=rows_meta["night_rows"][0], column=march_6_col).value, "BK 서성원")
        self.assertEqual(sheet.cell(row=rows_meta["night_rows"][6], column=march_6_col).value, "자체 김현진")
        self.assertEqual(sheet.cell(row=rows_meta["night_need_row"], column=march_6_col).value, "섭외 8인 요청")
        self.assertEqual(
            sheet.cell(row=rows_meta["night_vendor_count_row"], column=march_6_col).value,
            "BK 2인 투입\nF 1인 투입\nRK 1인 투입\nKS 1인 투입",
        )
        self.assertEqual(sheet.cell(row=rows_meta["work_note_row"], column=march_6_col).value, "매장 리뉴얼 대응")

    def test_finance_review_workbook_uses_site_specific_support_status_for_all(self) -> None:
        workbook, _template_path, _template_version = _build_monthly_export_workbook_from_contexts(
            export_contexts=[
                _build_site_context(
                    site_code="R738",
                    site_name="Apple_명동",
                    rows=[
                        {
                            "employee_id": "emp-1",
                            "employee_code": "R738-1",
                            "employee_name": "김민지",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-02",
                            "duty_type": "day",
                            "shift_type": "day",
                            "shift_start_time": "10:00:00",
                            "shift_end_time": "22:00:00",
                            "template_start_time": "10:00:00",
                            "template_end_time": "22:00:00",
                            "paid_hours": None,
                            "soc_role": "Supervisor",
                        }
                    ],
                    export_revision="review-revision-site-a",
                ),
                _build_site_context(
                    site_code="R739",
                    site_name="Apple_가로수길",
                    rows=[
                        {
                            "employee_id": "emp-2",
                            "employee_code": "R739-1",
                            "employee_name": "조태환",
                            "sequence_no": 1,
                            "schedule_date": "2026-03-02",
                            "duty_type": "day",
                            "shift_type": "day",
                            "shift_start_time": "08:00:00",
                            "shift_end_time": "18:00:00",
                            "template_start_time": "08:00:00",
                            "template_end_time": "18:00:00",
                            "paid_hours": None,
                            "soc_role": "Officer",
                        }
                    ],
                    export_revision="review-revision-site-b",
                ),
            ],
            month_key="2026-03",
            tenant_code="SRS_KOR",
            source_version="finance-review-test:site-support",
            include_summary_sections=False,
            include_support_assignment_sections=False,
            support_status_rows_by_site_code={
                "R738": [
                    {
                        "site_code": "R738",
                        "work_date": date(2026, 3, 2),
                        "shift_kind": "day",
                        "request_count": 1,
                        "assignments": [
                            {"slot_index": 1, "worker_type": "BK", "display_value": "BK 명동지원", "affiliation": "BK"},
                        ],
                    }
                ],
                "R739": [
                    {
                        "site_code": "R739",
                        "work_date": date(2026, 3, 2),
                        "shift_kind": "day",
                        "request_count": 1,
                        "assignments": [
                            {"slot_index": 1, "worker_type": "F", "display_value": "F 가로수지원", "affiliation": "F"},
                        ],
                    }
                ],
            },
        )

        march_2_col = self._date_col(workbook["Apple_명동"], "2026-03-02")
        rows_meta_myeongdong = _locate_support_section_rows(workbook["Apple_명동"])
        rows_meta_garosu = _locate_support_section_rows(workbook["Apple_가로수길"])

        self.assertEqual(
            workbook["Apple_명동"].cell(row=rows_meta_myeongdong["weekly_rows"][0], column=march_2_col).value,
            "BK 명동지원",
        )
        self.assertEqual(
            workbook["Apple_가로수길"].cell(row=rows_meta_garosu["weekly_rows"][0], column=march_2_col).value,
            "F 가로수지원",
        )


if __name__ == "__main__":
    unittest.main()
