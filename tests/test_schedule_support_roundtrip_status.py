from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.routers.v1.schedules import _build_support_roundtrip_status_payload


class _FakeCursor:
    def __init__(self, responses):
        self._responses = list(responses)

    def execute(self, _query, _params=None):
        return None

    def fetchone(self):
        if not self._responses:
            return None
        return self._responses.pop(0)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, cursor_responses):
        self._cursor_responses = list(cursor_responses)

    def cursor(self):
        responses = self._cursor_responses.pop(0) if self._cursor_responses else []
        return _FakeCursor(responses)


class SupportRoundtripStatusPayloadTests(unittest.TestCase):
    def test_status_payload_exposes_sentrix_artifact_metadata(self):
        conn = _FakeConn([
            [{"cnt": 7}, {"cnt": 1}],
        ])
        uploaded_at = datetime(2026, 3, 11, 1, 23, tzinfo=timezone.utc)
        status = _build_support_roundtrip_status_payload(
            conn,
            source_row={
                "id": "src-1",
                "state": "waiting_for_hq_merge",
                "source_revision": "rev-1234567890",
                "source_uploaded_at": uploaded_at,
                "source_uploaded_by_username": "master",
                "source_filename": "support_source.xlsx",
                "hq_merge_available": False,
                "hq_merge_stale": True,
            },
            tenant_code="srs_kor",
            tenant_id="tenant-1",
            site_id="site-1",
            site_code="R692",
            month_key="2026-03",
        )

        self.assertEqual(status.artifact_revision, "rev-1234567890")
        self.assertEqual(status.artifact_generated_at, uploaded_at)
        self.assertEqual(
            status.artifact_id,
            "sentrix-hq:SRS_KOR:2026-03:R692:rev-1234567890",
        )
        self.assertEqual(status.support_assignment_count, 7)
        self.assertEqual(status.conflict_count, 1)
        self.assertEqual(
            status.blocked_reasons,
            ["현재 Sentrix 제출 기준이 최신 Supervisor source보다 오래되었습니다. 최신 artifact를 다시 Sentrix로 넘겨 주세요."],
        )

    def test_missing_sentrix_submission_is_not_reported_as_apply_blocker(self):
        conn = _FakeConn([
            [{"cnt": 0}, {"cnt": 0}],
        ])
        status = _build_support_roundtrip_status_payload(
            conn,
            source_row={
                "id": "src-2",
                "state": "waiting_for_hq_merge",
                "source_revision": "rev-002",
                "source_uploaded_at": datetime(2026, 3, 11, 2, 0, tzinfo=timezone.utc),
                "hq_merge_available": False,
                "hq_merge_stale": False,
            },
            tenant_code="srs_kor",
            tenant_id="tenant-1",
            site_id="site-2",
            site_code="R001",
            month_key="2026-03",
        )

        self.assertEqual(status.blocked_reasons, [])
        self.assertEqual(status.artifact_id, "sentrix-hq:SRS_KOR:2026-03:R001:rev-002")


if __name__ == "__main__":
    unittest.main()
