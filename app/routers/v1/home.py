from __future__ import annotations

from datetime import date as dt_date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import (
    HomeAttendanceTrendPointOut,
    HomeBriefingListRowOut,
    HomeBriefingOpsSummaryOut,
    HomeBriefingOut,
    HomeBriefingPersonalSummaryOut,
    HomeBriefingRequestSummaryOut,
    HomeBriefingSiteReadinessOut,
    HomeBriefingSiteSummaryOut,
    HomeBriefingWeekSummaryOut,
    HomeDataSourceRegisterItemOut,
    HomeLeaveBalanceSummaryOut,
    HomeMissingStaffOut,
    HomeNextShiftOut,
    HomeNoticeHighlightOut,
    HomeSiteAttendanceOut,
    HomeSupportWorkSummaryOut,
    HomeTaskSummaryOut,
    HomeTeamAttendanceBreakdownOut,
    HomeWeekDayOut,
    HomeWorkTimeSummaryOut,
)
from ...services.leave_ledger import calculate_leave_duration_days
from ...services.attendance_runtime import fetch_today_status, get_kst_day_bounds_utc
from ...utils.schema_introspection import table_column_exists
from ...utils.permissions import (
    ROLE_DEVELOPER,
    ROLE_HQ_ADMIN,
    ROLE_OFFICER,
    ROLE_SUPERVISOR,
    ROLE_VICE_SUPERVISOR,
    normalize_user_role,
)
from ...utils.tenant_context import resolve_scoped_tenant
from .notices import _fetch_notice_rows, _map_notice_summary

router = APIRouter(prefix="/home", tags=["home"], dependencies=[Depends(apply_rate_limit)])
KST = timezone(timedelta(hours=9))
NON_WORK_SHIFT_TYPES = ("off", "holiday", "annual_leave", "half_day_leave", "half_leave", "leave")
SHIFT_LABELS = {
    "day": "주간근무",
    "overtime": "초과근무",
    "night": "야간근무",
    "off": "휴무",
    "holiday": "공휴일",
    "annual_leave": "연차",
    "half_day_leave": "반차",
    "half_leave": "반차",
}


def _table_exists(conn, table_name: str) -> bool:
    if not hasattr(conn, "cursor"):
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = %s
            ) AS exists
            """,
            (table_name,),
        )
        row = cur.fetchone() or {}
    return bool(row.get("exists"))


def _table_column_exists(conn, table_name: str, column_name: str) -> bool:
    if not hasattr(conn, "cursor"):
        return False
    return table_column_exists(conn, table_name, column_name)


def _resolve_home_audience(user: dict[str, Any]) -> str:
    role = normalize_user_role(user.get("role"))
    if role in {ROLE_DEVELOPER, ROLE_HQ_ADMIN}:
        return "hq"
    if role == ROLE_SUPERVISOR:
        return "supervisor"
    return "officer"


def _role_label(user: dict[str, Any]) -> str:
    role = normalize_user_role(user.get("role"))
    if role == ROLE_DEVELOPER:
        return "Developer"
    if role == ROLE_HQ_ADMIN:
        return "HQ Admin"
    if role == ROLE_SUPERVISOR:
        return "Supervisor"
    if role == ROLE_VICE_SUPERVISOR:
        return "Vice Supervisor"
    return "Officer"


def _today_context() -> tuple[datetime, datetime, dt_date]:
    now_utc = datetime.now(timezone.utc)
    start_utc, end_utc, today_kst = get_kst_day_bounds_utc(now_utc)
    return start_utc, end_utc, today_kst


def _week_bounds(today_kst: dt_date) -> tuple[dt_date, dt_date]:
    start = today_kst - timedelta(days=today_kst.weekday())
    return start, start + timedelta(days=6)


def _normalize_site_label(site_row: dict[str, Any] | None) -> str:
    if not isinstance(site_row, dict):
        return "본인 범위"
    site_name = str(site_row.get("site_name") or "").strip()
    site_code = str(site_row.get("site_code") or "").strip().upper()
    if site_name and site_code:
        return f"{site_name} ({site_code})"
    return site_name or site_code or "본인 범위"


def _lookup_site_row(conn, *, site_id: str | None = None, site_code: str | None = None, tenant_id: str) -> dict[str, Any] | None:
    if not site_id and not site_code:
        return None
    clauses: list[str] = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if site_id:
        clauses.append("id = %s")
        params.append(site_id)
    else:
        clauses.append("upper(trim(site_code)) = upper(trim(%s))")
        params.append(site_code)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, site_code, site_name
            FROM sites
            WHERE {" AND ".join(clauses)}
            LIMIT 1
            """,
            tuple(params),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_notice_summaries(conn, *, tenant_id: str, limit: int = 4) -> list:
    rows = _fetch_notice_rows(conn, tenant_id=tenant_id, limit=limit)
    return [_map_notice_summary(row) for row in rows]


def _pct(part: int | float, total: int | float) -> int:
    total_number = float(total or 0)
    if total_number <= 0:
        return 0
    return max(0, min(100, int(round((float(part or 0) / total_number) * 100))))


def _weekday_label(value: dt_date | str | None) -> str:
    if isinstance(value, str):
        try:
            parsed = dt_date.fromisoformat(value[:10])
        except ValueError:
            return ""
        value = parsed
    if not isinstance(value, dt_date):
        return ""
    return ["월", "화", "수", "목", "금", "토", "일"][value.weekday()]


def _compact_date_label(value: dt_date | str | None) -> str:
    if isinstance(value, str):
        try:
            value = dt_date.fromisoformat(value[:10])
        except ValueError:
            return str(value or "")
    if not isinstance(value, dt_date):
        return ""
    return f"{value.month:02d}.{value.day:02d}"


def _clean_notice_summary(text: object, *, fallback: str = "") -> str:
    raw = str(text or fallback or "").strip()
    if not raw:
        return ""
    cleaned = " ".join(raw.replace("\r", " ").replace("\n", " ").split())
    for delimiter in ("。", ".", "!", "?", "다."):
        index = cleaned.find(delimiter)
        if index >= 16:
            end = index + len(delimiter)
            return cleaned[:end].strip()
    return cleaned[:96].strip()


def _build_notice_highlight(notice_rows: list[Any]) -> HomeNoticeHighlightOut | None:
    if not notice_rows:
        return None
    row = notice_rows[0]
    title = str(getattr(row, "title", "") or "").strip()
    body_preview = str(getattr(row, "body_preview", "") or "").strip()
    published_at = getattr(row, "published_at", None)
    date_label = _compact_date_label(published_at.date() if isinstance(published_at, datetime) else None)
    return HomeNoticeHighlightOut(
        notice_id=getattr(row, "id", None),
        title=title,
        summary=_clean_notice_summary(body_preview, fallback=title),
        category=getattr(row, "category", None),
        date_label=date_label or None,
        published_at=published_at if isinstance(published_at, datetime) else None,
        is_pinned=bool(getattr(row, "is_pinned", False)),
    )


