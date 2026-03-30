from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.v1 import calendar as calendar_router
from app.schemas import (
    CalendarAttendeeOptionOut,
    CalendarContainerOut,
    CalendarEventOut,
    CalendarEventUpsertIn,
    CalendarMiniMonthDayOut,
    CalendarResourceOut,
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


def _sample_container() -> CalendarContainerOut:
    return CalendarContainerOut(
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


def _sample_event(container_id: str, *, resource_id=None) -> CalendarEventOut:
    return CalendarEventOut(
        id=uuid4(),
        container_id=container_id,
        title="Phase 2 일정",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        location="회의실 A",
        resource_id=resource_id,
        resource_label="회의실 A" if resource_id else None,
    )


def test_calendar_workspace_includes_resources(monkeypatch):
    container = _sample_container()
    event = _sample_event(str(container.id))
    resource = CalendarResourceOut(
        id=uuid4(),
        resource_code="ROOM-A",
        resource_name="회의실 A",
        resource_type="room",
        capacity=8,
        site_label="Apple_가로수길",
    )
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *args, **kwargs: [container])
    monkeypatch.setattr(calendar_router, "_resolve_selected_container", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_attendee_options", lambda *args, **kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_events", lambda *args, **kwargs: [event])
    monkeypatch.setattr(calendar_router, "_pick_selected_event", lambda *args, **kwargs: event)
    monkeypatch.setattr(calendar_router, "_site_scope_label", lambda *args, **kwargs: "전체 운영 범위")
    monkeypatch.setattr(calendar_router, "_role_label", lambda *args, **kwargs: "HQ Admin")
    monkeypatch.setattr(calendar_router, "_fetch_available_resources", lambda *args, **kwargs: [resource])
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

    assert len(result.resources) == 1
    assert result.resources[0].resource_name == "회의실 A"


def test_calendar_availability_returns_lanes_and_suggestions(monkeypatch):
    attendee = CalendarAttendeeOptionOut(
        user_id=uuid4(),
        employee_id=uuid4(),
        display_name="김하루",
        subtitle="R692 · Apple_가로수길",
        email="haru@example.com",
    )
    resource = CalendarResourceOut(
        id=uuid4(),
        resource_code="ROOM-A",
        resource_name="회의실 A",
        resource_type="room",
        capacity=8,
        site_label="Apple_가로수길",
    )
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_fetch_attendee_options", lambda *args, **kwargs: [attendee])
    monkeypatch.setattr(calendar_router, "_fetch_available_resources", lambda *args, **kwargs: [resource])

    def _busy_rows(*args, **kwargs):
        lane_type = kwargs.get("lane_type")
        if lane_type == "user":
            return [{
                "starts_at": datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 3, 30, 11, 0, tzinfo=timezone.utc),
                "title": "기존 1:1",
                "status": "confirmed",
            }]
        if lane_type == "resource":
            return [{
                "starts_at": datetime(2026, 3, 30, 13, 0, tzinfo=timezone.utc),
                "ends_at": datetime(2026, 3, 30, 14, 0, tzinfo=timezone.utc),
                "title": "회의실 사용 중",
                "status": "confirmed",
            }]
        return []

    monkeypatch.setattr(calendar_router, "_fetch_busy_rows_for_lane", _busy_rows)

    result = calendar_router.get_calendar_availability(
        date="2026-03-30",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 9, 30, tzinfo=timezone.utc),
        attendee_user_ids=[str(attendee.user_id)],
        attendee_employee_ids=[],
        attendee_emails=[],
        resource_id=str(resource.id),
        event_id=None,
        tenant_code=None,
        conn=_FakeConn(),
        user={"id": "user-1", "role": "hq_admin", "employee_id": "emp-1", "site_id": "site-1"},
    )

    assert len(result.lanes) == 2
    assert any(lane.lane_type == "attendee" for lane in result.lanes)
    assert any(lane.lane_type == "resource" for lane in result.lanes)
    assert result.suggested_slots


def test_create_calendar_event_uses_created_by_user_id_and_resource(monkeypatch):
    container = _sample_container()
    resource_id = uuid4()
    created_event = _sample_event(str(container.id), resource_id=resource_id)
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_validate_calendar_schedule_guards", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_upsert_calendar_event_relations", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_single_event", lambda *args, **kwargs: created_event)
    conn = _FakeConn(fetchone_queue=[{"id": str(created_event.id)}])
    payload = CalendarEventUpsertIn(
        container_id=container.id,
        title="새 일정",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        resource_id=resource_id,
    )

    result = calendar_router.create_calendar_event(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert str(result.id) == str(created_event.id)
    insert_sql = next(sql for sql, _ in conn.executed if "INSERT INTO calendar_events" in sql)
    assert "created_by_user_id" in insert_sql
    assert "organizer_user_id" not in insert_sql
    assert conn.commit_calls == 1


def test_validate_calendar_schedule_guards_blocks_resource_overlap(monkeypatch):
    payload = CalendarEventUpsertIn(
        container_id=uuid4(),
        title="충돌 테스트",
        starts_at=datetime(2026, 3, 30, 9, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 3, 30, 10, 0, tzinfo=timezone.utc),
        resource_id=uuid4(),
    )
    monkeypatch.setattr(calendar_router, "_collect_calendar_schedule_keys", lambda *args, **kwargs: (set(), set(), set()))
    monkeypatch.setattr(
        calendar_router,
        "_fetch_calendar_conflict_rows",
        lambda *args, **kwargs: [{
            "resource_id": str(payload.resource_id),
            "resource_label": "회의실 A",
        }],
    )

    with pytest.raises(HTTPException) as error:
        calendar_router._validate_calendar_schedule_guards(
            _FakeConn(),
            tenant_id="tenant-1",
            user={"id": str(uuid4()), "employee_id": str(uuid4())},
            payload=payload,
        )

    assert error.value.status_code == 409
    assert "회의실 A" in str(error.value.detail)
