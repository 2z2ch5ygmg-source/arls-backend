from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from app.routers.v1.schedules import (
    _build_finance_final_filename,
    _build_finance_review_filename,
    _can_download_finance_final,
    _can_download_finance_review,
    _can_upload_finance_final,
    _can_view_finance_submission,
)


class ScheduleFinanceSubmissionHelpersTests(unittest.TestCase):
    def test_finance_filename_builders_follow_expected_pattern(self):
        fixed = datetime(2026, 3, 9, 15, 40, tzinfo=timezone(timedelta(hours=9)))
        self.assertEqual(
            _build_finance_review_filename(month_key="2026-03", site_code="R692", generated_at=fixed),
            "2026년 3월 근무표_R692_1차확인본_260309.xlsx",
        )
        self.assertEqual(
            _build_finance_final_filename(month_key="2026-03", site_code="R692", generated_at=fixed),
            "2026년 3월 근무표_R692_2차최종_260309.xlsx",
        )

    def test_finance_role_permissions_match_business_rules(self):
        supervisor = {"role": "Supervisor"}
        hq = {"role": "HQ_Admin"}
        vice = {"role": "Vice_Supervisor"}
        developer = {"role": "Developer"}

        self.assertTrue(_can_view_finance_submission(supervisor))
        self.assertTrue(_can_view_finance_submission(hq))
        self.assertTrue(_can_view_finance_submission(vice))
        self.assertTrue(_can_view_finance_submission(developer))

        self.assertTrue(_can_download_finance_review(hq))
        self.assertTrue(_can_download_finance_review(developer))
        self.assertFalse(_can_download_finance_review(supervisor))

        self.assertTrue(_can_upload_finance_final(supervisor))
        self.assertTrue(_can_upload_finance_final(developer))
        self.assertFalse(_can_upload_finance_final(hq))
        self.assertFalse(_can_upload_finance_final(vice))

        self.assertTrue(_can_download_finance_final(hq))
        self.assertTrue(_can_download_finance_final(developer))
        self.assertFalse(_can_download_finance_final(supervisor))


if __name__ == "__main__":
    unittest.main()