def _home_data_source_register(audience: str) -> list[HomeDataSourceRegisterItemOut]:
    rows = [
        ("notice_highlight", "aggregate-only", "notices", "latest notice title and one-line summary"),
        ("personal_summary", "aggregate-only", "attendance home status + user/site", "own work status"),
        ("work_time_summary", "aggregate-only", "attendance sessions + monthly_schedules", "bounded day/week work minutes"),
        ("next_shift", "aggregate-only", "monthly_schedules", "next scheduled work row"),
        ("attendance_trend", "aggregate-only", "monthly_schedules + attendance_records + late_shift_log", "7-day bounded trend"),
        ("site_attendance_rows", "aggregate-only", "monthly_schedules + attendance_records", "today per-site attendance"),
        ("support_work_summary", "aggregate-only", "sentrix_support_request_tickets + support_assignment", "support-work request/assignment summary"),
        ("team_attendance_breakdown", "aggregate-only", "site-scoped schedule/attendance snapshot", "supervisor and vice summary"),
        ("missing_staff_rows", "aggregate-only", "employees + schedules + attendance", "avatar initials fallback only"),
        ("leave_balance", "aggregate-only", "leave_grants/leave_requests read-only aggregate", "no home-owned leave storage"),
        ("geofence_permission", "client-runtime", "browser geolocation permission + sites radius", "computed on client"),
    ]
    if audience == "hq":
        rows.append(("task_summary", "aggregate-only", "requests + schedules/support sources", "HQ core status quadrant"))
    return [
        HomeDataSourceRegisterItemOut(
            field=field,
            source_type=source_type,
            source=source,
            notes=notes,
        )
        for field, source_type, source, notes in rows
    ]


def _count_unread_notifications(conn, *, tenant_id: str, user_id: str) -> int:
    if not _table_exists(conn, "in_app_notifications"):
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM in_app_notifications
            WHERE tenant_id = %s
              AND user_id = %s
              AND read_at IS NULL
            """,
            (tenant_id, user_id),
        )
        row = cur.fetchone() or {}
    return max(int(row.get("cnt") or 0), 0)


def _build_request_summary(
    conn,
    *,
    tenant_id: str,
    user_id: str | None = None,
    employee_id: str | None = None,
) -> HomeBriefingRequestSummaryOut:
    leave_pending_count = 0
    attendance_pending_count = 0
    correction_pending_count = 0
    unread_count = _count_unread_notifications(conn, tenant_id=tenant_id, user_id=user_id or "") if user_id else 0

    if _table_exists(conn, "leave_requests"):
        with conn.cursor() as cur:
            if employee_id:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM leave_requests
                    WHERE tenant_id = %s
                      AND employee_id = %s
                      AND lower(COALESCE(status, '')) = 'pending'
                    """,
                    (tenant_id, employee_id),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM leave_requests
                    WHERE tenant_id = %s
                      AND lower(COALESCE(status, '')) = 'pending'
                    """,
                    (tenant_id,),
                )
            leave_pending_count = max(int((cur.fetchone() or {}).get("cnt") or 0), 0)

    if _table_exists(conn, "attendance_requests"):
        with conn.cursor() as cur:
            if employee_id:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM attendance_requests
                    WHERE tenant_id = %s
                      AND employee_id = %s
                      AND lower(COALESCE(status, '')) = 'pending'
                    """,
                    (tenant_id, employee_id),
                )
            else:
                cur.execute(
                    """
                    SELECT COUNT(*) AS cnt
                    FROM attendance_requests
                    WHERE tenant_id = %s
                      AND lower(COALESCE(status, '')) = 'pending'
                    """,
                    (tenant_id,),
                )
            attendance_pending_count = max(int((cur.fetchone() or {}).get("cnt") or 0), 0)

    return HomeBriefingRequestSummaryOut(
        total_pending_count=leave_pending_count + attendance_pending_count + correction_pending_count,
        leave_pending_count=leave_pending_count,
        attendance_pending_count=attendance_pending_count,
        correction_pending_count=correction_pending_count,
        unread_count=unread_count,
    )


