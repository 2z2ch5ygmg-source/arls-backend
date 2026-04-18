from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import unittest
from unittest.mock import patch

from app.routers.v1.schedules import (
    _build_finance_submission_overview_payload,
    _build_finance_final_filename,
    _build_finance_review_filename,
    _can_read_schedule_import_mapping_profile,
    _can_download_finance_final,
    _can_download_finance_review,
    _can_upload_finance_final,
    _can_view_finance_download_workspace,
    _can_view_finance_submission,
    _finance_preview_row_has_real_protected_change,
    _is_supported_import_source_version,
    apply_finance_final_upload,
    download_finance_final_excel,
    get_finance_submission_status,
)
from app.schemas import ImportApplyOut


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
        self.assertTrue(_can_download_finance_review(supervisor))
        self.assertFalse(_can_download_finance_review(vice))

        self.assertTrue(_can_upload_finance_final(supervisor))
        self.assertTrue(_can_upload_finance_final(developer))
        self.assertTrue(_can_upload_finance_final(hq))
        self.assertFalse(_can_upload_finance_final(vice))

        self.assertTrue(_can_view_finance_download_workspace(hq))
        self.assertTrue(_can_view_finance_download_workspace(developer))
        self.assertFalse(_can_view_finance_download_workspace(supervisor))
        self.assertFalse(_can_view_finance_download_workspace(vice))

        self.assertTrue(_can_download_finance_final(hq))
        self.assertTrue(_can_download_finance_final(developer))
        self.assertFalse(_can_download_finance_final(supervisor))
        self.assertFalse(_can_download_finance_final(vice))

    def test_schedule_import_mapping_profile_is_readable_for_upload_roles_only(self):
        self.assertTrue(_can_read_schedule_import_mapping_profile({"role": "Developer"}))
        self.assertTrue(_can_read_schedule_import_mapping_profile({"role": "HQ_Admin"}))
        self.assertTrue(_can_read_schedule_import_mapping_profile({"role": "Supervisor"}))
        self.assertTrue(_can_read_schedule_import_mapping_profile({"role": "Vice_Supervisor"}))
        self.assertFalse(_can_read_schedule_import_mapping_profile({"role": "Officer"}))

    def test_finance_review_workbook_source_version_is_supported_for_final_upload(self):
        self.assertTrue(_is_supported_import_source_version("schedule_export.phase2.roundtrip"))
        self.assertTrue(_is_supported_import_source_version("schedule_export.phase2.roundtrip:finance-review"))
        self.assertTrue(_is_supported_import_source_version("schedule_export.phase2.roundtrip:finance-review:all-sites"))

    def test_finance_protected_change_helper_ignores_unchanged_protected_rows(self):
        self.assertFalse(_finance_preview_row_has_real_protected_change({
            "diff_category": "ignored_protected",
            "work_value": "0",
            "current_work_value": "0",
        }))
        self.assertTrue(_finance_preview_row_has_real_protected_change({
            "diff_category": "ignored_protected",
            "work_value": "1",
            "current_work_value": "0",
        }))

    def test_final_download_streams_stored_uploaded_artifact(self):
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}
        site_row = {"id": "site-1", "site_code": "R692"}
        submission_row = {"active_final_batch_id": "batch-1"}
        stored_bytes = b"finance-final-artifact"
        finance_batch = {
            "id": "batch-1",
            "filename": "finance-final-original.xlsx",
            "artifact_bytes": stored_bytes,
        }
        status_payload = type("StatusPayload", (), {"final_download_enabled": True})()

        with patch("app.routers.v1.schedules._resolve_target_tenant", return_value=target_tenant), \
             patch("app.routers.v1.schedules._resolve_site_context_by_code", return_value=site_row), \
             patch("app.routers.v1.schedules._build_finance_submission_status_payload", return_value=status_payload), \
             patch("app.routers.v1.schedules._get_finance_submission_state", return_value=submission_row), \
             patch("app.routers.v1.schedules._get_finance_submission_batch", return_value=finance_batch):
            response = download_finance_final_excel(
                month="2026-03",
                site_code="R692",
                tenant_code="SRS_KOREA",
                conn=object(),
                user={"role": "HQ_Admin"},
            )

        streamed = asyncio.run(self._read_streaming_response(response))
        self.assertEqual(streamed, stored_bytes)
        self.assertIn("finance-final-original.xlsx", response.headers.get("Content-Disposition", ""))

    async def _read_streaming_response(self, response) -> bytes:
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return b"".join(chunks)

    def test_apply_finance_final_upload_links_active_uploaded_batch_for_download(self):
        finance_batch_id = uuid.uuid4()
        import_batch_id = uuid.uuid4()
        fake_conn = _FakeConn()
        finance_batch = {
            "id": str(finance_batch_id),
            "site_code": "R692",
            "month_key": "2026-03",
            "source_revision": "rev-current",
            "filename": "finance-final-original.xlsx",
            "import_batch_id": str(import_batch_id),
        }
        result = ImportApplyOut(
            batch_id=import_batch_id,
            applied=3,
            skipped=0,
            applied_rows=[],
            skipped_rows=[],
            blocked=False,
            blocked_reasons=[],
        )

        with patch("app.routers.v1.schedules._resolve_target_tenant", return_value={"id": "tenant-1", "tenant_code": "SRS_KOREA"}), \
             patch("app.routers.v1.schedules._get_finance_submission_batch", return_value=finance_batch), \
             patch("app.routers.v1.schedules._resolve_site_context_by_code", return_value={"id": "site-1", "site_code": "R692"}), \
             patch("app.routers.v1.schedules._ensure_finance_submission_state", return_value={"id": "state-1"}), \
             patch("app.routers.v1.schedules._sync_finance_submission_state") as sync_state, \
             patch("app.routers.v1.schedules.apply_import", return_value=result), \
             patch("app.routers.v1.schedules._build_schedule_export_revision", return_value="rev-final"):
            response = apply_finance_final_upload(
                finance_batch_id=finance_batch_id,
                tenant_code="SRS_KOREA",
                conn=fake_conn,
                user={"id": "user-1", "role": "Supervisor", "site_id": "site-1", "site_code": "R692"},
            )

        sync_state.assert_not_called()
        self.assertEqual(response.applied, 3)
        state_update = next(
            params
            for sql, params in fake_conn.calls
            if "UPDATE schedule_finance_submission_states" in sql
        )
        self.assertEqual(state_update[0], "rev-final")
        self.assertEqual(str(state_update[1]), str(finance_batch_id))
        self.assertEqual(state_update[2], "rev-final")
        self.assertEqual(state_update[3], "rev-current")
        self.assertEqual(state_update[4], "finance-final-original.xlsx")

    def test_overview_payload_limits_field_scope_to_own_site(self):
        target_tenant = {
            "id": "tenant-1",
            "tenant_code": "SRS_KOREA",
            "tenant_name": "SRS Korea",
        }
        scoped_site_row = {"id": "site-1", "site_code": "R692", "site_name": "Apple 가로수길"}
        scoped_state = {
            "site_id": "site-1",
            "review_download_revision": "rev-123",
            "updated_at": datetime(2026, 3, 27, 1, 0, tzinfo=timezone.utc),
        }
        user = {"role": "Supervisor", "site_code": "R692"}

        with patch("app.routers.v1.schedules._resolve_scoped_schedule_site_code", return_value="R692"), \
             patch("app.routers.v1.schedules._resolve_site_context_by_code", return_value=scoped_site_row), \
             patch("app.routers.v1.schedules._list_finance_submission_states_for_workspace", return_value={"site-1": scoped_state}), \
             patch("app.routers.v1.schedules._list_finance_download_workspace_sites") as list_sites:
            payload = _build_finance_submission_overview_payload(
                conn=object(),
                target_tenant=target_tenant,
                user=user,
                month_key="2026-03",
            )

        list_sites.assert_not_called()
        self.assertFalse(payload.tenant_wide)
        self.assertEqual(payload.scope_label, "본인 지점")
        self.assertEqual(payload.total_site_count, 1)
        self.assertEqual(payload.sites[0].site_code, "R692")
        self.assertEqual(payload.sites[0].review_status_label, "다운로드 완료")

    def test_status_endpoint_uses_scoped_site_code_for_field_user(self):
        fake_conn = object()
        target_tenant = {"id": "tenant-1", "tenant_code": "SRS_KOREA"}
        status_payload = type("StatusPayload", (), {"site_code": "R692"})()

        with patch("app.routers.v1.schedules._resolve_target_tenant", return_value=target_tenant), \
             patch("app.routers.v1.schedules._resolve_scoped_schedule_site_code", return_value="R692"), \
             patch("app.routers.v1.schedules._resolve_site_context_by_code", return_value={"id": "site-1", "site_code": "R692"}) as resolve_site, \
             patch("app.routers.v1.schedules._build_finance_submission_status_payload", return_value=status_payload):
            response = get_finance_submission_status(
                month="2026-03",
                site_code="R738",
                tenant_code="SRS_KOREA",
                conn=fake_conn,
                user={"role": "Supervisor", "site_code": "R692"},
            )

        resolve_site.assert_called_once_with(
            fake_conn,
            tenant_id="tenant-1",
            site_code="R692",
        )
        self.assertEqual(response.site_code, "R692")


class _FakeCursor:
    def __init__(self, calls: list[tuple[str, tuple | None]]):
        self._calls = calls

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self._calls.append((sql, params))


class _FakeConn:
    def __init__(self):
        self.calls: list[tuple[str, tuple | None]] = []

    def cursor(self):
        return _FakeCursor(self.calls)


if __name__ == "__main__":
    unittest.main()
