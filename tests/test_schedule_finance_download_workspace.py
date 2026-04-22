from __future__ import annotations

from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.routers.v1.schedules import (
    _build_finance_download_workspace_payload,
    _build_finance_download_workspace_site_payload,
)
from app.schemas import FinanceDownloadWorkspaceSiteOut


class FinanceDownloadWorkspaceTests(unittest.TestCase):
    def test_site_payload_marks_missing_upload_as_not_uploaded(self):
        site_row = {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"}
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}

        with patch("app.routers.v1.schedules._get_finance_submission_state", return_value=None):
            payload = _build_finance_download_workspace_site_payload(
                conn=object(),
                target_tenant=target_tenant,
                site_row=site_row,
                month_key="2026-03",
            )

        self.assertEqual(payload.site_code, "R692")
        self.assertEqual(payload.status, "not_uploaded")
        self.assertEqual(payload.status_label, "미업로드")
        self.assertFalse(payload.uploaded)
        self.assertFalse(payload.download_enabled)
        self.assertEqual(payload.download_blocked_reason, "업로드된 파일 없음")

    def test_site_payload_keeps_uploaded_artifact_metadata(self):
        site_row = {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"}
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}
        existing_state = {
            "id": "state-1",
            "tenant_id": "tenant-1",
            "site_id": "site-1",
            "month_key": "2026-03",
        }
        refreshed_state = {
            **existing_state,
            "active_final_batch_id": "batch-1",
            "active_final_filename": "finance-final.xlsx",
            "final_uploaded_at": datetime(2026, 3, 27, 1, 30, tzinfo=timezone.utc),
            "final_uploaded_by_username": "hq_admin",
            "final_download_enabled": True,
            "final_upload_stale": False,
            "conflict_required": False,
            "_derived_blocked_reasons": [],
        }

        with patch("app.routers.v1.schedules._get_finance_submission_state", return_value=existing_state), \
             patch("app.routers.v1.schedules._build_schedule_export_revision", return_value="rev-123"), \
             patch("app.routers.v1.schedules._refresh_finance_submission_state_row", return_value=refreshed_state):
            payload = _build_finance_download_workspace_site_payload(
                conn=object(),
                target_tenant=target_tenant,
                site_row=site_row,
                month_key="2026-03",
            )

        self.assertEqual(payload.status, "uploaded")
        self.assertEqual(payload.status_label, "업로드 완료")
        self.assertTrue(payload.uploaded)
        self.assertTrue(payload.download_enabled)
        self.assertEqual(payload.final_uploaded_by, "hq_admin")
        self.assertEqual(payload.active_final_filename, "finance-final.xlsx")
        self.assertIsNone(payload.download_blocked_reason)

    def test_site_payload_keeps_stale_uploaded_file_downloadable(self):
        site_row = {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"}
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}
        refreshed_state = {
            "id": "state-1",
            "tenant_id": "tenant-1",
            "site_id": "site-1",
            "month_key": "2026-03",
            "active_final_batch_id": "batch-1",
            "active_final_filename": "finance-final.xlsx",
            "final_uploaded_at": datetime(2026, 3, 27, 1, 30, tzinfo=timezone.utc),
            "final_uploaded_by_username": "hq_admin",
            "final_download_enabled": False,
            "final_upload_stale": True,
            "conflict_required": False,
            "_derived_blocked_reasons": [],
        }

        payload = _build_finance_download_workspace_site_payload(
            conn=object(),
            target_tenant=target_tenant,
            site_row=site_row,
            month_key="2026-03",
            active_state=refreshed_state,
            state_preloaded=True,
        )

        self.assertEqual(payload.status, "stale")
        self.assertTrue(payload.uploaded)
        self.assertTrue(payload.download_enabled)
        self.assertIsNone(payload.download_blocked_reason)

    def test_workspace_payload_summarizes_uploaded_and_downloadable_counts(self):
        target_tenant = {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        }
        site_rows = [
            {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"},
            {"id": "site-2", "site_code": "R738", "site_name": "Apple 가로수길"},
        ]
        payload_rows = [
            FinanceDownloadWorkspaceSiteOut(
                site_code="R692",
                site_name="Apple 명동",
                uploaded=True,
                status="uploaded",
                status_label="업로드 완료",
                download_enabled=True,
            ),
            FinanceDownloadWorkspaceSiteOut(
                site_code="R738",
                site_name="Apple 가로수길",
                uploaded=False,
                status="not_uploaded",
                status_label="미업로드",
                download_enabled=False,
                download_blocked_reason="업로드된 파일 없음",
            ),
        ]

        with patch("app.routers.v1.schedules._list_finance_download_workspace_sites", return_value=site_rows), \
             patch("app.routers.v1.schedules._list_finance_submission_states_for_workspace", return_value={}), \
             patch("app.routers.v1.schedules._list_finance_submission_batch_filenames", return_value={}), \
             patch("app.routers.v1.schedules._build_finance_download_workspace_site_payload", side_effect=payload_rows):
            payload = _build_finance_download_workspace_payload(
                conn=object(),
                target_tenant=target_tenant,
                user={"role": "HQ_Admin"},
                month_key="2026-03",
            )

        self.assertEqual(payload.tenant_code, "SRS_KOREA")
        self.assertEqual(payload.total_site_count, 2)
        self.assertEqual(payload.uploaded_site_count, 1)
        self.assertEqual(payload.downloadable_site_count, 1)
        self.assertEqual([row.site_code for row in payload.sites], ["R692", "R738"])

    def test_workspace_payload_does_not_refetch_missing_preloaded_states(self):
        target_tenant = {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        }
        site_rows = [
            {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"},
            {"id": "site-2", "site_code": "R738", "site_name": "Apple 가로수길"},
        ]

        with patch("app.routers.v1.schedules._list_finance_download_workspace_sites", return_value=site_rows), \
             patch("app.routers.v1.schedules._list_finance_submission_states_for_workspace", return_value={}), \
             patch("app.routers.v1.schedules._list_finance_submission_batch_filenames", return_value={}), \
             patch("app.routers.v1.schedules._get_finance_submission_state") as get_state:
            payload = _build_finance_download_workspace_payload(
                conn=object(),
                target_tenant=target_tenant,
                user={"role": "HQ_Admin"},
                month_key="2026-03",
            )

        get_state.assert_not_called()
        self.assertEqual(payload.total_site_count, 2)
        self.assertEqual(payload.uploaded_site_count, 0)
        self.assertEqual([row.status for row in payload.sites], ["not_uploaded", "not_uploaded"])

    def test_site_payload_uses_preloaded_state_without_revision_refresh(self):
        site_row = {"id": "site-1", "site_code": "R692", "site_name": "Apple 명동"}
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}
        preloaded_state = {
            "id": "state-1",
            "tenant_id": "tenant-1",
            "site_id": "site-1",
            "month_key": "2026-03",
            "active_final_batch_id": "batch-1",
            "final_uploaded_at": datetime(2026, 3, 27, 1, 30, tzinfo=timezone.utc),
            "final_uploaded_by_username": "hq_admin",
            "final_download_enabled": True,
            "final_upload_stale": False,
            "conflict_required": False,
        }

        with patch("app.routers.v1.schedules._get_finance_submission_state") as get_state, \
             patch("app.routers.v1.schedules._build_schedule_export_revision") as build_revision, \
             patch("app.routers.v1.schedules._refresh_finance_submission_state_row") as refresh_state:
            payload = _build_finance_download_workspace_site_payload(
                conn=object(),
                target_tenant=target_tenant,
                site_row=site_row,
                month_key="2026-03",
                active_state=preloaded_state,
                active_batch_filename="finance-final.xlsx",
            )

        get_state.assert_not_called()
        build_revision.assert_not_called()
        refresh_state.assert_not_called()
        self.assertTrue(payload.uploaded)
        self.assertTrue(payload.download_enabled)
        self.assertEqual(payload.active_final_filename, "finance-final.xlsx")


if __name__ == "__main__":
    unittest.main()