def _fetch_next_shift_label(conn, *, tenant_id: str, employee_id: str, today_kst: dt_date) -> str | None:
    if not _table_exists(conn, "monthly_schedules"):
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schedule_date,
                   lower(COALESCE(shift_type, '')) AS shift_type
            FROM monthly_schedules
            WHERE tenant_id = %s
              AND employee_id = %s
              AND schedule_date >= %s
            ORDER BY schedule_date ASC
            LIMIT 1
            """,
            (tenant_id, employee_id, today_kst),
        )
        row = cur.fetchone() or {}
    shift_type = str(row.get("shift_type") or "").strip().lower()
    schedule_date = row.get("schedule_date")
    if not shift_type or not isinstance(schedule_date, dt_date):
        return None
    return f"{schedule_date.isoformat()} · {SHIFT_LABELS.get(shift_type, shift_type or '스케줄')}"


def _build_personal_summary(
    conn,
    *,
    user: dict[str, Any],
    today_kst: dt_date,
    request_summary: HomeBriefingRequestSummaryOut,
) -> HomeBriefingPersonalSummaryOut | None:
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        return None
    home_status = (
        fetch_today_status(conn, tenant_id=str(user["tenant_id"]), employee_id=employee_id)
        if hasattr(conn, "cursor")
        else {}
    ) or {}
    fallback_site = _lookup_site_row(
        conn,
        site_id=str(user.get("site_id") or "").strip() or None,
        site_code=str(user.get("site_code") or "").strip() or None,
        tenant_id=str(user["tenant_id"]),
    )
    site_code = str(home_status.get("site_code") or user.get("site_code") or (fallback_site or {}).get("site_code") or "").strip().upper() or None
    site_name = str(home_status.get("site_name") or (fallback_site or {}).get("site_name") or "").strip() or None
    return HomeBriefingPersonalSummaryOut(
        employee_name=str(user.get("full_name") or user.get("username") or "").strip() or None,
        site_code=site_code,
        site_name=site_name,
        today_status=str(home_status.get("status") or "NONE").strip().upper() or "NONE",
        button_mode=str(home_status.get("button_mode") or "").strip().lower() or None,
        check_in_at=home_status.get("check_in_at"),
        check_out_at=home_status.get("check_out_at"),
        auto_checkout=bool(home_status.get("auto_checkout")),
        next_shift_label=_fetch_next_shift_label(
            conn,
            tenant_id=str(user["tenant_id"]),
            employee_id=employee_id,
            today_kst=today_kst,
        ),
        pending_leave_count=request_summary.leave_pending_count,
        pending_attendance_count=request_summary.attendance_pending_count,
        unread_count=request_summary.unread_count,
    )


def _build_week_summary(conn, *, tenant_id: str, employee_id: str, today_kst: dt_date) -> HomeBriefingWeekSummaryOut:
    week_start, week_end = _week_bounds(today_kst)
    scheduled_days: set[dt_date] = set()
    off_days: set[dt_date] = set()
    worked_days: set[dt_date] = set()

    if _table_exists(conn, "monthly_schedules"):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT schedule_date,
                       lower(COALESCE(shift_type, '')) AS shift_type
                FROM monthly_schedules
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND schedule_date >= %s
                  AND schedule_date <= %s
                """,
                (tenant_id, employee_id, week_start, week_end),
            )
            for row in cur.fetchall() or []:
                schedule_date = row.get("schedule_date")
                shift_type = str(row.get("shift_type") or "").strip().lower()
                if not isinstance(schedule_date, dt_date):
                    continue
                if shift_type in NON_WORK_SHIFT_TYPES:
                    off_days.add(schedule_date)
                else:
                    scheduled_days.add(schedule_date)

    start_utc, _ = _kst_day_bounds_for_date(week_start)
    _, end_utc = _kst_day_bounds_for_date(week_end)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT (event_at AT TIME ZONE 'Asia/Seoul')::date AS work_date
            FROM attendance_records
            WHERE tenant_id = %s
              AND employee_id = %s
              AND event_type = 'check_in'
              AND event_at >= %s
              AND event_at < %s
            """,
            (tenant_id, employee_id, start_utc, end_utc),
        )
        for row in cur.fetchall() or []:
            work_date = row.get("work_date")
            if isinstance(work_date, dt_date):
                worked_days.add(work_date)

    return HomeBriefingWeekSummaryOut(
        start_date=week_start.isoformat(),
        end_date=week_end.isoformat(),
        scheduled_days=len(scheduled_days),
        worked_days=len(worked_days),
        off_days=len(off_days),
    )


def _shift_expected_minutes(row: dict[str, Any] | None) -> int:
    if not isinstance(row, dict):
        return 0
    start_value = row.get("shift_start_time") or row.get("template_start_time")
    end_value = row.get("shift_end_time") or row.get("template_end_time")
    if not start_value or not end_value:
        shift_type = str(row.get("shift_type") or "").strip().lower()
        return 480 if shift_type not in NON_WORK_SHIFT_TYPES else 0
    try:
        start_parts = [int(part) for part in str(start_value).split(":")[:2]]
        end_parts = [int(part) for part in str(end_value).split(":")[:2]]
        start_minutes = start_parts[0] * 60 + start_parts[1]
        end_minutes = end_parts[0] * 60 + end_parts[1]
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60
        return max(end_minutes - start_minutes, 0)
    except (ValueError, IndexError):
        return 480


def _format_time_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if ":" in text:
        parts = text.split(":")
        return ":".join(parts[:2])
    return text


def _fetch_schedule_rows_for_employee(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_date: dt_date,
    end_date: dt_date,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "monthly_schedules"):
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.schedule_date,
                   lower(COALESCE(ms.shift_type, 'day')) AS shift_type,
                   ms.shift_start_time,
                   ms.shift_end_time,
                   ms.paid_hours,
                   s.site_code,
                   s.site_name,
                   st.start_time AS template_start_time,
                   st.end_time AS template_end_time,
                   st.paid_hours AS template_paid_hours
            FROM monthly_schedules ms
            LEFT JOIN sites s ON s.id = ms.site_id
            LEFT JOIN schedule_templates st ON st.id = ms.template_id
            WHERE ms.tenant_id = %s
              AND ms.employee_id = %s
              AND ms.schedule_date >= %s
              AND ms.schedule_date <= %s
            ORDER BY ms.schedule_date ASC, ms.shift_start_time ASC NULLS LAST, ms.shift_type ASC
            """,
            (tenant_id, employee_id, start_date, end_date),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_attendance_bounds_by_date(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    start_date: dt_date,
    end_date: dt_date,
) -> dict[dt_date, dict[str, Any]]:
    if not hasattr(conn, "cursor"):
        return {}
    start_utc, _ = _kst_day_bounds_for_date(start_date)
    _, end_utc = _kst_day_bounds_for_date(end_date)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT (event_at AT TIME ZONE 'Asia/Seoul')::date AS work_date,
                   MIN(event_at) FILTER (WHERE event_type = 'check_in') AS check_in_at,
                   MAX(event_at) FILTER (WHERE event_type = 'check_out') AS check_out_at
            FROM attendance_records
            WHERE tenant_id = %s
              AND employee_id = %s
              AND event_at >= %s
              AND event_at < %s
            GROUP BY 1
            """,
            (tenant_id, employee_id, start_utc, end_utc),
        )
        rows = cur.fetchall() or []
    return {row["work_date"]: dict(row) for row in rows if isinstance(row.get("work_date"), dt_date)}


def _build_work_time_summary(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    today_kst: dt_date,
    home_status: dict[str, Any] | None,
) -> HomeWorkTimeSummaryOut:
    week_start, week_end = _week_bounds(today_kst)
    schedules = _fetch_schedule_rows_for_employee(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=week_start,
        end_date=week_end,
    )
    schedule_by_date: dict[dt_date, dict[str, Any]] = {}
    for row in schedules:
        schedule_date = row.get("schedule_date")
        if isinstance(schedule_date, dt_date) and schedule_date not in schedule_by_date:
            schedule_by_date[schedule_date] = row
    attendance_by_date = _fetch_attendance_bounds_by_date(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=week_start,
        end_date=week_end,
    )
    week_target = sum(_shift_expected_minutes(row) for row in schedule_by_date.values())
    week_worked = 0
    for row in attendance_by_date.values():
        check_in = row.get("check_in_at")
        check_out = row.get("check_out_at")
        if isinstance(check_in, datetime) and isinstance(check_out, datetime) and check_out > check_in:
            week_worked += int((check_out - check_in).total_seconds() // 60)
    today_worked = max(int((home_status or {}).get("worked_minutes") or 0), 0)
    today_expected = _shift_expected_minutes(schedule_by_date.get(today_kst))
    if today_worked <= 0:
        today_row = attendance_by_date.get(today_kst) or {}
        check_in = today_row.get("check_in_at")
        check_out = today_row.get("check_out_at")
        if isinstance(check_in, datetime):
            end = check_out if isinstance(check_out, datetime) else datetime.now(timezone.utc)
            if end > check_in:
                today_worked = int((end - check_in).total_seconds() // 60)
    return HomeWorkTimeSummaryOut(
        today_worked_minutes=today_worked,
        today_expected_minutes=today_expected,
        week_worked_minutes=week_worked,
        week_target_minutes=week_target,
        today_progress_percent=_pct(today_worked, today_expected),
        week_progress_percent=_pct(week_worked, week_target),
    )


def _build_next_shift(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    today_kst: dt_date,
) -> HomeNextShiftOut | None:
    rows = _fetch_schedule_rows_for_employee(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=today_kst,
        end_date=today_kst + timedelta(days=45),
    )
    for row in rows:
        shift_type = str(row.get("shift_type") or "").strip().lower()
        if shift_type in NON_WORK_SHIFT_TYPES:
            continue
        schedule_date = row.get("schedule_date")
        if not isinstance(schedule_date, dt_date):
            continue
        start_time = _format_time_value(row.get("shift_start_time") or row.get("template_start_time"))
        end_time = _format_time_value(row.get("shift_end_time") or row.get("template_end_time"))
        label = f"{schedule_date.isoformat()} · {row.get('site_name') or row.get('site_code') or SHIFT_LABELS.get(shift_type, shift_type or '근무')}"
        return HomeNextShiftOut(
            date=schedule_date.isoformat(),
            weekday=_weekday_label(schedule_date),
            site_code=str(row.get("site_code") or "").strip().upper() or None,
            site_name=str(row.get("site_name") or "").strip() or None,
            shift_type=shift_type or None,
            start_time=start_time,
            end_time=end_time,
            label=label,
        )
    return None


def _build_week_rows(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    today_kst: dt_date,
) -> list[HomeWeekDayOut]:
    week_start, week_end = _week_bounds(today_kst)
    schedules = _fetch_schedule_rows_for_employee(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=week_start,
        end_date=week_end,
    )
    schedule_by_date: dict[dt_date, dict[str, Any]] = {}
    for row in schedules:
        schedule_date = row.get("schedule_date")
        if isinstance(schedule_date, dt_date) and schedule_date not in schedule_by_date:
            schedule_by_date[schedule_date] = row
    attendance_by_date = _fetch_attendance_bounds_by_date(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        start_date=week_start,
        end_date=week_end,
    )
    rows: list[HomeWeekDayOut] = []
    cursor = week_start
    while cursor <= week_end:
        schedule = schedule_by_date.get(cursor) or {}
        attendance = attendance_by_date.get(cursor) or {}
        shift_type = str(schedule.get("shift_type") or "").strip().lower()
        check_in = attendance.get("check_in_at")
        check_out = attendance.get("check_out_at")
        worked_minutes = 0
        if isinstance(check_in, datetime) and isinstance(check_out, datetime) and check_out > check_in:
            worked_minutes = int((check_out - check_in).total_seconds() // 60)
        if shift_type in NON_WORK_SHIFT_TYPES:
            status_label = "휴무"
        elif check_in:
            status_label = "근무"
        elif schedule:
            status_label = "예정"
        else:
            status_label = "-"
        rows.append(
            HomeWeekDayOut(
                date=cursor.isoformat(),
                weekday=_weekday_label(cursor),
                work_status=status_label,
                check_in=_format_time_value(check_in.astimezone(KST).time()) if isinstance(check_in, datetime) else None,
                check_out=_format_time_value(check_out.astimezone(KST).time()) if isinstance(check_out, datetime) else None,
                worked_minutes=worked_minutes,
                shift_type=shift_type or None,
                site_name=str(schedule.get("site_name") or "").strip() or None,
            )
        )
        cursor += timedelta(days=1)
    return rows


def _kst_day_bounds_for_date(target_date: dt_date) -> tuple[datetime, datetime]:
    start_kst = datetime.combine(target_date, datetime.min.time(), tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def _fetch_today_staff_snapshot(
    conn,
    *,
    tenant_id: str,
    target_date: dt_date,
    day_start_utc: datetime,
    day_end_utc: datetime,
    site_id: str | None = None,
) -> list[dict[str, Any]]:
    if not _table_exists(conn, "monthly_schedules"):
        return []
    params: list[Any] = [tenant_id, target_date, list(NON_WORK_SHIFT_TYPES)]
    site_clause = ""
    if site_id:
        site_clause = "AND ms.site_id = %s"
        params.append(site_id)
    phone_expr = "COALESCE(e.phone, '')" if _table_column_exists(conn, "employees", "phone") else "''"
    photo_expr = "COALESCE(e.photo_attachment_id, '')" if _table_column_exists(conn, "employees", "photo_attachment_id") else "''"
    role_expr = "COALESCE(e.duty_role, e.role, '')" if _table_column_exists(conn, "employees", "duty_role") and _table_column_exists(conn, "employees", "role") else ("COALESCE(e.duty_role, '')" if _table_column_exists(conn, "employees", "duty_role") else ("COALESCE(e.role, '')" if _table_column_exists(conn, "employees", "role") else "''"))
    params.extend(
        [
            tenant_id,
            day_start_utc,
            day_end_utc,
            tenant_id,
            target_date,
            target_date,
            tenant_id,
            target_date,
            target_date,
            tenant_id,
            target_date,
        ]
    )
    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH scheduled AS (
                SELECT DISTINCT ON (ms.employee_id)
                       ms.employee_id,
                       ms.site_id,
                       lower(COALESCE(ms.shift_type, 'day')) AS shift_type
                FROM monthly_schedules ms
                WHERE ms.tenant_id = %s
                  AND ms.schedule_date = %s
                  AND NOT (lower(COALESCE(ms.shift_type, '')) = ANY(%s))
                  {site_clause}
                ORDER BY ms.employee_id,
                         CASE lower(COALESCE(ms.shift_type, ''))
                           WHEN 'day' THEN 1
                           WHEN 'overtime' THEN 2
                           WHEN 'night' THEN 3
                           ELSE 9
                         END ASC
            )
            SELECT e.id AS employee_id,
                   e.employee_code,
                   COALESCE(NULLIF(trim(e.full_name), ''), e.employee_code) AS employee_name,
                   {phone_expr} AS phone,
                   {photo_expr} AS photo_attachment_id,
                   {role_expr} AS role_label,
                   COALESCE(s.site_code, '') AS site_code,
                   COALESCE(s.site_name, '') AS site_name,
                   scheduled.shift_type,
                   EXISTS (
                       SELECT 1
                       FROM attendance_records ar
                       WHERE ar.tenant_id = %s
                         AND ar.employee_id = scheduled.employee_id
                         AND ar.event_type = 'check_in'
                         AND ar.event_at >= %s
                         AND ar.event_at < %s
                   ) AS has_check_in,
                   EXISTS (
                       SELECT 1
                       FROM leave_requests lr
                       WHERE lr.tenant_id = %s
                         AND lr.employee_id = scheduled.employee_id
                         AND lower(COALESCE(lr.status, '')) = 'approved'
                         AND lr.start_at::date <= %s
                         AND lr.end_at::date >= %s
                   ) AS approved_leave,
                   EXISTS (
                       SELECT 1
                       FROM leave_requests lr
                       WHERE lr.tenant_id = %s
                         AND lr.employee_id = scheduled.employee_id
                         AND lower(COALESCE(lr.status, '')) = 'pending'
                         AND lr.start_at::date <= %s
                         AND lr.end_at::date >= %s
                   ) AS pending_leave,
                   EXISTS (
                       SELECT 1
                       FROM attendance_requests arq
                       WHERE arq.tenant_id = %s
                         AND arq.employee_id = scheduled.employee_id
                         AND lower(COALESCE(arq.status, '')) = 'pending'
                         AND (arq.requested_at AT TIME ZONE 'Asia/Seoul')::date = %s
                   ) AS pending_attendance
            FROM scheduled
            JOIN employees e ON e.id = scheduled.employee_id
            LEFT JOIN sites s ON s.id = scheduled.site_id
            ORDER BY s.site_name ASC, employee_name ASC
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    return [dict(row) for row in rows]


def _fetch_assignment_flags(conn, *, tenant_id: str, target_date: dt_date, site_id: str | None = None) -> dict[str, int]:
    if not _table_exists(conn, "monthly_schedules"):
        return {"site_count": 0, "closer_missing_count": 0, "leader_missing_count": 0}
    params: list[Any] = [tenant_id, target_date, list(NON_WORK_SHIFT_TYPES)]
    site_clause = ""
    if site_id:
        site_clause = "AND ms.site_id = %s"
        params.append(site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT ms.site_id) AS site_count,
                   COUNT(DISTINCT ms.site_id) FILTER (
                     WHERE lower(COALESCE(ms.schedule_note, '')) LIKE '%%closer%%'
                        OR lower(COALESCE(ms.shift_type, '')) IN ('close', 'closing')
                   ) AS closer_site_count,
                   COUNT(DISTINCT ms.site_id) FILTER (
                     WHERE ms.leader_user_id IS NOT NULL
                   ) AS leader_site_count
            FROM monthly_schedules ms
            WHERE ms.tenant_id = %s
              AND ms.schedule_date = %s
              AND NOT (lower(COALESCE(ms.shift_type, '')) = ANY(%s))
              {site_clause}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
    site_count = max(int(row.get("site_count") or 0), 0)
    closer_count = max(int(row.get("closer_site_count") or 0), 0)
    leader_count = max(int(row.get("leader_site_count") or 0), 0)
    return {
        "site_count": site_count,
        "closer_missing_count": max(site_count - closer_count, 0),
        "leader_missing_count": max(site_count - leader_count, 0),
    }


def _count_late_shifts(
    conn,
    *,
    tenant_id: str,
    target_date: dt_date,
    site_id: str | None = None,
) -> int:
    if not _table_exists(conn, "late_shift_log"):
        return 0
    params: list[Any] = [tenant_id, target_date]
    site_clause = ""
    if site_id:
        site_clause = "AND site_id = %s"
        params.append(site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT employee_id) AS cnt
            FROM late_shift_log
            WHERE tenant_id = %s
              AND work_date = %s
              {site_clause}
            """,
            tuple(params),
        )
        row = cur.fetchone() or {}
    return max(int(row.get("cnt") or 0), 0)


