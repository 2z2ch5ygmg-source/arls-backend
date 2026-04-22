from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
NORMAL_CHECKIN_LEAD = timedelta(minutes=60)
MISSED_CHECKOUT_GRACE = timedelta(minutes=60)


def ensure_utc(value: datetime | None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def ensure_kst(value: datetime | None) -> datetime:
    return ensure_utc(value).astimezone(KST)


def normalize_shift_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    aliases = {
        "leave": "off",
        "annual_leave": "off",
        "half_leave": "off",
        "holiday_leave": "holiday",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"day", "overtime", "night", "off", "holiday"}:
        return normalized
    return ""


def normalize_time_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt_time):
        return value.strftime("%H:%M:%S")
    text = str(value).strip()
    if not text:
        return ""
    if len(text) >= 8 and text[2] == ":" and text[5] == ":":
        return text[:8]
    if len(text) >= 5 and text[2] == ":":
        return f"{text[:5]}:00"
    return ""


def time_to_minutes(value: Any) -> int | None:
    text = normalize_time_value(value)
    if not text:
        return None
    try:
        hour, minute, _second = [int(part) for part in text.split(":")]
    except (TypeError, ValueError):
        return None
    if hour == 24 and minute == 0:
        return 1440
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return hour * 60 + minute


def minutes_to_time_text(value: int) -> str:
    safe = value % 1440
    return f"{safe // 60:02d}:{safe % 60:02d}:00"


def default_shift_times(shift_type: str) -> tuple[str, str]:
    if shift_type == "night":
        return "22:00:00", "08:00:00"
    if shift_type == "overtime":
        return "18:00:00", "22:00:00"
    return "09:00:00", "18:00:00"


@dataclass(frozen=True)
class ScheduleWindow:
    business_date: date
    schedule_id: str
    shift_type: str
    site_id: str
    site_code: str
    start_at: datetime
    end_at: datetime
    is_overnight: bool

    @property
    def normal_check_in_start_at(self) -> datetime:
        return self.start_at - NORMAL_CHECKIN_LEAD

    @property
    def missed_checkout_at(self) -> datetime:
        return self.end_at + MISSED_CHECKOUT_GRACE


