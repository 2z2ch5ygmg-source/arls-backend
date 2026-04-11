from __future__ import annotations

from datetime import datetime, timezone

from app.routers.v1 import hr_documents


class _FakeCursor:
    def __init__(self, conn) -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))

    def fetchone(self):
        if self.conn.fetchone_queue:
            return self.conn.fetchone_queue.pop(0)
        return None

    def fetchall(self):
        if self.conn.fetchall_queue:
            return self.conn.fetchall_queue.pop(0)
        return []


class _FakeConn:
    def __init__(self, *, fetchone_queue=None, fetchall_queue=None) -> None:
        self.fetchone_queue = list(fetchone_queue or [])
        self.fetchall_queue = list(fetchall_queue or [])
        self.executed: list[tuple[str, object]] = []

    def cursor(self):
        return _FakeCursor(self)


def _admin_user() -> dict:
    return {
        "id": "user-1",
        "tenant_id": "tenant-1",
        "tenant_code": "SRS_KOREA",
        "role": "hq_admin",
    }


def test_list_admin_resignation_requests_returns_items():
    conn = _FakeConn(
        fetchall_queue=[[
            {
                "id": "req-1",
                "status": "requested",
                "purpose_code": "PERSONAL",
                "purpose_text": '{"expected_last_working_date":"2026-04-30","resignation_reason":"개인 사정","handover_notes":"인수인계 예정"}',
                "requested_at": datetime(2026, 4, 7, tzinfo=timezone.utc),
                "approved_at": None,
                "rejection_reason": None,
                "employee_code": "R692-1",
                "employee_name": "서성원",
                "company_name": "SRS Korea",
                "org_name": "Apple_가로수길",
            }
        ]]
    )

    result = hr_documents.list_admin_resignation_requests(
        status_filter="requested",
        q="R692-1",
        limit=20,
        page=1,
        pageSize=None,
        x_tenant_id=None,
        conn=conn,
        user=_admin_user(),
    )

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["resignation_type"] == "PERSONAL"
    assert item["expected_last_working_date"] == "2026-04-30"
    assert item["resignation_reason"] == "개인 사정"


def test_serialize_resignation_request_row_parses_json_payload():
    item = hr_documents._serialize_resignation_request_row(
        {
            "id": "req-1",
            "status": "approved",
            "purpose_code": "CAREER",
            "purpose_text": '{"expected_last_working_date":"2026-05-01","resignation_reason":"이직","handover_notes":"정리 완료"}',
        }
    )

    assert item["resignation_type"] == "CAREER"
    assert item["expected_last_working_date"] == "2026-05-01"
    assert item["resignation_reason"] == "이직"
    assert item["handover_notes"] == "정리 완료"