def _build_attendance_trend(
    conn,
    *,
    tenant_id: str,
    end_date: dt_date,
    site_id: str | None = None,
    days: int = 7,
) -> list[HomeAttendanceTrendPointOut]:
    rows: list[HomeAttendanceTrendPointOut] = []
    start_date = end_date - timedelta(days=max(days, 1) - 1)
    cursor = start_date
    while cursor <= end_date:
        start_utc, end_utc = _kst_day_bounds_for_date(cursor)
        snapshot = _fetch_today_staff_snapshot(
            conn,
            tenant_id=tenant_id,
            target_date=cursor,
            day_start_utc=start_utc,
            day_end_utc=end_utc,
            site_id=site_id,
        )
        completed = sum(1 for row in snapshot if row.get("has_check_in"))
        missing = sum(1 for row in snapshot if not row.get("has_check_in") and not row.get("approved_leave"))
        rows.append(
            HomeAttendanceTrendPointOut(
                date=cursor.isoformat(),
                label=f"{cursor.month:02d}.{cursor.day:02d} ({_weekday_label(cursor)})",
                completed=completed,
                missing=missing,
                late=_count_late_shifts(conn, tenant_id=tenant_id, target_date=cursor, site_id=site_id),
            )
        )
        cursor += timedelta(days=1)
    return rows


