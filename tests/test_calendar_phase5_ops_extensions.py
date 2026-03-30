from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.routers.v1 import calendar as calendar_router
from app.schemas import (
    CalendarBookingLinkCreateIn,
    CalendarBookingLinkOut,
    CalendarCommentIn,
    CalendarCommentOut,
    CalendarContainerOut,
    CalendarCustomFieldRowOut,
    CalendarEventOut,
    CalendarEventUpsertIn,
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


def _sample_booking_link(container_id) -> CalendarBookingLinkOut:
    return CalendarBookingLinkOut(
        id=uuid4(),
        container_id=container_id,
        slug="ops-link",
        title="Ops Link",
        description="Phase 5 booking",
        approval_required=True,
        approval_policy="manual",
        assignment_mode="round_robin",
        is_public=True,
        booking_window_days=10,
        buffer_before_minutes=10,
        buffer_after_minutes=15,
        duration_minutes=45,
        availability_start_time="09:00",
        availability_end_time="18:00",
        owner_label="HQ Admin",
    )


def _sample_event(container_id) -> CalendarEventOut:
    return CalendarEventOut(
        id=uuid4(),
        container_id=container_id,
        title="Phase 5 일정",
        starts_at=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc),
        custom_fields=[
            CalendarCustomFieldRowOut(
                key="project",
                label="프로젝트",
                value="ARLS Calendar",
                field_type="text",
            )
        ],
        comments=[
            CalendarCommentOut(
                id=uuid4(),
                body="첫 댓글",
                is_internal=False,
                created_at=datetime(2026, 4, 1, 0, 0, tzinfo=timezone.utc),
                author_label="HQ Admin",
            )
        ],
    )


def _patch_scope(monkeypatch):
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})


def test_create_booking_link_persists_assignment_and_approval_policy(monkeypatch):
    _patch_scope(monkeypatch)
    container = _sample_container()
    expected = _sample_booking_link(container.id)
    conn = _FakeConn(fetchone_queue=[{"id": str(expected.id)}])
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_generate_booking_slug", lambda *args, **kwargs: expected.slug)
    monkeypatch.setattr(calendar_router, "_fetch_booking_link_for_manager", lambda *args, **kwargs: expected)

    payload = CalendarBookingLinkCreateIn(
        container_id=container.id,
        title="Ops Link",
        description="Phase 5 booking",
        approval_policy="manual",
        assignment_mode="round_robin",
        duration_minutes=45,
        booking_window_days=10,
        buffer_before_minutes=10,
        buffer_after_minutes=15,
        availability_start_time="09:00",
        availability_end_time="18:00",
    )

    result = calendar_router.create_calendar_booking_link(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert result.approval_policy == "manual"
    assert result.assignment_mode == "round_robin"
    insert_sql, insert_params = next((sql, params) for sql, params in conn.executed if "INSERT INTO calendar_booking_links" in sql)
    assert "approval_policy" in insert_sql
    assert "assignment_mode" in insert_sql
    assert "manual" in insert_params
    assert "round_robin" in insert_params


def test_public_booking_submit_uses_manual_policy_for_pending(monkeypatch):
    starts_at = datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc)
    row = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "owner_user_id": uuid4(),
        "container_id": uuid4(),
        "slug": "ops-link",
        "title": "Ops Link",
        "description": "booking",
        "approval_required": False,
        "approval_policy": "manual",
        "assignment_mode": "round_robin",
        "is_public": True,
        "booking_window_days": 10,
        "buffer_before_minutes": 10,
        "buffer_after_minutes": 15,
        "duration_minutes": 45,
        "availability_start_time": "09:00",
        "availability_end_time": "18:00",
        "expires_at": None,
        "host_notes": "",
        "intake_questions_json": [],
        "owner_label": "HQ Admin",
    }
    monkeypatch.setattr(calendar_router, "_fetch_public_booking_link_row", lambda *args, **kwargs: row)
    monkeypatch.setattr(
        calendar_router,
        "_build_public_booking_slots",
        lambda *args, **kwargs: [
            calendar_router.CalendarBookingSlotOut(
                starts_at=starts_at.astimezone(calendar_router.KST),
                ends_at=(starts_at + timedelta(minutes=45)).astimezone(calendar_router.KST),
                label="04.01 10:00 - 10:45",
                date_label="2026년 04월 01일",
            )
        ],
    )
    conn = _FakeConn(fetchone_queue=[{"id": str(uuid4())}])

    result = calendar_router.submit_public_calendar_booking(
        slug="ops-link",
        payload=calendar_router.CalendarPublicBookingSubmitIn(
            guest_name="외부 게스트",
            guest_email="guest@example.com",
            starts_at=starts_at,
        ),
        conn=conn,
    )

    assert result.status == "pending"
    assert result.approval_policy == "manual"


def test_create_calendar_event_serializes_custom_fields(monkeypatch):
    _patch_scope(monkeypatch)
    container = _sample_container()
    expected = _sample_event(str(container.id))
    conn = _FakeConn(fetchone_queue=[{"id": str(expected.id)}])
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_validate_calendar_schedule_guards", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_upsert_calendar_event_relations", lambda *args, **kwargs: None)
    monkeypatch.setattr(calendar_router, "_fetch_single_event", lambda *args, **kwargs: expected)

    payload = CalendarEventUpsertIn(
        container_id=container.id,
        title="Phase 5 일정",
        starts_at=datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 4, 1, 2, 0, tzinfo=timezone.utc),
        custom_fields=[
            {
                "label": "프로젝트",
                "value": "ARLS Calendar",
                "field_type": "text",
            }
        ],
    )

    result = calendar_router.create_calendar_event(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert str(result.id) == str(expected.id)
    insert_sql, insert_params = next((sql, params) for sql, params in conn.executed if "INSERT INTO calendar_events" in sql)
    assert "custom_fields_json" in insert_sql
    assert "ARLS Calendar" in str(insert_params)


def test_create_calendar_event_comment_returns_refreshed_event(monkeypatch):
    _patch_scope(monkeypatch)
    container = _sample_container()
    expected = _sample_event(str(container.id))
    conn = _FakeConn(fetchone_queue=[{"container_id": str(container.id)}])
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_fetch_single_event", lambda *args, **kwargs: expected)

    result = calendar_router.create_calendar_event_comment(
        event_id=str(expected.id),
        payload=CalendarCommentIn(body="승인 전 확인 부탁드립니다.", is_internal=True),
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert str(result.id) == str(expected.id)
    insert_sql, insert_params = next((sql, params) for sql, params in conn.executed if "INSERT INTO calendar_comments" in sql)
    assert "calendar_comments" in insert_sql
    assert "승인 전 확인 부탁드립니다." in str(insert_params)
    assert conn.commit_calls == 1
