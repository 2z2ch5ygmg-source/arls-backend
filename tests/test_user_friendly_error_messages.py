import unittest

from app.main import _api_error_payload
from app.routers.v1.schedules import _sentrix_hq_issue_template


class UserFriendlyErrorMessageTests(unittest.TestCase):
    def test_api_error_payload_maps_invalid_import_header_to_plain_korean(self):
        payload = _api_error_payload(400, "invalid import header")
        self.assertEqual(
            payload["error"]["message"],
            "업로드한 파일 형식이 현재 양식과 다릅니다. 최신 양식을 다시 다운로드해 주세요.",
        )

    def test_api_error_payload_maps_support_roundtrip_source_missing_to_plain_korean(self):
        payload = _api_error_payload(409, "support roundtrip source missing")
        self.assertEqual(
            payload["error"]["message"],
            "먼저 지점 스케줄 원본 업로드를 완료해 주세요.",
        )

    def test_sentrix_hq_issue_template_uses_plain_outdated_workbook_message(self):
        severity, title, message, guidance = _sentrix_hq_issue_template("OUTDATED_WORKBOOK")
        self.assertEqual(severity, "blocking")
        self.assertEqual(title, "예전에 받은 파일입니다")
        self.assertEqual(message, "이 파일을 받은 뒤 ARLS 스케줄이 바뀌었습니다.")
        self.assertEqual(guidance, "최신 HQ 제출용 파일을 다시 다운로드해 주세요.")


if __name__ == "__main__":
    unittest.main()