def _build_site_attendance_rows(
    snapshot: list[dict[str, Any]],
    *,
    late_by_site: dict[str, int] | None = None,
) -> list[HomeSiteAttendanceOut]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in snapshot:
        site_code = str(row.get("site_code") or "").strip().upper() or "-"
        site_name = str(row.get("site_name") or site_code).strip() or site_code
        if site_code not in grouped:
            grouped[site_code] = {
                "site_code": site_code if site_code != "-" else None,
                "site_name": site_name,
                "scheduled": 0,
                "present": 0,
                "missing": 0,
            }
        grouped[site_code]["scheduled"] += 1
        if row.get("has_check_in"):
            grouped[site_code]["present"] += 1
        elif not row.get("approved_leave"):
            grouped[site_code]["missing"] += 1
    result: list[HomeSiteAttendanceOut] = []
    for site_code, item in grouped.items():
        late_count = max(int((late_by_site or {}).get(site_code) or 0), 0)
        scheduled = int(item["scheduled"])
        present = int(item["present"])
        result.append(
            HomeSiteAttendanceOut(
                site_code=item.get("site_code"),
                site_name=item.get("site_name"),
                scheduled=scheduled,
                present=present,
                missing=int(item["missing"]),
                late=late_count,
                attendance_rate=_pct(present, scheduled),
            )
        )
    return sorted(result, key=lambda row: row.attendance_rate, reverse=True)[:8]


