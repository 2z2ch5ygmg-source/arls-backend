from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.routers.v1 import attendance as attendance_router
from app.schemas import AttendanceCreate


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._one = None
        self._all = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        sql = " ".join(str(query).split())
        self.conn.queries.append((sql, params))
        self._one = None
        self._all = []

        if "FROM employees e" in sql:
            self._one = {"id": "emp-1", "site_id": "site-1"}
            return
        if "FROM sites" in sql:
            self._one = {
                "id": "site-1",
                "site_name": "Apple_명동",
                "latitude": 37.564553,
                "longitude": 126.982897,
                "radius_meters": 100,
            }
            return
        if "SELECT id, event_type, event_at FROM attendance_records" in sql:
            self._all = []
            return
        if "INSERT INTO attendance_records" in sql:
            self.conn.last_event_at = params[4]
            self._one = {
                "id": "11111111-1111-1111-1111-111111111111",
                "event_at": params[4],
            }
            return
        if "SELECT ar.id, ar.employee_id, ar.event_type, ar.event_at" in sql:
            self._one = {
                "id": "11111111-1111-1111-1111-111111111111",
                "employee_id": "emp-1",
                "event_type": "check_in",
                "event_at": self.conn.last_event_at,
                "site_name": "Apple_명동",
                "distance_meters": 0,
                "is_within_radius": True,
                "employee_code": "R738-90329",
                "auto_checkout": False,
            }
            return
        raise AssertionError(f"Unexpected SQL: {sql}")

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class FakeConn:
    def __init__(self):
        self.queries = []
        self.last_event_at = None

    def cursor(self):
        return FakeCursor(self)


def test_create_record_allows_case_insensitive_tenant_code(monkeypatch):
    monkeypatch.setattr(attendance_router, "haversine_meters", lambda *args, **kwargs: 0.0)
    monkeypatch.setattr(attendance_router, "send_attendance_push_notification", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        attendance_router,
        "resolve_event_context",
        lambda *args, **kwargs: {"sessions": [], "checkin_window": None, "open_session": None},
    )

    conn = FakeConn()
    payload = AttendanceCreate(
        tenant_code="SRS_KOREA",
        employee_code="R738-90329",
        site_code="R738",
        event_type="check_in",
        event_at=datetime(2026, 3, 29, 0, 18, 28, tzinfo=timezone.utc),
        latitude=37.564553,
        longitude=126.982897,
    )
    user = {
        "tenant_id": "tenant-1",
        "tenant_code": "srs_korea",
        "role": "officer",
        "full_name": "QA 전파 현장 0329",
        "id": "user-1",
    }

    result = attendance_router.create_record(payload, idempotency_key=None, conn=conn, user=user)

    assert result.already_exists is False
    assert UUID(str(result.record.id))
    assert result.record.event_type == "check_in"
    tenant_lookup_query = next(sql for sql, _ in conn.queries if "FROM employees e" in sql)
    assert "upper(trim(t.tenant_code)) = upper(trim(%s))" in tenant_lookup_query
