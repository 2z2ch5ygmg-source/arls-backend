from __future__ import annotations

from datetime import date as dt_date, datetime, time as dt_time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ...deps import get_db_conn, get_current_user, apply_rate_limit, get_idempotency_key
from ...schemas import (
    AttendanceCreate,
    AttendanceOut,
    AttendanceRecordUpsertOut,
    AttendanceTodayStatusOut,
)
from ...services.attendance_sessions import (
    build_sessions,
    build_weekly_summary as build_attendance_weekly_summary,
    ensure_kst,
    fetch_schedule_windows,
    find_existing_checkin_session,
    resolve_event_context,
)
from ...services.attendance_runtime import (
    fetch_today_status,
    get_kst_day_bounds_utc,
)
from ...services.closing_overtime import apply_closing_overtime_from_checkout
from ...services.p1_schedule import upsert_pending_apple_daytime_ot_from_checkout
from ...services.push_notifications import send_attendance_push_notification
from ...utils.geo import haversine_meters
from ...utils.permissions import can_post_attendance, is_super_admin

router = APIRouter(prefix="/attendance", tags=["attendance"], dependencies=[Depends(apply_rate_limit)])
KST = timezone(timedelta(hours=9))


def _parse_iso_date(value: str, *, field_name: str) -> dt_date:
    normalized = str(value or "").strip()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} is required")
    try:
        return dt_date.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field_name} must be YYYY-MM-DD",
        ) from exc


