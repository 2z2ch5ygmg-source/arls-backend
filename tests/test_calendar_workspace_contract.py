from __future__ import annotations

from uuid import uuid4

from app.routers.v1 import calendar as calendar_router
from app.schemas import (
    CalendarBookingLinkOut,
    CalendarContainerOut,
    CalendarEventOut,
    CalendarMiniMonthDayOut,
    CalendarSyncConnectionOut,
)

CONTAINER_SHARED_ID = str(uuid4())
CONTAINER_PERSONAL_ID = str(uuid4())
CONTAINER_TEAM_ID = str(uuid4())
BOOKING_ID = str(uuid4())
SYNC_ID = str(uuid4())


class _FakeConn:
    def __init__(self) -> None:
        self.commit_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1


class _CaptureCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query, params=None) -> None:
        self.executed.append((str(query), params))

    def fetchall(self):
        return []


class _CaptureConn:
    def __init__(self) -> None:
        self.cursor_obj = _CaptureCursor()

    def cursor(self):
        return self.cursor_obj


def _build_days(selected_date: str) -> list[CalendarMiniMonthDayOut]:
    rows: list[CalendarMiniMonthDayOut] = []
    for index in range(42):
        date_value = f"2026-03-{(index % 31) + 1:02d}"
        rows.append(
            CalendarMiniMonthDayOut(
                date=date_value,
                day=(index % 31) + 1,
                in_month=index < 31,
                is_today=index == 2,
                is_selected=date_value == selected_date,
            )
        )
    return rows


def _patch_common(monkeypatch, *, audience: str, scope_label: str, selected_date: str = "2026-03-30") -> None:
    monkeypatch.setattr(
        calendar_router,
        "resolve_scoped_tenant",
        lambda *args, **kwargs: {"id": "tenant-1"},
    )
    monkeypatch.setattr(calendar_router, "_resolve_calendar_audience", lambda _user: audience)
    monkeypatch.setattr(calendar_router, "_site_scope_label", lambda *_args, **_kwargs: scope_label)
    monkeypatch.setattr(calendar_router, "_role_label", lambda _user: "QA Role")
    monkeypatch.setattr(calendar_router, "_build_mini_month_days", lambda *_args, **_kwargs: _build_days(selected_date))
    monkeypatch.setattr(calendar_router, "_build_templates", lambda: [])
    monkeypatch.setattr(calendar_router, "_fetch_events", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_attendee_options", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_available_resources", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_pick_selected_event", lambda *_args, **_kwargs: None)


def test_calendar_workspace_hq_prefers_shared_container(monkeypatch):
    _patch_common(monkeypatch, audience="hq", scope_label="전체 운영 범위")
    shared_container = CalendarContainerOut(
        id=CONTAINER_SHARED_ID,
        name="전체 캘린더",
        color="#ff7a1a",
        scope_type="shared",
        provider="arls",
        is_default=True,
        badge_label="공유",
        owner_label="HQ",
    )
    personal_container = CalendarContainerOut(
        id=CONTAINER_PERSONAL_ID,
        name="내 캘린더",
        color="#2c6bff",
        scope_type="personal",
        provider="arls",
        is_default=False,
        badge_label="개인",
        owner_label="QA 사용자",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: CONTAINER_SHARED_ID)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [personal_container, shared_container])
    monkeypatch.setattr(
        calendar_router,
        "_fetch_booking_links",
        lambda *_args, **_kwargs: [
            CalendarBookingLinkOut(
                id=BOOKING_ID,
                title="파트너 미팅",
                slug="partner-meeting",
                approval_required=False,
                expires_at=None,
                booking_window_days=14,
                owner_label="HQ Admin",
            )
        ],
    )
    monkeypatch.setattr(
        calendar_router,
        "_fetch_sync_connections",
        lambda *_args, **_kwargs: [
            CalendarSyncConnectionOut(
                id=SYNC_ID,
                provider="google",
                account_label="hq@example.com",
                access_scope="read_write",
                sync_state="connected",
                last_synced_at="2026-03-30T10:00:00+09:00",
            )
        ],
    )
    user = {"id": "user-hq", "role": "hq_admin", "employee_id": "emp-1", "site_id": "site-1"}
    conn = _FakeConn()

    result = calendar_router.get_calendar_workspace(view="week", date="2026-03-30", tenant_code=None, conn=conn, user=user)

    assert conn.commit_calls == 1
    assert result.audience == "hq"
    assert str(result.selected_container_id) == CONTAINER_SHARED_ID
    assert result.capabilities.can_manage_shared is True
    assert result.capabilities.can_manage_booking_links is True
    assert result.capabilities.can_manage_sync is True
    assert result.scope_label == "전체 운영 범위"
    assert result.booking_links[0].slug == "partner-meeting"
    assert result.sync_connections[0].provider == "google"


