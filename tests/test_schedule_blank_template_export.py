from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from openpyxl import load_workbook

from app.routers.v1.schedules import (
    ARLS_SHEET_NAME,
    _extract_arls_date_columns,
    _load_required_arls_month_workbook,
    _prepare_blank_arls_template_sheet,
    _prepare_blank_arls_template_workbook,
)


class BlankTemplateExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workbook, self.template_path = _load_required_arls_month_workbook()

    @patch("app.routers.v1.schedules._fetch_kr_public_holiday_map")
    def test_blank_template_populates_month_site_address_and_holiday_rows(self, mock_holidays) -> None:
        mock_holidays.return_value = {"2026-03-01": "3·1절"}

        _prepare_blank_arls_template_workbook(
            self.workbook,
            month_key="2026-03",
            site_name="Apple_가로수길",
            site_address="서울 강남구 도산대로 1",
        )

        sheet = self.workbook[ARLS_SHEET_NAME]
        self.assertEqual(sheet["B1"].value, "2026년 3월")
        self.assertEqual(sheet["B2"].value, "현장명  Apple_가로수길")
        self.assertEqual(sheet["B3"].value, "현장주소\n서울 강남구 도산대로 1")
        self.assertEqual(sheet["D2"].value, date(2026, 3, 1))
        self.assertEqual(sheet["D3"].value, "일")
        self.assertEqual(sheet["D4"].value, "3·1절")
        self.assertEqual(sheet["AH2"].value, date(2026, 3, 31))

    @patch("app.routers.v1.schedules._fetch_kr_public_holiday_map")
    def test_blank_template_clears_unused_day_columns_for_short_month(self, mock_holidays) -> None:
        mock_holidays.return_value = {}

        _prepare_blank_arls_template_workbook(
            self.workbook,
            month_key="2026-02",
            site_name="Apple_명동",
            site_address="서울 중구 명동길 1",
        )

        sheet = self.workbook[ARLS_SHEET_NAME]
        self.assertEqual(sheet["AE2"].value, date(2026, 2, 28))
        self.assertEqual(sheet["AE3"].value, "토")
        self.assertIsNone(sheet["AF2"].value)
        self.assertIsNone(sheet["AF3"].value)
        self.assertIsNone(sheet["AF4"].value)
        self.assertIsNone(sheet["AH2"].value)

    @patch("app.routers.v1.schedules._fetch_kr_public_holiday_map")
    def test_generated_blank_template_headers_are_parseable_by_import_reader(self, mock_holidays) -> None:
        mock_holidays.return_value = {"2026-03-01": "3·1절"}

        _prepare_blank_arls_template_workbook(
            self.workbook,
            month_key="2026-03",
            site_name="Apple_가로수길",
            site_address="서울 강남구 도산대로 1",
        )

        sheet = self.workbook[ARLS_SHEET_NAME]
        date_map, month_ctx = _extract_arls_date_columns(sheet)
        self.assertEqual(month_ctx, (2026, 3))
        self.assertEqual(date_map[4], date(2026, 3, 1))
        self.assertEqual(date_map[34], date(2026, 3, 31))

    @patch("app.routers.v1.schedules._fetch_kr_public_holiday_map")
    def test_blank_template_repairs_hidden_sheet_ref_dependency(self, mock_holidays) -> None:
        mock_holidays.return_value = {}

        _prepare_blank_arls_template_workbook(
            self.workbook,
            month_key="2026-03",
            site_name="Apple_가로수길",
            site_address="서울 강남구 도산대로 1",
        )

        hidden_sheet = self.workbook["출동.잔업 초과수당(2)"]
        self.assertEqual(hidden_sheet["B3"].value, date(2026, 3, 1))
        self.assertNotIn("#REF!", str(hidden_sheet["B3"].value))

    @patch("app.routers.v1.schedules._fetch_kr_public_holiday_map")
    def test_blank_template_can_prepare_multiple_site_sheets(self, mock_holidays) -> None:
        mock_holidays.return_value = {"2026-03-01": "3·1절"}

        template_sheet = self.workbook[ARLS_SHEET_NAME]
        second_sheet = self.workbook.copy_worksheet(template_sheet)
        template_sheet.title = "Apple_명동"
        second_sheet.title = "Apple_가로수길"

        _prepare_blank_arls_template_sheet(
            self.workbook,
            sheet=template_sheet,
            month_key="2026-03",
            site_name="Apple_명동",
            site_address="서울 중구 명동길 1",
        )
        _prepare_blank_arls_template_sheet(
            self.workbook,
            sheet=second_sheet,
            month_key="2026-03",
            site_name="Apple_가로수길",
            site_address="서울 강남구 도산대로 1",
        )

        self.assertEqual(template_sheet["B2"].value, "현장명  Apple_명동")
        self.assertEqual(second_sheet["B2"].value, "현장명  Apple_가로수길")
        self.assertEqual(template_sheet["D4"].value, "3·1절")
        self.assertEqual(second_sheet["D4"].value, "3·1절")


if __name__ == "__main__":
    unittest.main()