def build_schedule_window(row: dict[str, Any]) -> ScheduleWindow | None:
    business_date_raw = row.get("schedule_date")
    if isinstance(business_date_raw, datetime):
        business_date = business_date_raw.date()
    elif isinstance(business_date_raw, date):
        business_date = business_date_raw
    else:
        try:
            business_date = date.fromisoformat(str(business_date_raw or "").strip())
        except ValueError:
            return None

    shift_type = normalize_shift_type(row.get("shift_type")) or "day"
    if shift_type in {"off", "holiday"}:
        return ScheduleWindow(
            business_date=business_date,
            schedule_id=str(row.get("id") or ""),
            shift_type=shift_type,
            site_id=str(row.get("site_id") or ""),
            site_code=str(row.get("site_code") or ""),
            start_at=datetime.combine(business_date, dt_time.min, tzinfo=KST),
            end_at=datetime.combine(business_date, dt_time.min, tzinfo=KST),
            is_overnight=False,
        )

    start_text = (
        normalize_time_value(row.get("shift_start_time"))
        or normalize_time_value(row.get("template_start_time"))
        or normalize_time_value(row.get("start_time"))
    )
    end_text = (
        normalize_time_value(row.get("shift_end_time"))
        or normalize_time_value(row.get("template_end_time"))
        or normalize_time_value(row.get("end_time"))
    )
    if not start_text or not end_text:
        start_text, end_text = default_shift_times(shift_type)

    start_minutes = time_to_minutes(start_text)
    end_minutes = time_to_minutes(end_text)
    if start_minutes is None or end_minutes is None:
        return None

    start_at = datetime.combine(
        business_date,
        dt_time(hour=start_minutes // 60, minute=start_minutes % 60),
        tzinfo=KST,
    )
    end_date = business_date
    is_overnight = end_minutes <= start_minutes
    if is_overnight:
        end_date = business_date + timedelta(days=1)
    end_at = datetime.combine(
        end_date,
        dt_time(hour=end_minutes // 60, minute=end_minutes % 60),
        tzinfo=KST,
    )
    return ScheduleWindow(
        business_date=business_date,
        schedule_id=str(row.get("id") or ""),
        shift_type=shift_type,
        site_id=str(row.get("site_id") or ""),
        site_code=str(row.get("site_code") or ""),
        start_at=start_at,
        end_at=end_at,
        is_overnight=is_overnight,
    )


def schedule_window_to_dict(window: ScheduleWindow | None) -> dict[str, Any]:
    if not window:
        return {}
    return {
        "business_date": window.business_date.isoformat(),
        "schedule_id": window.schedule_id or None,
        "shift_type": window.shift_type,
        "shift_start_at": window.start_at.astimezone(timezone.utc),
        "shift_end_at": window.end_at.astimezone(timezone.utc),
        "is_overnight": window.is_overnight,
    }


def _is_work_window(window: ScheduleWindow) -> bool:
    return window.shift_type not in {"off", "holiday"}


def select_checkin_window(
    windows: list[ScheduleWindow],
    event_at: datetime,
) -> ScheduleWindow | None:
    event_kst = ensure_kst(event_at)
    work_windows = [window for window in windows if _is_work_window(window)]
    if not work_windows:
        return None

    upcoming = [
        window
        for window in work_windows
        if window.normal_check_in_start_at <= event_kst < window.start_at
    ]
    if upcoming:
        return min(upcoming, key=lambda item: item.start_at)

    active = [
        window for window in work_windows if window.start_at <= event_kst <= window.end_at
    ]
    if active:
        return max(active, key=lambda item: item.start_at)

    same_day_future = [
        window
        for window in work_windows
        if window.business_date == event_kst.date() and event_kst < window.start_at
    ]
    if same_day_future:
        return min(same_day_future, key=lambda item: item.start_at)

    same_business_day = [
        window
        for window in work_windows
        if window.business_date == event_kst.date() and event_kst >= window.start_at
    ]
    if same_business_day:
        return max(same_business_day, key=lambda item: item.start_at)

    candidates = [
        window
        for window in work_windows
        if window.start_at - timedelta(hours=12) <= event_kst <= window.end_at + MISSED_CHECKOUT_GRACE
    ]
    if candidates:
        return min(candidates, key=lambda item: abs((item.start_at - event_kst).total_seconds()))
    return None


def select_open_session(sessions: list[dict[str, Any]], now_utc: datetime | None = None) -> dict[str, Any] | None:
    now_kst = ensure_kst(now_utc)
    open_sessions = [
        session
        for session in sessions
        if session.get("check_in_at") and not session.get("check_out_at")
    ]
    if not open_sessions:
        return None

    def is_actionable(session: dict[str, Any]) -> bool:
        window = session.get("window")
        if isinstance(window, ScheduleWindow):
            if window.is_overnight:
                return True
            return now_kst.date() <= window.business_date
        business_date = session.get("business_date")
        if isinstance(business_date, date):
            return now_kst.date() <= business_date
        return True

    actionable = [session for session in open_sessions if is_actionable(session)]
    if actionable:
        return max(actionable, key=lambda item: item.get("check_in_at"))
    return None


def derive_session_status(
    *,
    window: ScheduleWindow | None,
    check_in_at: datetime | None = None,
    check_out_at: datetime | None = None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now_kst = ensure_kst(now_utc)
    check_in_kst = ensure_kst(check_in_at) if check_in_at else None
    check_out_kst = ensure_kst(check_out_at) if check_out_at else None

    if window is None:
        return {
            "session_status": "unscheduled",
            "check_in_status": "normal_check_in" if check_in_at else "",
            "check_out_status": "normal_checkout" if check_out_at else "",
            "worked_minutes": None,
        }

    if not _is_work_window(window):
        return {
            "session_status": "scheduled_off",
            "check_in_status": "",
            "check_out_status": "",
            "worked_minutes": 0,
        }

    check_in_status = ""
    check_out_status = ""
    session_status = "not_started"
    worked_minutes = None

    if check_in_kst:
        check_in_status = (
            "late_check_in" if check_in_kst > window.start_at else "normal_check_in"
        )
        session_status = "working"
    elif now_kst > window.start_at:
        check_in_status = "missing_check_in"
        session_status = "missing_check_in"

    if check_in_kst and check_out_kst:
        check_out_status = (
            "delayed_checkout"
            if check_out_kst > window.missed_checkout_at
            else "normal_checkout"
        )
        session_status = (
            "delayed_checkout"
            if check_out_status == "delayed_checkout"
            else (
                "late_check_in"
                if check_in_status == "late_check_in"
                else "normal_checkout"
            )
        )
        effective_start = max(check_in_kst, window.start_at)
        effective_end = min(check_out_kst, window.end_at)
        worked_minutes = int(max(0, (effective_end - effective_start).total_seconds() // 60))
    elif check_in_kst and now_kst > window.missed_checkout_at:
        check_out_status = "missing_checkout"
        session_status = "missing_checkout"

    return {
        "session_status": session_status,
        "check_in_status": check_in_status,
        "check_out_status": check_out_status,
        "worked_minutes": worked_minutes,
    }


def build_sessions(
    windows: list[ScheduleWindow],
    attendance_rows: list[dict[str, Any]],
    *,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    sorted_rows = sorted(
        [dict(row) for row in attendance_rows],
        key=lambda row: ensure_utc(row.get("event_at")),
    )
    sessions: list[dict[str, Any]] = []
    open_session: dict[str, Any] | None = None

    for row in sorted_rows:
        event_type = str(row.get("event_type") or "").strip()
        event_at = ensure_utc(row.get("event_at"))
        if event_type == "check_in":
            if open_session and not open_session.get("check_out_at"):
                sessions.append(open_session)
            window = select_checkin_window(windows, event_at)
            open_session = {
                "business_date": window.business_date if window else ensure_kst(event_at).date(),
                "window": window,
                "check_in_at": event_at,
                "check_in_id": row.get("id"),
                "check_out_at": None,
                "check_out_id": None,
                "site_id": row.get("site_id") or (window.site_id if window else None),
                "site_code": row.get("site_code") or (window.site_code if window else None),
                "site_name": row.get("site_name"),
                "auto_checkout": False,
            }
            continue
        if event_type != "check_out":
            continue
        if open_session and not open_session.get("check_out_at"):
            open_session["check_out_at"] = event_at
            open_session["check_out_id"] = row.get("id")
            open_session["auto_checkout"] = bool(row.get("auto_checkout"))
            sessions.append(open_session)
            open_session = None
            continue
        sessions.append(
            {
                "business_date": ensure_kst(event_at).date(),
                "window": None,
                "check_in_at": None,
                "check_in_id": None,
                "check_out_at": event_at,
                "check_out_id": row.get("id"),
                "site_id": row.get("site_id"),
                "site_code": row.get("site_code"),
                "site_name": row.get("site_name"),
                "auto_checkout": bool(row.get("auto_checkout")),
            }
        )

    if open_session:
        sessions.append(open_session)

    result: list[dict[str, Any]] = []
    for session in sessions:
        window = session.get("window") if isinstance(session.get("window"), ScheduleWindow) else None
        status_payload = derive_session_status(
            window=window,
            check_in_at=session.get("check_in_at"),
            check_out_at=session.get("check_out_at"),
            now_utc=now_utc,
        )
        result.append({**session, **status_payload})
    return result


def summarize_window(
    window: ScheduleWindow,
    sessions: list[dict[str, Any]],
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    matching = [
        session
        for session in sessions
        if session.get("business_date") == window.business_date
        and (
            session.get("window") == window
            or not session.get("window")
            or str(getattr(session.get("window"), "schedule_id", "")) == window.schedule_id
        )
    ]
    session = matching[-1] if matching else None
    status_payload = derive_session_status(
        window=window,
        check_in_at=session.get("check_in_at") if session else None,
        check_out_at=session.get("check_out_at") if session else None,
        now_utc=now_utc,
    )
    return {
        **schedule_window_to_dict(window),
        "date": window.business_date.isoformat(),
        "check_in_count": 1 if session and session.get("check_in_at") else 0,
        "check_out_count": 1 if session and session.get("check_out_at") else 0,
        "check_in_at": session.get("check_in_at") if session else None,
        "check_out_at": session.get("check_out_at") if session else None,
        "today_record_id": (session.get("check_out_id") or session.get("check_in_id")) if session else None,
        "auto_checkout": bool(session.get("auto_checkout")) if session else None,
        **status_payload,
    }


def build_off_summary(business_date: date) -> dict[str, Any]:
    return {
        "date": business_date.isoformat(),
        "business_date": business_date.isoformat(),
        "schedule_id": None,
        "shift_type": "off",
        "shift_start_at": None,
        "shift_end_at": None,
        "check_in_count": 0,
        "check_out_count": 0,
        "session_status": "scheduled_off",
        "check_in_status": "",
        "check_out_status": "",
        "worked_minutes": 0,
    }


def fetch_schedule_windows(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_date: date,
    end_date: date,
) -> list[ScheduleWindow]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ms.id,
                ms.tenant_id,
                ms.employee_id,
                ms.site_id,
                ms.schedule_date,
                ms.shift_type,
                ms.shift_start_time,
                ms.shift_end_time,
                ms.paid_hours,
                s.site_code,
                s.site_name,
                st.start_time AS template_start_time,
                st.end_time AS template_end_time,
                st.paid_hours AS template_paid_hours,
                st.duty_type
            FROM monthly_schedules ms
            LEFT JOIN schedule_templates st ON st.id = ms.template_id
            LEFT JOIN sites s ON s.id = ms.site_id
            WHERE ms.tenant_id = %s
              AND ms.employee_id = %s
              AND ms.schedule_date >= %s
              AND ms.schedule_date <= %s
            ORDER BY ms.schedule_date ASC, ms.shift_start_time ASC NULLS LAST, ms.shift_type ASC
            """,
            (tenant_id, employee_id, start_date, end_date),
        )
        rows = cur.fetchall() or []
    windows = [build_schedule_window(dict(row)) for row in rows]
    return [window for window in windows if window is not None]


def fetch_attendance_rows(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_at_utc: datetime,
    end_at_utc: datetime,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                ar.id,
                ar.site_id,
                ar.event_type,
                ar.event_at,
                COALESCE(ar.auto_checkout, FALSE) AS auto_checkout,
                COALESCE(ar.auto_checkout_reason, '') AS auto_checkout_reason,
                s.site_code,
                s.site_name
            FROM attendance_records ar
            LEFT JOIN sites s ON s.id = ar.site_id
            WHERE ar.tenant_id = %s
              AND ar.employee_id = %s
              AND ar.event_at >= %s
              AND ar.event_at < %s
              AND ar.event_type IN ('check_in', 'check_out')
            ORDER BY ar.event_at ASC
            """,
            (tenant_id, employee_id, start_at_utc, end_at_utc),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def get_fetch_range_for_windows(
    windows: list[ScheduleWindow],
    start_date: date,
    end_date: date,
) -> tuple[datetime, datetime]:
    if windows:
        start_kst = min(window.start_at for window in windows) - timedelta(hours=12)
        end_kst = max(window.end_at for window in windows) + timedelta(hours=12)
    else:
        start_kst = datetime.combine(start_date, dt_time.min, tzinfo=KST)
        end_kst = datetime.combine(end_date + timedelta(days=1), dt_time.min, tzinfo=KST)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def _iter_dates(start_date: date, end_date: date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def load_context(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_date: date,
    end_date: date,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    windows = fetch_schedule_windows(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
    )
    start_at_utc, end_at_utc = get_fetch_range_for_windows(
        windows,
        start_date,
        end_date,
    )
    rows = fetch_attendance_rows(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_at_utc=start_at_utc,
        end_at_utc=end_at_utc,
    )
    sessions = build_sessions(windows, rows, now_utc=now_utc)
    return {"windows": windows, "attendance_rows": rows, "sessions": sessions}


def resolve_event_context(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    event_at: datetime,
) -> dict[str, Any]:
    event_kst = ensure_kst(event_at)
    context = load_context(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=event_kst.date() - timedelta(days=1),
        end_date=event_kst.date() + timedelta(days=1),
        now_utc=event_at,
    )
    return {
        **context,
        "checkin_window": select_checkin_window(context["windows"], event_at),
        "open_session": select_open_session(context["sessions"], now_utc=event_at),
    }


def session_matches_window(session: dict[str, Any], window: ScheduleWindow | None) -> bool:
    if not window:
        return False
    session_window = session.get("window")
    if isinstance(session_window, ScheduleWindow):
        if session_window.schedule_id and window.schedule_id:
            return session_window.schedule_id == window.schedule_id
        return (
            session_window.business_date == window.business_date
            and session_window.shift_type == window.shift_type
        )
    return session.get("business_date") == window.business_date


def find_existing_checkin_session(
    sessions: list[dict[str, Any]],
    window: ScheduleWindow | None,
    event_at: datetime,
) -> dict[str, Any] | None:
    if window:
        candidates = [
            session
            for session in sessions
            if session_matches_window(session, window) and session.get("check_in_at")
        ]
        return candidates[-1] if candidates else None
    event_date = ensure_kst(event_at).date()
    candidates = [
        session
        for session in sessions
        if session.get("business_date") == event_date
        and not session.get("window")
        and session.get("check_in_at")
    ]
    return candidates[-1] if candidates else None


def resolve_home_status(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    now_utc = ensure_utc(now_utc)
    now_kst = ensure_kst(now_utc)
    context = load_context(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=now_kst.date() - timedelta(days=1),
        end_date=now_kst.date() + timedelta(days=1),
        now_utc=now_utc,
    )
    sessions = context["sessions"]
    open_session = select_open_session(sessions, now_utc=now_utc)
    if open_session:
        window = open_session.get("window") if isinstance(open_session.get("window"), ScheduleWindow) else None
        payload = {
            **schedule_window_to_dict(window),
            **open_session,
            "status": "WORKING",
            "button_mode": "check_out",
            "button_label": "퇴근하기"
            if open_session.get("session_status") != "missing_checkout"
            else "퇴근지연",
            "today_record_id": open_session.get("check_in_id"),
            "open_session": True,
        }
        return _public_payload(payload)

    checkin_window = select_checkin_window(context["windows"], now_utc)
    if checkin_window:
        summary = summarize_window(checkin_window, sessions, now_utc=now_utc)
        has_checkin = bool(summary.get("check_in_count"))
        has_checkout = bool(summary.get("check_out_count"))
        status = "DONE" if has_checkin and has_checkout else "NONE"
        button_mode = "done" if status == "DONE" else "check_in"
        return _public_payload(
            {
                **summary,
                "status": status,
                "button_mode": button_mode,
                "button_label": "퇴근완료" if button_mode == "done" else "출근하기",
                "open_session": False,
            }
        )

    return {
        "status": "NONE",
        "button_mode": "check_in",
        "button_label": "출근하기",
        "session_status": "scheduled_off",
        "check_in_status": "",
        "check_out_status": "",
        "worked_minutes": 0,
        "open_session": False,
        "business_date": now_kst.date().isoformat(),
        "shift_type": "off",
    }


def build_weekly_summary(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_date: date,
    end_date: date,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    context = load_context(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        now_utc=now_utc,
    )
    windows_by_date: dict[date, list[ScheduleWindow]] = {}
    for window in context["windows"]:
        windows_by_date.setdefault(window.business_date, []).append(window)

    entries: list[dict[str, Any]] = []
    for current in _iter_dates(start_date, end_date):
        windows = windows_by_date.get(current, [])
        work_windows = [window for window in windows if _is_work_window(window)]
        if not windows:
            entries.append(build_off_summary(current))
            continue
        if not work_windows:
            entries.append(
                {
                    **build_off_summary(current),
                    "schedule_id": windows[0].schedule_id or None,
                    "shift_type": windows[0].shift_type,
                }
            )
            continue
        summaries = [
            summarize_window(window, context["sessions"], now_utc=now_utc)
            for window in work_windows
        ]
        primary = summaries[0]
        primary["check_in_count"] = sum(int(item.get("check_in_count") or 0) for item in summaries)
        primary["check_out_count"] = sum(int(item.get("check_out_count") or 0) for item in summaries)
        primary["worked_minutes"] = sum(
            int(item.get("worked_minutes") or 0) for item in summaries if item.get("worked_minutes") is not None
        )
        entries.append(_public_payload(primary))
    return entries


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    result = dict(payload)
    window = result.pop("window", None)
    if isinstance(window, ScheduleWindow):
        result.update(schedule_window_to_dict(window))
    business_date = result.get("business_date")
    if isinstance(business_date, date):
        result["business_date"] = business_date.isoformat()
    for key in ["shift_start_at", "shift_end_at", "check_in_at", "check_out_at"]:
        if isinstance(result.get(key), datetime):
            result[key] = result[key].astimezone(timezone.utc)
    result["open_session"] = bool(result.get("open_session"))
    return result
