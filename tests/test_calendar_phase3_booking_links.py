from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.routers.v1 import calendar as calendar_router
from app.schemas import (
    CalendarBookingLinkCreateIn,
    CalendarBookingLinkOut,
    CalendarBookingQuestionIn,
    CalendarBookingQuestionOut,
    CalendarBookingSlotOut,
    CalendarContainerOut,
    CalendarPublicBookingSubmitIn,
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
        slug="team-standup-abc123",
        title="팀 스탠드업 링크",
        description="외부 예약 링크",
        approval_required=True,
        is_public=True,
        booking_window_days=14,
        buffer_before_minutes=10,
        buffer_after_minutes=10,
        duration_minutes=30,
        availability_start_time="09:00",
        availability_end_time="18:00",
        host_notes="호스트 전용 메모",
        intake_questions=[
            CalendarBookingQuestionOut(
                key="agenda",
                label="논의 안건",
                answer_type="long_text",
                required=True,
                options=[],
            )
        ],
        owner_label="HQ Admin",
    )


def test_create_booking_link_returns_saved_row(monkeypatch):
    container = _sample_container()
    expected = _sample_booking_link(container.id)
    conn = _FakeConn(fetchone_queue=[{"id": str(expected.id)}])
    monkeypatch.setattr(calendar_router, "resolve_scoped_tenant", lambda *args, **kwargs: {"id": "tenant-1"})
    monkeypatch.setattr(calendar_router, "_resolve_calendar_container_access", lambda *args, **kwargs: container)
    monkeypatch.setattr(calendar_router, "_generate_booking_slug", lambda *args, **kwargs: expected.slug)
    monkeypatch.setattr(calendar_router, "_fetch_booking_link_for_manager", lambda *args, **kwargs: expected)

    payload = CalendarBookingLinkCreateIn(
        container_id=container.id,
        title="팀 스탠드업 링크",
        description="외부 예약 링크",
        approval_required=True,
        booking_window_days=14,
        buffer_before_minutes=10,
        buffer_after_minutes=10,
        duration_minutes=30,
        availability_start_time="09:00",
        availability_end_time="18:00",
        host_notes="호스트 전용 메모",
        intake_questions=[CalendarBookingQuestionIn(label="논의 안건", answer_type="long_text")],
    )

    result = calendar_router.create_calendar_booking_link(
        payload=payload,
        tenant_code=None,
        conn=conn,
        user={"id": str(uuid4()), "role": "hq_admin", "employee_id": str(uuid4())},
    )

    assert str(result.id) == str(expected.id)
    assert result.slug == expected.slug
    assert conn.commit_calls == 1
    insert_sql = next(sql for sql, _ in conn.executed if "INSERT INTO calendar_booking_links" in sql)
    assert "duration_minutes" in insert_sql
    assert "availability_start_time" in insert_sql


def test_public_booking_fetch_returns_slots(monkeypatch):
    row = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "owner_user_id": uuid4(),
        "container_id": uuid4(),
        "slug": "public-demo",
        "title": "외부 미팅",
        "description": "예약 링크 설명",
        "approval_required": False,
        "is_public": True,
        "booking_window_days": 7,
        "buffer_before_minutes": 5,
        "buffer_after_minutes": 5,
        "duration_minutes": 30,
        "availability_start_time": "09:00",
        "availability_end_time": "18:00",
        "expires_at": None,
        "host_notes": "internal",
        "intake_questions_json": [{"key": "company", "label": "회사명", "answer_type": "short_text", "required": True}],
        "owner_label": "HQ Admin",
    }
    slots = [
        CalendarBookingSlotOut(
            starts_at=datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 3, 31, 1, 30, tzinfo=timezone.utc),
            label="03.31 10:00 - 10:30",
            date_label="2026년 03월 31일",
        )
    ]
    monkeypatch.setattr(calendar_router, "_fetch_public_booking_link_row", lambda *args, **kwargs: row)
    monkeypatch.setattr(calendar_router, "_build_public_booking_slots", lambda *args, **kwargs: slots)

    result = calendar_router.get_public_calendar_booking_link("public-demo", conn=_FakeConn())

    assert result.slug == "public-demo"
    assert len(result.slots) == 1
    assert result.intake_questions[0].label == "회사명"


def test_public_booking_submit_returns_pending(monkeypatch):
    starts_at = datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc)
    row = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "owner_user_id": uuid4(),
        "container_id": uuid4(),
        "slug": "public-demo",
        "title": "외부 미팅",
        "description": "예약 링크 설명",
        "approval_required": True,
        "is_public": True,
        "booking_window_days": 7,
        "buffer_before_minutes": 5,
        "buffer_after_minutes": 5,
        "duration_minutes": 30,
        "availability_start_time": "09:00",
        "availability_end_time": "18:00",
        "expires_at": None,
        "host_notes": "internal",
        "intake_questions_json": [],
        "owner_label": "HQ Admin",
    }
    monkeypatch.setattr(calendar_router, "_fetch_public_booking_link_row", lambda *args, **kwargs: row)
    monkeypatch.setattr(
        calendar_router,
        "_build_public_booking_slots",
        lambda *args, **kwargs: [
            CalendarBookingSlotOut(
                starts_at=starts_at.astimezone(calendar_router.KST),
                ends_at=(starts_at + timedelta(minutes=30)).astimezone(calendar_router.KST),
                label="03.31 10:00 - 10:30",
                date_label="2026년 03월 31일",
            )
        ],
    )
    conn = _FakeConn(fetchone_queue=[{"id": str(uuid4())}])
    payload = CalendarPublicBookingSubmitIn(
        guest_name="외부 게스트",
        guest_email="guest@example.com",
        starts_at=starts_at,
        note="사전 공유 메모",
        answers={"company": "OpenAI"},
    )

    result = calendar_router.submit_public_calendar_booking(
        slug="public-demo",
        payload=payload,
        conn=conn,
    )

    assert result.status == "pending"
    assert result.approval_required is True
    assert conn.commit_calls == 1
    insert_sql = next(sql for sql, _ in conn.executed if "INSERT INTO calendar_events" in sql)
    assert "calendar_events" in insert_sql


def test_public_booking_submit_blocks_unavailable_slot(monkeypatch):
    row = {
        "id": uuid4(),
        "tenant_id": uuid4(),
        "owner_user_id": uuid4(),
        "container_id": uuid4(),
        "slug": "public-demo",
        "title": "외부 미팅",
        "description": "예약 링크 설명",
        "approval_required": False,
        "is_public": True,
        "booking_window_days": 7,
        "buffer_before_minutes": 5,
        "buffer_after_minutes": 5,
        "duration_minutes": 30,
        "availability_start_time": "09:00",
        "availability_end_time": "18:00",
        "expires_at": None,
        "host_notes": "internal",
        "intake_questions_json": [],
        "owner_label": "HQ Admin",
    }
    monkeypatch.setattr(calendar_router, "_fetch_public_booking_link_row", lambda *args, **kwargs: row)
    monkeypatch.setattr(calendar_router, "_build_public_booking_slots", lambda *args, **kwargs: [])

    with pytest.raises(HTTPException) as error:
        calendar_router.submit_public_calendar_booking(
            slug="public-demo",
            payload=CalendarPublicBookingSubmitIn(
                guest_name="외부 게스트",
                guest_email="guest@example.com",
                starts_at=datetime(2026, 3, 31, 1, 0, tzinfo=timezone.utc),
            ),
            conn=_FakeConn(),
        )

    assert error.value.status_code == 409
