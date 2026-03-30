from __future__ import annotations

import uuid

from app.routers.v1.leaves import review_leave
from app.schemas import LeaveRequestReview


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        self.conn.executions.append((sql, params))

    def fetchone(self):
        if not self.conn.fetchone_results:
            return None
        return self.conn.fetchone_results.pop(0)


class _FakeConn:
    def __init__(self, fetchone_results):
        self.fetchone_results = list(fetchone_results)
        self.executions: list[tuple[str, tuple | None]] = []

    def cursor(self):
        return _FakeCursor(self)


def _leave_row(*, status: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "tenant_code": "srs_korea",
        "employee_code": "R738-90329",
        "employee_name": "QA 전파 현장 0329",
        "site_code": "R738",
        "site_name": "Apple_명동",
        "leave_type": "annual",
        "half_day_slot": None,
        "start_at": "2026-04-02",
        "end_at": "2026-04-02",
        "reason": "QA_PROP_260329_A",
        "attachment_names": [],
        "status": status,
        "requested_at": "2026-03-28T15:40:12.994930Z",
        "reviewed_at": "2026-03-29T00:45:00Z" if status != "pending" else None,
        "review_note": None,
        "reviewed_by_username": "qa_prop_hq_0329" if status != "pending" else None,
        "tenant_id": "tenant-1",
        "employee_id": "employee-1",
        "site_id": "site-1",
    }


def test_review_leave_for_update_lock_query_uses_real_table_column_name():
    leave_id = uuid.uuid4()
    conn = _FakeConn(
        [
            {"id": str(leave_id)},
            _leave_row(status="pending"),
            _leave_row(status="approved"),
        ]
    )
    user = {
        "id": "user-1",
        "role": "hq_admin",
        "tenant_id": "tenant-1",
    }

    result = review_leave(
        leave_id,
        LeaveRequestReview(status="approved", review_note=None),
        conn=conn,
        user=user,
    )

    lock_sql, lock_params = conn.executions[0]
    assert "FROM leave_requests" in lock_sql
    assert "WHERE id = %s" in lock_sql
    assert "WHERE lr.id = %s" not in lock_sql
    assert lock_params == (leave_id, "tenant-1")
    assert result.status == "approved"