def _fetch_late_counts_by_site(conn, *, tenant_id: str, target_date: dt_date) -> dict[str, int]:
    if not _table_exists(conn, "late_shift_log"):
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(s.site_code, '') AS site_code,
                   COUNT(DISTINCT lsl.employee_id) AS cnt
            FROM late_shift_log lsl
            LEFT JOIN sites s ON s.id = lsl.site_id
            WHERE lsl.tenant_id = %s
              AND lsl.work_date = %s
            GROUP BY 1
            """,
            (tenant_id, target_date),
        )
        rows = cur.fetchall() or []
    return {
        str(row.get("site_code") or "").strip().upper() or "-": max(int(row.get("cnt") or 0), 0)
        for row in rows
    }


def _build_team_breakdown(
    snapshot: list[dict[str, Any]],
    *,
    late_count: int = 0,
) -> HomeTeamAttendanceBreakdownOut:
    total = len(snapshot)
    missing = sum(1 for row in snapshot if not row.get("has_check_in") and not row.get("approved_leave"))
    other = sum(1 for row in snapshot if row.get("approved_leave"))
    normal = max(sum(1 for row in snapshot if row.get("has_check_in")) - late_count, 0)
    return HomeTeamAttendanceBreakdownOut(
        total=total,
        normal=normal,
        late=max(late_count, 0),
        early=0,
        missing=missing,
        other=other,
        normal_rate=_pct(normal, total),
        late_rate=_pct(late_count, total),
        early_rate=0,
        missing_rate=_pct(missing, total),
    )


def _initials(name: str) -> str:
    compact = "".join(str(name or "").split())
    if not compact:
        return ""
    return compact[-2:] if len(compact) >= 2 else compact


def _build_missing_staff_rows(snapshot: list[dict[str, Any]]) -> list[HomeMissingStaffOut]:
    rows: list[HomeMissingStaffOut] = []
    for row in snapshot:
        if row.get("has_check_in") or row.get("approved_leave"):
            continue
        name = str(row.get("employee_name") or row.get("employee_code") or "직원").strip()
        rows.append(
            HomeMissingStaffOut(
                employee_id=row.get("employee_id"),
                employee_code=str(row.get("employee_code") or "").strip() or None,
                employee_name=name,
                role_label=str(row.get("role_label") or row.get("duty_role") or "").strip() or None,
                site_code=str(row.get("site_code") or "").strip().upper() or None,
                site_name=str(row.get("site_name") or "").strip() or None,
                phone=str(row.get("phone") or "").strip() or None,
                avatar_initials=_initials(name),
                photo_attachment_id=str(row.get("photo_attachment_id") or "").strip() or None,
            )
        )
    return rows[:8]


def _build_support_work_summary(
    conn,
    *,
    tenant_id: str,
    today_kst: dt_date,
    site_id: str | None = None,
) -> HomeSupportWorkSummaryOut:
    month_key = today_kst.strftime("%Y-%m")
    requested = 0
    cancelled = 0
    if _table_exists(conn, "sentrix_support_request_tickets"):
        params: list[Any] = [tenant_id, month_key]
        site_clause = ""
        if site_id:
            site_clause = "AND site_id = %s"
            params.append(site_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COALESCE(SUM(request_count) FILTER (WHERE status = 'active'), 0) AS requested,
                       COALESCE(SUM(request_count) FILTER (WHERE status = 'retracted'), 0) AS cancelled
                FROM sentrix_support_request_tickets
                WHERE tenant_id = %s
                  AND month_key = %s
                  {site_clause}
                """,
                tuple(params),
            )
            row = cur.fetchone() or {}
        requested = max(int(row.get("requested") or 0), 0)
        cancelled = max(int(row.get("cancelled") or 0), 0)
    assigned = 0
    confirmed = 0
    if _table_exists(conn, "support_assignment"):
        start_date = today_kst.replace(day=1)
        end_date = (start_date + timedelta(days=40)).replace(day=1) - timedelta(days=1)
        params = [tenant_id, start_date, end_date]
        site_clause = ""
        if site_id:
            site_clause = "AND site_id = %s"
            params.append(site_id)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS assigned,
                       COUNT(*) FILTER (WHERE upper(COALESCE(worker_type, '')) <> 'UNAVAILABLE') AS confirmed
                FROM support_assignment
                WHERE tenant_id = %s
                  AND work_date >= %s
                  AND work_date <= %s
                  {site_clause}
                """,
                tuple(params),
            )
            row = cur.fetchone() or {}
        assigned = max(int(row.get("assigned") or 0), 0)
        confirmed = max(int(row.get("confirmed") or 0), 0)
    return HomeSupportWorkSummaryOut(
        requested=requested,
        assigned=assigned,
        confirmed=confirmed,
        cancelled=cancelled,
        total=max(requested, assigned, confirmed) + cancelled,
        source_label="support roundtrip",
    )


def _leave_days_from_requests(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    year: int,
    status: str = "approved",
) -> float:
    if not _table_exists(conn, "leave_requests"):
        return 0.0
    start = dt_date(year, 1, 1)
    end = dt_date(year, 12, 31)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT leave_type, start_at, end_at, half_day_slot
            FROM leave_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND lower(COALESCE(status, '')) = %s
              AND start_at <= %s
              AND end_at >= %s
            """,
            (tenant_id, employee_id, status, end, start),
        )
        rows = cur.fetchall() or []
    total = 0.0
    for row in rows:
        total += float(calculate_leave_duration_days(row.get("start_at"), row.get("end_at"), row.get("half_day_slot")))
    return round(total, 2)