def _kst_day_bounds_for_date(target_date: dt_date) -> tuple[datetime, datetime]:
    start_kst = datetime.combine(target_date, dt_time.min, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def _resolve_week_range(
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[dt_date, dt_date]:
    _, _, today_kst = get_kst_day_bounds_utc(datetime.now(timezone.utc))
    resolved_start = _parse_iso_date(start_date, field_name="start_date") if start_date else (today_kst - timedelta(days=today_kst.weekday()))
    resolved_end = _parse_iso_date(end_date, field_name="end_date") if end_date else (resolved_start + timedelta(days=6))
    if resolved_end < resolved_start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_date must be on or after start_date")
    if (resolved_end - resolved_start).days > 31:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="date range must be 31 days or less")
    return resolved_start, resolved_end


def _tenant_employee(conn, tenant_id: str, tenant_code: str, employee_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.site_id
            FROM employees e
            JOIN tenants t ON t.id = e.tenant_id
            WHERE e.tenant_id = %s
              AND upper(trim(t.tenant_code)) = upper(trim(%s))
              AND e.employee_code = %s
            """,
            (tenant_id, tenant_code, employee_code),
        )
        row = cur.fetchone()
    return row


def _site_for_company(conn, tenant_id: str, site_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site_name, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s AND site_code = %s
            """,
            (tenant_id, site_code),
        )
        return cur.fetchone()


def _ensure_utc(value: datetime | None) -> datetime:
    if not isinstance(value, datetime):
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _attendance_row_to_out(row: dict[str, Any]) -> AttendanceOut:
    return AttendanceOut(
        id=row["id"],
        employee_code=row["employee_code"],
        event_type=row["event_type"],
        event_at=row["event_at"],
        site_name=row["site_name"],
        distance_meters=float(row.get("distance_meters") or 0),
        is_within_radius=bool(row.get("is_within_radius")),
        auto_checkout=bool(row.get("auto_checkout")),
    )


def _build_home_status_out(user: dict[str, Any], status_row: dict[str, Any] | None) -> AttendanceTodayStatusOut:
    row = status_row if isinstance(status_row, dict) else {}
    status_code = str(row.get("status") or "NONE").strip().upper() or "NONE"
    button_mode = str(row.get("button_mode") or "").strip().lower()
    if button_mode not in {"check_in", "check_out", "done"}:
        button_mode = "check_out" if status_code == "WORKING" else ("done" if status_code == "DONE" else "check_in")
    return AttendanceTodayStatusOut(
        status=status_code,
        check_in_at=row.get("check_in_at"),
        check_out_at=row.get("check_out_at"),
        today_record_id=row.get("today_record_id"),
        button_mode=button_mode,
        button_label=row.get("button_label"),
        auto_checkout=row.get("auto_checkout"),
        site_id=row.get("site_id"),
        site_code=row.get("site_code"),
        site_name=row.get("site_name"),
        employee_id=user.get("employee_id"),
        employee_name=user.get("full_name"),
        business_date=row.get("business_date"),
        schedule_id=row.get("schedule_id"),
        shift_type=row.get("shift_type"),
        shift_start_at=row.get("shift_start_at"),
        shift_end_at=row.get("shift_end_at"),
        session_status=row.get("session_status"),
        check_in_status=row.get("check_in_status"),
        check_out_status=row.get("check_out_status"),
        worked_minutes=row.get("worked_minutes"),
        open_session=bool(row.get("open_session")),
    )


def _resolve_attendance_home_status(conn, user: dict[str, Any]) -> AttendanceTodayStatusOut:
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        return AttendanceTodayStatusOut(
            status="NONE",
            today_record_id=None,
            button_mode="check_in",
            site_id=None,
            site_code=None,
            site_name=None,
            employee_id=None,
            employee_name=None,
        )
    status_row = fetch_today_status(
        conn,
        tenant_id=str(user["tenant_id"]),
        employee_id=employee_id,
    )
    return _build_home_status_out(user, status_row)


def _fetch_record_out_by_id(conn, record_id: str) -> AttendanceOut:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id, ar.employee_id, ar.event_type, ar.event_at, s.site_name,
                   ar.distance_meters, ar.is_within_radius, e.employee_code,
                   COALESCE(ar.auto_checkout, FALSE) AS auto_checkout
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            WHERE ar.id = %s
            """,
            (record_id,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="attendance record not found")
    return _attendance_row_to_out(dict(row))


@router.post("/records", response_model=AttendanceRecordUpsertOut)
def create_record(
    payload: AttendanceCreate,
    idempotency_key=Depends(get_idempotency_key),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_post_attendance(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    requested_tenant_code = str(payload.tenant_code or "").strip().upper()
    actor_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    if requested_tenant_code != actor_tenant_code and not is_super_admin(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")

    emp = _tenant_employee(conn, user["tenant_id"], requested_tenant_code, payload.employee_code)
    if not emp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="employee not found")

    site = _site_for_company(conn, user["tenant_id"], payload.site_code)
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

    distance = haversine_meters(
        float(payload.latitude),
        float(payload.longitude),
        float(site["latitude"]),
        float(site["longitude"]),
    )
    within = distance <= float(site["radius_meters"])
    event_at_utc = _ensure_utc(payload.event_at)
    event_context = resolve_event_context(
        conn,
        tenant_id=str(user["tenant_id"]),
        employee_id=str(emp["id"]),
        event_at=event_at_utc,
    )

    with conn.cursor() as cur:
        if payload.event_type == "check_in":
            existing_session = find_existing_checkin_session(
                event_context["sessions"],
                event_context["checkin_window"],
                event_at_utc,
            )
            if existing_session and existing_session.get("check_in_id"):
                existing_out = _fetch_record_out_by_id(conn, str(existing_session["check_in_id"]))
                return AttendanceRecordUpsertOut(record=existing_out, already_exists=True)
        if payload.event_type == "check_out":
            open_session = event_context.get("open_session")
            if not open_session or not open_session.get("check_in_id"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="check_in required before check_out",
                )
            if open_session.get("check_out_id"):
                existing_out = _fetch_record_out_by_id(conn, str(open_session["check_out_id"]))
                return AttendanceRecordUpsertOut(record=existing_out, already_exists=True)
        # 신규 출퇴근 기록은 지점 반경 내에서만 허용한다.
        if not within:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="outside allowed attendance radius",
            )

        cur.execute(
            """
            INSERT INTO attendance_records (
              tenant_id, employee_id, site_id, event_type, event_at,
              latitude, longitude, distance_meters, is_within_radius, auto_checkout
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE)
            ON CONFLICT (tenant_id, employee_id, event_type, event_at)
            DO NOTHING
            RETURNING id, event_at
            """,
            (
                user["tenant_id"],
                emp["id"],
                site["id"],
                payload.event_type,
                event_at_utc,
                payload.latitude,
                payload.longitude,
                distance,
                within,
            ),
        )
        inserted = cur.fetchone()
        if not inserted:
            cur.execute(
                """
                SELECT id
                FROM attendance_records
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND event_type = %s
                  AND event_at = %s
                LIMIT 1
                """,
                (
                    user["tenant_id"],
                    emp["id"],
                    payload.event_type,
                    event_at_utc,
                ),
            )
            fallback_row = cur.fetchone()
            if fallback_row:
                existing_out = _fetch_record_out_by_id(conn, str(fallback_row["id"]))
                return AttendanceRecordUpsertOut(record=existing_out, already_exists=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="attendance insert failed")

        if payload.event_type == "check_out":
            apply_closing_overtime_from_checkout(
                conn,
                tenant_id=user["tenant_id"],
                site_id=site["id"],
                employee_id=emp["id"],
                checkout_at=event_at_utc,
                source_event_uid=f"attendance_record:{inserted['id']}",
                source_label="ATTENDANCE_RECORD",
            )
            upsert_pending_apple_daytime_ot_from_checkout(
                conn,
                tenant_id=user["tenant_id"],
                site_id=site["id"],
                checkout_at=event_at_utc,
                fallback_user_id=user.get("id"),
                source_event_uid=f"attendance_record:{inserted['id']}",
            )
    inserted_out = _fetch_record_out_by_id(conn, str(inserted["id"]))
    try:
        send_attendance_push_notification(
            conn,
            tenant_id=str(user["tenant_id"]),
            site_id=str(site["id"] or ""),
            site_name=str(site.get("site_name") or payload.site_code or ""),
            employee_id=str(emp["id"]),
            employee_name=str(user.get("full_name") or payload.employee_code or ""),
            event_type=payload.event_type,
            event_at_iso=str(inserted_out.event_at.isoformat() if inserted_out.event_at else event_at_utc.isoformat()),
            auto_checkout=False,
        )
    except Exception:
        # 푸시 실패는 근태 기록 저장을 막지 않는다.
        pass

    return AttendanceRecordUpsertOut(record=inserted_out, already_exists=False)


@router.get("/today/status", response_model=AttendanceTodayStatusOut)
def get_today_status(conn=Depends(get_db_conn), user=Depends(get_current_user)):
    if not can_post_attendance(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _resolve_attendance_home_status(conn, user)


@router.get("/home-status", response_model=AttendanceTodayStatusOut)
def get_home_status(conn=Depends(get_db_conn), user=Depends(get_current_user)):
    if not can_post_attendance(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return _resolve_attendance_home_status(conn, user)


@router.get("/records")
def list_records(date: str | None = None, conn=Depends(get_db_conn), user=Depends(get_current_user)):
    _, _, today_kst = get_kst_day_bounds_utc(datetime.now(timezone.utc))
    target_date = _parse_iso_date(date, field_name="date") if date else today_kst
    query_start_utc, _ = _kst_day_bounds_for_date(target_date - timedelta(days=1))
    _, query_end_utc = _kst_day_bounds_for_date(target_date + timedelta(days=1))
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id, ar.event_type, ar.event_at, ar.distance_meters, ar.is_within_radius,
                   COALESCE(ar.auto_checkout, FALSE) AS auto_checkout,
                   ar.employee_id,
                   e.employee_code, e.full_name, s.id AS site_id, s.site_code, s.site_name
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            WHERE ar.tenant_id = %s
              AND ar.event_at >= %s
              AND ar.event_at < %s
            ORDER BY ar.event_at DESC
            LIMIT 300
            """,
            (user["tenant_id"], query_start_utc, query_end_utc),
        )
        raw_rows = [dict(r) for r in cur.fetchall()]

    rows_by_employee: dict[str, list[dict[str, Any]]] = {}
    for row in raw_rows:
        employee_id = str(row.get("employee_id") or "").strip()
        if employee_id:
            rows_by_employee.setdefault(employee_id, []).append(row)

    included_ids: set[str] = set()
    for employee_id, employee_rows in rows_by_employee.items():
        windows = fetch_schedule_windows(
            conn,
            tenant_id=str(user["tenant_id"]),
            employee_id=employee_id,
            start_date=target_date - timedelta(days=1),
            end_date=target_date + timedelta(days=1),
        )
        sessions = build_sessions(windows, employee_rows, now_utc=datetime.now(timezone.utc))
        for session in sessions:
            if session.get("business_date") == target_date:
                for key in ("check_in_id", "check_out_id"):
                    if session.get(key):
                        included_ids.add(str(session[key]))

    result = []
    for row in raw_rows:
        row_id = str(row.get("id") or "")
        if row_id in included_ids:
            result.append(row)
            continue
        if not included_ids and ensure_kst(row.get("event_at")).date() == target_date:
            result.append(row)
    return result


@router.get("/weekly-summary")
def get_weekly_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_post_attendance(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    range_start, range_end = _resolve_week_range(start_date, end_date)
    entries: list[dict[str, Any]] = []
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        return {
            "start_date": range_start.isoformat(),
            "end_date": range_end.isoformat(),
            "entries": entries,
        }

    entries = build_attendance_weekly_summary(
        conn,
        tenant_id=str(user["tenant_id"]),
        employee_id=employee_id,
        start_date=range_start,
        end_date=range_end,
        now_utc=datetime.now(timezone.utc),
    )

    return {
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "entries": entries,
    }