def test_calendar_workspace_supervisor_uses_team_container(monkeypatch):
    _patch_common(monkeypatch, audience="supervisor", scope_label="Apple_명동 (R738)")
    team_container = CalendarContainerOut(
        id=CONTAINER_TEAM_ID,
        name="지점 캘린더",
        color="#ff7a1a",
        scope_type="team",
        provider="arls",
        is_default=True,
        badge_label="팀",
        owner_label="Apple_명동",
    )
    personal_container = CalendarContainerOut(
        id=CONTAINER_PERSONAL_ID,
        name="내 캘린더",
        color="#2c6bff",
        scope_type="personal",
        provider="arls",
        is_default=False,
        badge_label="개인",
        owner_label="Supervisor",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: CONTAINER_TEAM_ID)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [personal_container, team_container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    user = {"id": "user-sv", "role": "supervisor", "employee_id": "emp-2", "site_id": "site-1"}
    conn = _FakeConn()

    result = calendar_router.get_calendar_workspace(view="month", date="2026-03-01", tenant_code=None, conn=conn, user=user)

    assert result.audience == "supervisor"
    assert str(result.selected_container_id) == CONTAINER_TEAM_ID
    assert result.capabilities.can_manage_shared is False
    assert result.capabilities.can_manage_booking_links is True
    assert result.capabilities.can_manage_sync is False
    assert result.range_label == "2026년 3월"
    assert result.scope_label == "Apple_명동 (R738)"


def test_calendar_workspace_vice_keeps_team_scope_without_shared(monkeypatch):
    _patch_common(monkeypatch, audience="vice", scope_label="현장 준비도 범위")
    team_container = CalendarContainerOut(
        id=CONTAINER_TEAM_ID,
        name="현장 캘린더",
        color="#0f766e",
        scope_type="team",
        provider="arls",
        is_default=True,
        badge_label="팀",
        owner_label="Vice Supervisor",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: CONTAINER_TEAM_ID)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [team_container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    user = {"id": "user-vice", "role": "vice_supervisor", "employee_id": "emp-3", "site_id": "site-1"}

    result = calendar_router.get_calendar_workspace(view="agenda", date="2026-03-30", tenant_code=None, conn=_FakeConn(), user=user)

    assert result.audience == "vice"
    assert str(result.selected_container_id) == CONTAINER_TEAM_ID
    assert result.capabilities.can_manage_booking_links is True
    assert result.capabilities.can_manage_shared is False
    assert result.capabilities.can_manage_sync is False
    assert result.range_label == "2026년 3월 30일 이후"


def test_calendar_workspace_officer_is_personal_first(monkeypatch):
    _patch_common(monkeypatch, audience="officer", scope_label="본인 일정 범위")
    personal_container = CalendarContainerOut(
        id=CONTAINER_PERSONAL_ID,
        name="내 캘린더",
        color="#ff7a1a",
        scope_type="personal",
        provider="arls",
        is_default=True,
        badge_label="개인",
        owner_label="Officer",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [personal_container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    user = {"id": "user-officer", "role": "officer", "employee_id": "emp-4", "site_id": "site-1"}

    result = calendar_router.get_calendar_workspace(view="week", date="2026-03-30", tenant_code=None, conn=_FakeConn(), user=user)

    assert result.audience == "officer"
    assert str(result.selected_container_id) == CONTAINER_PERSONAL_ID
    assert result.capabilities.can_create is True
    assert result.capabilities.can_manage_booking_links is False
    assert result.capabilities.can_manage_shared is False
    assert result.capabilities.can_manage_sync is False
    assert result.scope_label == "본인 일정 범위"


def test_calendar_workspace_booking_links_view_uses_booking_range_label(monkeypatch):
    _patch_common(monkeypatch, audience="hq", scope_label="전체 운영 범위")
    container = CalendarContainerOut(
        id=CONTAINER_SHARED_ID,
        name="전체 캘린더",
        color="#ff7a1a",
        scope_type="shared",
        provider="arls",
        is_default=True,
        badge_label="공유",
        owner_label="HQ",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: CONTAINER_SHARED_ID)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    user = {"id": "user-hq", "role": "developer", "employee_id": "emp-1", "site_id": "site-1"}

    result = calendar_router.get_calendar_workspace(view="booking-links", date="2026-03-30", tenant_code=None, conn=_FakeConn(), user=user)

    assert result.view == "booking-links"
    assert result.range_label == "예약 링크"


def test_calendar_workspace_marks_single_selected_mini_month_day(monkeypatch):
    _patch_common(monkeypatch, audience="officer", scope_label="본인 일정 범위", selected_date="2026-03-30")
    personal_container = CalendarContainerOut(
        id=CONTAINER_PERSONAL_ID,
        name="내 캘린더",
        color="#ff7a1a",
        scope_type="personal",
        provider="arls",
        is_default=True,
        badge_label="개인",
        owner_label="Officer",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [personal_container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    user = {"id": "user-officer", "role": "officer", "employee_id": "emp-4", "site_id": "site-1"}

    result = calendar_router.get_calendar_workspace(view="week", date="2026-03-30", tenant_code=None, conn=_FakeConn(), user=user)

    selected_rows = [row for row in result.mini_month_days if row.is_selected]
    assert len(result.mini_month_days) == 42
    assert len(selected_rows) == 1
    assert selected_rows[0].date == "2026-03-30"


def test_calendar_workspace_includes_selected_event(monkeypatch):
    _patch_common(monkeypatch, audience="hq", scope_label="전체 운영 범위")
    container = CalendarContainerOut(
        id=CONTAINER_SHARED_ID,
        name="전체 캘린더",
        color="#ff7a1a",
        scope_type="shared",
        provider="arls",
        is_default=True,
        badge_label="공유",
        owner_label="HQ",
    )
    event = CalendarEventOut(
        id=uuid4(),
        container_id=CONTAINER_SHARED_ID,
        title="주간 운영 회의",
        starts_at="2026-03-30T09:00:00+09:00",
        ends_at="2026-03-30T10:00:00+09:00",
        location="회의실 A",
    )
    monkeypatch.setattr(calendar_router, "_ensure_personal_container", lambda *_args, **_kwargs: CONTAINER_PERSONAL_ID)
    monkeypatch.setattr(calendar_router, "_ensure_shared_container", lambda *_args, **_kwargs: CONTAINER_SHARED_ID)
    monkeypatch.setattr(calendar_router, "_ensure_team_container", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_workspace_containers", lambda *_args, **_kwargs: [container])
    monkeypatch.setattr(calendar_router, "_fetch_booking_links", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_sync_connections", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(calendar_router, "_fetch_events", lambda *_args, **_kwargs: [event])
    monkeypatch.setattr(calendar_router, "_pick_selected_event", lambda *_args, **_kwargs: event)

    result = calendar_router.get_calendar_workspace(
        view="week",
        date="2026-03-30",
        tenant_code=None,
        conn=_FakeConn(),
        user={"id": "user-hq", "role": "hq_admin", "employee_id": "emp-1", "site_id": "site-1"},
    )

    assert len(result.events) == 1
    assert str(result.selected_event.id) == str(event.id)


def test_fetch_workspace_containers_orders_by_selected_scope_alias():
    conn = _CaptureConn()

    calendar_router._fetch_workspace_containers(
        conn,
        tenant_id="tenant-1",
        user={"id": "user-1", "site_id": "site-1"},
    )

    query, params = conn.cursor_obj.executed[0]
    assert "AS scope_sort" in query
    assert "ORDER BY\n              scope_sort," in query
    assert params == ("user-1", "user-1", "tenant-1", "user-1", True, "site-1", "user-1")
