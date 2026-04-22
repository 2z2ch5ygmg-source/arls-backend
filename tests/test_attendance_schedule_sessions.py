from __future__ import annotations

from datetime import date, datetime, timezone

from app.services.attendance_sessions import (
    KST,
    build_schedule_window,
    build_sessions,
    derive_session_status,
    select_checkin_window,
    select_open_session,
    summarize_window,
)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _schedule(
    business_date: date,
    start: str,
    end: str,
    *,
    shift_type: str = "day",
    schedule_id: str = "schedule-1",
):
    return build_schedule_window(
        {
            "id": schedule_id,
            "schedule_date": business_date,
            "shift_type": shift_type,
            "shift_start_time": start,
            "shift_end_time": end,
            "site_id": "site-1",
            "site_code": "SEOUL01",
        }
    )


def test_early_checkin_is_normal_but_worked_time_clamps_to_schedule_start():
    window = _schedule(date(2026, 4, 15), "10:00", "12:00")
    session = build_sessions(
        [window],
        [
            {"id": "in-1", "event_type": "check_in", "event_at": _dt("2026-04-14T23:00:00+00:00")},
            {"id": "out-1", "event_type": "check_out", "event_at": _dt("2026-04-15T03:00:00+00:00")},
        ],
        now_utc=_dt("2026-04-15T04:00:00+00:00"),
    )[0]

    assert session["business_date"] == date(2026, 4, 15)
    assert session["check_in_status"] == "normal_check_in"
    assert session["check_out_status"] == "normal_checkout"
    assert session["worked_minutes"] == 120


def test_late_checkin_is_late_and_late_checkout_clamps_to_schedule_end():
    window = _schedule(date(2026, 4, 15), "10:00", "12:00")
    session = build_sessions(
        [window],
        [
            {"id": "in-1", "event_type": "check_in", "event_at": _dt("2026-04-15T01:01:00+00:00")},
            {"id": "out-1", "event_type": "check_out", "event_at": _dt("2026-04-15T03:40:00+00:00")},
        ],
        now_utc=_dt("2026-04-15T04:00:00+00:00"),
    )[0]

    assert session["check_in_status"] == "late_check_in"
    assert session["check_out_status"] == "normal_checkout"
    assert session["session_status"] == "late_check_in"
    assert session["worked_minutes"] == 119


def test_missing_checkout_after_grace_and_delayed_checkout_status():
    window = _schedule(date(2026, 4, 15), "10:00", "12:00")
    missing = derive_session_status(
        window=window,
        check_in_at=_dt("2026-04-15T01:00:00+00:00"),
        check_out_at=None,
        now_utc=_dt("2026-04-15T04:01:00+00:00"),
    )
    delayed = derive_session_status(
        window=window,
        check_in_at=_dt("2026-04-15T01:00:00+00:00"),
        check_out_at=_dt("2026-04-15T04:10:00+00:00"),
        now_utc=_dt("2026-04-15T04:20:00+00:00"),
    )

    assert missing["session_status"] == "missing_checkout"
    assert missing["check_out_status"] == "missing_checkout"
    assert delayed["session_status"] == "delayed_checkout"
    assert delayed["check_out_status"] == "delayed_checkout"
    assert delayed["worked_minutes"] == 120


def test_user_adjacent_overnight_and_day_shift_example():
    overnight = _schedule(
        date(2026, 4, 14),
        "22:00",
        "08:00",
        shift_type="night",
        schedule_id="night-14",
    )
    day = _schedule(
        date(2026, 4, 15),
        "08:00",
        "22:00",
        shift_type="day",
        schedule_id="day-15",
    )
    rows = [
        {"id": "in-14", "event_type": "check_in", "event_at": _dt("2026-04-14T12:55:00+00:00")},
        {"id": "out-14", "event_type": "check_out", "event_at": _dt("2026-04-14T23:11:00+00:00")},
        {"id": "in-15", "event_type": "check_in", "event_at": _dt("2026-04-14T23:12:00+00:00")},
        {"id": "out-15", "event_type": "check_out", "event_at": _dt("2026-04-15T13:11:00+00:00")},
    ]

    sessions = build_sessions([overnight, day], rows, now_utc=_dt("2026-04-15T14:00:00+00:00"))

    assert sessions[0]["business_date"] == date(2026, 4, 14)
    assert sessions[0]["check_in_status"] == "normal_check_in"
    assert sessions[0]["check_out_status"] == "normal_checkout"
    assert sessions[0]["worked_minutes"] == 600
    assert sessions[1]["business_date"] == date(2026, 4, 15)
    assert sessions[1]["check_in_status"] == "late_check_in"
    assert sessions[1]["check_out_status"] == "normal_checkout"
    assert sessions[1]["worked_minutes"] == 828


def test_same_day_open_session_is_not_actionable_after_midnight_but_overnight_is():
    same_day = _schedule(date(2026, 4, 14), "10:00", "12:00", schedule_id="day-14")
    overnight = _schedule(date(2026, 4, 14), "22:00", "08:00", shift_type="night", schedule_id="night-14")
    same_day_session = build_sessions(
        [same_day],
        [{"id": "in-1", "event_type": "check_in", "event_at": _dt("2026-04-14T01:00:00+00:00")}],
        now_utc=_dt("2026-04-14T16:00:00+00:00"),
    )
    overnight_session = build_sessions(
        [overnight],
        [{"id": "in-2", "event_type": "check_in", "event_at": _dt("2026-04-14T12:55:00+00:00")}],
        now_utc=_dt("2026-04-14T16:00:00+00:00"),
    )

    assert select_open_session(same_day_session, now_utc=_dt("2026-04-14T16:00:00+00:00")) is None
    assert select_open_session(overnight_session, now_utc=_dt("2026-04-14T16:00:00+00:00")) is not None


def test_summary_for_schedule_window_uses_business_date():
    window = _schedule(date(2026, 4, 14), "22:00", "08:00", shift_type="night")
    sessions = build_sessions(
        [window],
        [
            {"id": "in-1", "event_type": "check_in", "event_at": _dt("2026-04-14T12:55:00+00:00")},
            {"id": "out-1", "event_type": "check_out", "event_at": _dt("2026-04-14T23:11:00+00:00")},
        ],
        now_utc=_dt("2026-04-15T00:00:00+00:00"),
    )
    summary = summarize_window(window, sessions, now_utc=_dt("2026-04-15T00:00:00+00:00"))

    assert summary["date"] == "2026-04-14"
    assert summary["business_date"] == "2026-04-14"
    assert summary["check_in_count"] == 1
    assert summary["check_out_count"] == 1
    assert summary["session_status"] == "normal_checkout"


def test_checkin_selection_prefers_upcoming_shift_in_normal_lead_window():
    day = _schedule(date(2026, 4, 14), "08:00", "22:00", schedule_id="day-14")
    night = _schedule(date(2026, 4, 14), "22:00", "08:00", shift_type="night", schedule_id="night-14")

    selected = select_checkin_window([day, night], _dt("2026-04-14T12:55:00+00:00"))

    assert selected is night