def _build_leave_balance_summary(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    today_kst: dt_date,
    pending_count: int,
) -> HomeLeaveBalanceSummaryOut:
    used_days = _leave_days_from_requests(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        year=today_kst.year,
        status="approved",
    )
    granted_days: float | None = None
    if _table_exists(conn, "leave_grants"):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(SUM(granted_days), 0) AS granted
                FROM leave_grants
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND effective_from <= %s
                  AND (effective_to IS NULL OR effective_to >= %s)
                """,
                (tenant_id, employee_id, today_kst, today_kst),
            )
            row = cur.fetchone() or {}
        granted_days = float(row.get("granted") or 0)
    return HomeLeaveBalanceSummaryOut(
        remaining_days=(round(max(granted_days - used_days, 0), 2) if granted_days is not None else None),
        used_days=used_days,
        total_days=(round(granted_days, 2) if granted_days is not None else None),
        pending_count=max(int(pending_count or 0), 0),
        source_label="leave grants" if granted_days is not None else "leave requests aggregate",
        source_available=granted_days is not None,
    )


def _build_attention_rows(snapshot: list[dict[str, Any]], *, include_names: bool) -> list[HomeBriefingListRowOut]:
    rows: list[HomeBriefingListRowOut] = []
    for row in snapshot:
        employee_name = str(row.get("employee_name") or row.get("employee_code") or "직원").strip()
        site_label = str(row.get("site_name") or row.get("site_code") or "").strip()
        if row.get("pending_attendance") or row.get("pending_leave"):
            rows.append(
                HomeBriefingListRowOut(
                    title=employee_name if include_names else "출퇴근/휴가 요청 대기",
                    subtitle=f"{site_label} · 승인이 필요합니다." if include_names else "승인이 필요한 요청이 남아 있습니다.",
                    value=str(row.get("site_code") or "").strip().upper() or None,
                    pill_label="요청 대기",
                    pill_tone="warn",
                )
            )
            continue
        if not row.get("has_check_in") and not row.get("approved_leave"):
            rows.append(
                HomeBriefingListRowOut(
                    title=employee_name if include_names else "출근 누락",
                    subtitle=f"{site_label} · 오늘 출근 기록이 없습니다." if include_names else "근무 시작 확인이 필요합니다.",
                    value=str(row.get("site_code") or "").strip().upper() or None,
                    pill_label="출근 누락",
                    pill_tone="error",
                )
            )
    return rows[:6]


def _fetch_hq_org_issue_rows(conn, *, tenant_id: str) -> list[HomeBriefingListRowOut]:
    employee_total = 0
    unassigned_employee_count = 0
    unlinked_count = 0
    inactive_site_count = 0
    if _table_exists(conn, "employees"):
        employee_deleted_clause = (
            "AND COALESCE(e.is_deleted, FALSE) = FALSE"
            if _table_column_exists(conn, "employees", "is_deleted")
            else ""
        )
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) AS employee_total,
                       COUNT(*) FILTER (WHERE e.site_id IS NULL) AS unassigned_employee_count,
                       COUNT(*) FILTER (
                           WHERE NOT EXISTS (
                               SELECT 1
                               FROM arls_users au
                               WHERE au.tenant_id = e.tenant_id
                                 AND au.employee_id = e.id
                                 AND COALESCE(au.is_active, TRUE) = TRUE
                                 AND COALESCE(au.is_deleted, FALSE) = FALSE
                           )
                       ) AS unlinked_count
                FROM employees e
                WHERE e.tenant_id = %s
                  {employee_deleted_clause}
                """,
                (tenant_id,),
            )
            row = cur.fetchone() or {}
        employee_total = max(int(row.get("employee_total") or 0), 0)
        unassigned_employee_count = max(int(row.get("unassigned_employee_count") or 0), 0)
        unlinked_count = max(int(row.get("unlinked_count") or 0), 0)

    if _table_exists(conn, "sites"):
        site_active_expr = "TRUE" if not _table_column_exists(conn, "sites", "is_active") else "COALESCE(is_active, TRUE)"
        site_deleted_expr = "FALSE" if not _table_column_exists(conn, "sites", "is_deleted") else "COALESCE(is_deleted, FALSE)"
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT COUNT(*) FILTER (
                         WHERE {site_active_expr} = FALSE
                            OR {site_deleted_expr} = TRUE
                       ) AS inactive_site_count
                FROM sites
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
            inactive_site_count = max(int((cur.fetchone() or {}).get("inactive_site_count") or 0), 0)

    rows: list[HomeBriefingListRowOut] = [
        HomeBriefingListRowOut(
            title="미연동 직원",
            subtitle="계정 연결이 되지 않은 직원이 남아 있습니다.",
            value=f"{unlinked_count}명",
            pill_label="조직 점검",
            pill_tone="warn" if unlinked_count > 0 else "neutral",
        ),
        HomeBriefingListRowOut(
            title="미배치 직원",
            subtitle="지점이 비어 있는 직원을 확인하세요.",
            value=f"{unassigned_employee_count}명",
            pill_label="배치 확인",
            pill_tone="warn" if unassigned_employee_count > 0 else "neutral",
        ),
        HomeBriefingListRowOut(
            title="비활성 지점",
            subtitle=f"현재 등록 직원 {employee_total}명 기준 teaser 입니다.",
            value=f"{inactive_site_count}곳",
            pill_label="지점 상태",
            pill_tone="neutral" if inactive_site_count == 0 else "warn",
        ),
    ]
    return rows


