from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.routers.v1 import calendar as calendar_router
from app.schemas import (
    CalendarAttendeeOptionOut,
    CalendarContainerOut,
    CalendarEventOut,
    CalendarEventUpsertIn,
    CalendarMiniMonthDayOut,
)


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
        self.commit_calls = 0

    def cursor(self):
        return _FakeCursor(self)

    def commit(self):
        self.commit_calls += 1


def _sample_event(container_id: str) -> CalendarEventOut:
    return CalendarEventOut(
        id=uuid4(),
        container_id=container_id,
        title="Phase 1 일정",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        location="회의실 A",
    )


def test_calendar_workspace_includes_events_and_attendee_options(monkeypatch):
    container = CalendarContainerOut(
        id=uuid4(),
        scope_type="shared",
        name="공유 캘린더",
        color="#ff7a1a",
        provider="arls",
        permission="owner",
        is_default=True,
        badge_label="공유",
        owner_label="공용 일정",
    )
    event = _sample_event(str(container.id))
    attendee = CalendarAttendeeOptionOut(
        user_id=uuid4(),
        employee_id=uuid4(),
        display_name="김하루",
        subtitle="R692 · Apple_가로수길",
        email="haru@example.com",
    )
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *args, **kwargs: [container])
    monkeypatch.setattr(calendar_router, "_resolve_selected_container", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_attendee_options", lambda *args, **kwargs: [attendee])
    monkeypatch.setattr(calendar_router, "_fetch_events", lambda *args, **kwargs: [event])
    monkeypatch.setattr(calendar_router, "_pick_selected_event", lambda *args, **kwargs: event)
    monkeypatch.setattr(calendar_router, "_site_scope_label", lambda *args, **kwargs: "전체 운영 범위")
    monkeypatch.setattr(calendar_router, "_role_label", lambda *args, **kwargs: "HQ Admin")
    monkeypatch.setattr(calendar_router, "_build_mini_month_days", lambda *args, **kwargs: [
        CalendarMiniMonthDayOut(
            date="2026-03-30",
            day=30,
            in_month=True,
            is_today=False,
            is_selected=True,
        )
    ])

    result = calendar_router.get_calendar_workspace(
        view="week",
        date="2026-03-30",
        container_id=str(container.id),
        event_id=str(event.id),
        tenant_code=None,
        conn=_FakeConn(),
        user={"id": "user-1", "role": "hq_admin", "employee_id": "emp-1", "site_id": "site-1"},
    )

    assert len(result.events) == 1
    assert str(result.selected_event.id) == str(event.id)
    assert len(result.attendee_options) == 1
    assert result.attendee_options[0].display_name == "김하루"


def test_create_calendar_event_returns_saved_event(monkeypatch):
    container = CalendarContainerOut(
        id=uuid4(),
        scope_type="personal",
        name="내 캘린더",
        color="#ff7a1a",
        provider="arls",
        permission="owner",
    )
    created_event = _sample_event(str(container.id))
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_upsert_calendar_event_relations", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_single_event", lambda *args, **kwargs: created_event)
    conn = _FakeConn(fetchone_queue=[{"id": str(created_event.id)}])
    payload = CalendarEventUpsertIn(
        container_id=container.id,
        title="새 일정",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
    )

    result = calendar_router.create_calendar_event(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert str(result.id) == str(created_event.id)
    assert conn.commit_calls == 1
    assert any("INSERT INTO calendar_events" in sql for sql, _ in conn.executed)


def test_delete_calendar_event_removes_target(monkeypatch):
    container = CalendarContainerOut(
        id=uuid4(),
        scope_type="team",
        name="현장 캘린더",
        color="#1c66ff",
        provider="arls",
        permission="edit",
    )
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    conn = _FakeConn(fetchone_queue=[{"container_id": str(container.id)}])

    result = calendar_router.delete_calendar_event(
        event_id=str(uuid4()),
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "supervisor", "employee_id": str(uuid4())},
    )

    assert result["deleted"] is True
    assert conn.commit_calls == 1
    assert any("DELETE FROM calendar_events" in sql for sql, _ in conn.executed)
