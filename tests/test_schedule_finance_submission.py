from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from app.routers.v1.schedules import (
    ARLS_FINANCE_REVIEW_SOURCE_VERSION,
    _build_finance_final_filename,
    _build_finance_review_filename,
    _can_download_finance_final,
    _can_download_finance_review,
    _can_upload_finance_final,
    _can_view_finance_submission,
    _is_supported_import_source_version,
    _resolve_finance_submission_site_status,
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
        self.assertTrue(_can_view_finance_submission(developer))
        self.assertTrue(_can_view_finance_submission(vice))

        self.assertTrue(_can_download_finance_review(supervisor))
        self.assertTrue(_can_download_finance_review(hq))
        self.assertTrue(_can_download_finance_review(developer))
        self.assertTrue(_can_download_finance_review(vice))

        self.assertTrue(_can_upload_finance_final(supervisor))
        self.assertTrue(_can_upload_finance_final(hq))
        self.assertTrue(_can_upload_finance_final(developer))
        self.assertTrue(_can_upload_finance_final(vice))

        self.assertTrue(_can_download_finance_final(hq))
        self.assertTrue(_can_download_finance_final(developer))
        self.assertFalse(_can_download_finance_final(supervisor))
        self.assertFalse(_can_download_finance_final(vice))

    def test_finance_review_export_source_version_is_upload_compatible(self):
        self.assertTrue(_is_supported_import_source_version(ARLS_FINANCE_REVIEW_SOURCE_VERSION))

    def test_finance_hq_site_status_rules_follow_publish_and_acknowledgement(self):
        self.assertEqual(
            _resolve_finance_submission_site_status(
                has_published_file=False,
                current_publish_marker=None,
                last_seen_publish_marker=None,
            ),
            ("파일 없음", False, "게시된 Finance workbook이 없습니다."),
        )
        self.assertEqual(
            _resolve_finance_submission_site_status(
                has_published_file=True,
                current_publish_marker="batch-new",
                last_seen_publish_marker="batch-old",
            ),
            ("업데이트 필요", True, "이전에 확인한 게시본 이후 새 게시본이 있습니다."),
        )
        self.assertEqual(
            _resolve_finance_submission_site_status(
                has_published_file=True,
                current_publish_marker="batch-current",
                last_seen_publish_marker="batch-current",
            ),
            ("게시 완료", True, "최신 게시본을 내려받을 수 있습니다."),
        )


if __name__ == "__main__":
    unittest.main()