@router.get("/briefing", response_model=HomeBriefingOut)
def get_home_briefing(
    defer_hq_heavy: bool = False,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_id = str(target_tenant.get("id") or "").strip()
    audience = _resolve_home_audience(user)
    role_label = _role_label(user)
    _, _, today_kst = _today_context()
    if audience == "hq" and defer_hq_heavy:
        request_summary = HomeBriefingRequestSummaryOut()
        return HomeBriefingOut(
            audience=audience,
            date=today_kst.isoformat(),
            role_label=role_label,
            scope_label="전체 운영 범위",
            request_summary=request_summary,
            approval_summary=request_summary,
        )

    day_start_utc, day_end_utc = _kst_day_bounds_for_date(today_kst)
    own_site = _lookup_site_row(
        conn,
        site_id=str(user.get("site_id") or "").strip() or None,
        site_code=str(user.get("site_code") or "").strip() or None,
        tenant_id=tenant_id,
    )
    notice_rows = _fetch_notice_summaries(conn, tenant_id=tenant_id, limit=4)
    own_employee_id = str(user.get("employee_id") or "").strip()
    request_summary_employee_id = own_employee_id if audience == "officer" else None
    request_summary = _build_request_summary(
        conn,
        tenant_id=tenant_id,
        user_id=str(user.get("id") or "").strip() or None,
        employee_id=request_summary_employee_id,
    )

    payload = HomeBriefingOut(
        audience=audience,
        date=today_kst.isoformat(),
        role_label=role_label,
        scope_label="전체 운영 범위" if audience == "hq" else _normalize_site_label(own_site),
        notice_rows=notice_rows,
        request_summary=request_summary,
        notice_highlight=_build_notice_highlight(notice_rows),
        data_source_register=_home_data_source_register(audience),
    )
    payload.support_work_summary = _build_support_work_summary(
        conn,
        tenant_id=tenant_id,
        today_kst=today_kst,
    )
    payload.task_summary = HomeTaskSummaryOut(
        approval_pending=request_summary.total_pending_count,
        leave_request=request_summary.leave_pending_count,
        schedule_change_request=0,
        support_work_request=payload.support_work_summary.requested if payload.support_work_summary else 0,
    )

    if audience == "hq":
        payload.approval_summary = request_summary
        if defer_hq_heavy:
            return payload

        personal_summary = _build_personal_summary(
            conn,
            user=user,
            today_kst=today_kst,
            request_summary=_build_request_summary(
                conn,
                tenant_id=tenant_id,
                user_id=str(user.get("id") or "").strip() or None,
                employee_id=own_employee_id or None,
            ),
        )
        if personal_summary is not None:
            payload.personal_summary = personal_summary
            home_status = (
                fetch_today_status(conn, tenant_id=tenant_id, employee_id=own_employee_id)
                if own_employee_id and hasattr(conn, "cursor")
                else {}
            )
            payload.work_time_summary = _build_work_time_summary(
                conn,
                tenant_id=tenant_id,
                employee_id=own_employee_id,
                today_kst=today_kst,
                home_status=home_status,
            )
            payload.next_shift = _build_next_shift(
                conn,
                tenant_id=tenant_id,
                employee_id=own_employee_id,
                today_kst=today_kst,
            )

        snapshot = _fetch_today_staff_snapshot(
            conn,
            tenant_id=tenant_id,
            target_date=today_kst,
            day_start_utc=day_start_utc,
            day_end_utc=day_end_utc,
        )
        scheduled_count = len(snapshot)
        present_count = sum(1 for row in snapshot if row.get("has_check_in"))
        missing_count = sum(1 for row in snapshot if not row.get("has_check_in") and not row.get("approved_leave"))
        vacancy_site_count = len(
            {
                str(row.get("site_code") or "").strip().upper()
                for row in snapshot
                if not row.get("has_check_in") and not row.get("approved_leave")
            }
            - {""}
        )
        assignment_flags = _fetch_assignment_flags(conn, tenant_id=tenant_id, target_date=today_kst)
        payload.ops_summary = HomeBriefingOpsSummaryOut(
            attendance_rate=int(round((present_count / scheduled_count) * 100)) if scheduled_count > 0 else 0,
            scheduled_count=scheduled_count,
            present_count=present_count,
            missing_count=missing_count,
            issue_count=missing_count + request_summary.total_pending_count,
            pending_approval_count=request_summary.total_pending_count,
            vacancy_site_count=vacancy_site_count,
            site_count=assignment_flags["site_count"],
        )
        payload.attendance_trend = _build_attendance_trend(
            conn,
            tenant_id=tenant_id,
            end_date=today_kst,
        )
        payload.site_attendance_rows = _build_site_attendance_rows(
            snapshot,
            late_by_site=_fetch_late_counts_by_site(conn, tenant_id=tenant_id, target_date=today_kst),
        )
        payload.attendance_issue_rows = _build_attention_rows(snapshot, include_names=True)
        payload.schedule_risk_rows = [
            HomeBriefingListRowOut(
                title="배정 누락",
                subtitle=f"결원 지점 {vacancy_site_count}곳 · 즉시 확인이 필요합니다.",
                value=f"{missing_count}건",
                pill_label="확인 필요",
                pill_tone="warn" if missing_count == 0 else "error",
            ),
            HomeBriefingListRowOut(
                title="마감자 지정",
                subtitle="오늘 마감자 지정 상태입니다.",
                value=f"{assignment_flags['closer_missing_count']}곳",
                pill_label="미지정" if assignment_flags["closer_missing_count"] > 0 else "정상",
                pill_tone="warn" if assignment_flags["closer_missing_count"] > 0 else "success",
            ),
            HomeBriefingListRowOut(
                title="리더 지정",
                subtitle="오늘 리더 지정 상태입니다.",
                value=f"{assignment_flags['leader_missing_count']}곳",
                pill_label="미지정" if assignment_flags["leader_missing_count"] > 0 else "정상",
                pill_tone="warn" if assignment_flags["leader_missing_count"] > 0 else "success",
            ),
        ]
        payload.org_issue_rows = _fetch_hq_org_issue_rows(conn, tenant_id=tenant_id)
        return payload

    own_site_id = str((own_site or {}).get("id") or "").strip()
    site_snapshot = _fetch_today_staff_snapshot(
        conn,
        tenant_id=tenant_id,
        target_date=today_kst,
        day_start_utc=day_start_utc,
        day_end_utc=day_end_utc,
        site_id=own_site_id or None,
    )
    site_scheduled_count = len(site_snapshot)
    site_present_count = sum(1 for row in site_snapshot if row.get("has_check_in"))
    site_missing_count = sum(1 for row in site_snapshot if not row.get("has_check_in") and not row.get("approved_leave"))
    site_pending_request_count = sum(1 for row in site_snapshot if row.get("pending_attendance") or row.get("pending_leave"))
    site_leave_or_night_count = sum(
        1 for row in site_snapshot if row.get("approved_leave") or str(row.get("shift_type") or "").strip().lower() == "night"
    )
    site_assignment_flags = _fetch_assignment_flags(
        conn,
        tenant_id=tenant_id,
        target_date=today_kst,
        site_id=own_site_id or None,
    )
    personal_summary = _build_personal_summary(conn, user=user, today_kst=today_kst, request_summary=request_summary)
    if personal_summary is not None:
        payload.personal_summary = personal_summary
    if own_employee_id:
        home_status = (
            fetch_today_status(conn, tenant_id=tenant_id, employee_id=own_employee_id)
            if hasattr(conn, "cursor")
            else {}
        ) or {}
        payload.work_time_summary = _build_work_time_summary(
            conn,
            tenant_id=tenant_id,
            employee_id=own_employee_id,
            today_kst=today_kst,
            home_status=home_status,
        )
        payload.next_shift = _build_next_shift(
            conn,
            tenant_id=tenant_id,
            employee_id=own_employee_id,
            today_kst=today_kst,
        )
        payload.week_rows = _build_week_rows(
            conn,
            tenant_id=tenant_id,
            employee_id=own_employee_id,
            today_kst=today_kst,
        )
        payload.leave_balance = _build_leave_balance_summary(
            conn,
            tenant_id=tenant_id,
            employee_id=own_employee_id,
            today_kst=today_kst,
            pending_count=request_summary.leave_pending_count,
        )

    if audience == "supervisor":
        payload.scope_label = f"{_normalize_site_label(own_site)} · 지점 운영 범위"
        payload.site_summary = HomeBriefingSiteSummaryOut(
            site_code=str((own_site or {}).get("site_code") or "").strip().upper() or None,
            site_name=str((own_site or {}).get("site_name") or "").strip() or None,
            scheduled_count=site_scheduled_count,
            present_count=site_present_count,
            missing_count=site_missing_count,
            pending_request_count=site_pending_request_count,
            leave_or_night_count=site_leave_or_night_count,
            schedule_gap_count=site_missing_count + site_assignment_flags["closer_missing_count"] + site_assignment_flags["leader_missing_count"],
        )
        payload.team_attendance_breakdown = _build_team_breakdown(
            site_snapshot,
            late_count=_count_late_shifts(conn, tenant_id=tenant_id, target_date=today_kst, site_id=own_site_id or None),
        )
        payload.team_trend = _build_attendance_trend(
            conn,
            tenant_id=tenant_id,
            end_date=today_kst,
            site_id=own_site_id or None,
        )
        payload.missing_staff_rows = _build_missing_staff_rows(site_snapshot)
        payload.support_work_summary = _build_support_work_summary(
            conn,
            tenant_id=tenant_id,
            today_kst=today_kst,
            site_id=own_site_id or None,
        )
        payload.team_attention_rows = _build_attention_rows(site_snapshot, include_names=True)
        return payload

    payload.scope_label = "본인 근무 기준"
    employee_id = str(user.get("employee_id") or "").strip()
    if employee_id:
        payload.week_summary = _build_week_summary(conn, tenant_id=tenant_id, employee_id=employee_id, today_kst=today_kst)
    return payload
