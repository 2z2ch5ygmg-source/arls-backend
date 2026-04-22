import unittest

from app.routers.v1.schedules import _build_finance_download_workspace_site_payload


class FinanceDownloadWorkspacePayloadTests(unittest.TestCase):
    def test_reuploaded_final_uses_short_status_and_note(self):
        row = _build_finance_download_workspace_site_payload(
            None,
            target_tenant={"id": "tenant-1"},
            site_row={
                "id": "site-1",
                "site_code": "R692",
                "site_name": "Apple_가로수길",
            },
            month_key="2026-04",
            active_state={
                "active_final_batch_id": "batch-1",
                "final_uploaded_at": "2026-04-19T05:30:00Z",
                "final_uploaded_by_username": "Supervisor",
                "active_final_filename": "final.xlsx",
                "final_upload_count": 2,
                "final_download_enabled": True,
                "final_upload_stale": False,
                "conflict_required": False,
            },
            state_preloaded=True,
        )

        self.assertEqual(row.status, "reuploaded")
        self.assertEqual(row.status_label, "재업로드됨")
        self.assertEqual(row.note, "Report 업데이트로 재 다운로드 필요")
        self.assertTrue(row.download_enabled)

    def test_stale_final_uses_user_friendly_note(self):
        row = _build_finance_download_workspace_site_payload(
            None,
            target_tenant={"id": "tenant-1"},
            site_row={
                "id": "site-1",
                "site_code": "R692",
                "site_name": "Apple_가로수길",
            },
            month_key="2026-04",
            active_state={
                "active_final_batch_id": "batch-1",
                "final_uploaded_at": "2026-04-19T05:30:00Z",
                "final_uploaded_by_username": "Supervisor",
                "active_final_filename": "final.xlsx",
                "final_upload_count": 1,
                "final_download_enabled": False,
                "final_upload_stale": True,
                "conflict_required": False,
            },
            state_preloaded=True,
        )

        self.assertEqual(row.status, "stale")
        self.assertEqual(row.status_label, "재업로드 필요")
        self.assertEqual(row.note, "근무표가 변경되어 업로드한 보고서가 최신 상태가 아닙니다.")
        self.assertTrue(row.download_enabled)
        self.assertIsNone(row.download_blocked_reason)


if __name__ == "__main__":
    unittest.main()
