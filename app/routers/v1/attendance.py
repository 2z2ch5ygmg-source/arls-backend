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
            WHERE e.tenant_id = %s AND t.tenant_code = %s AND e.employee_code = %s
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
        auto_checkout=row.get("auto_checkout"),
        site_id=row.get("site_id"),
        site_code=row.get("site_code"),
        site_name=row.get("site_name"),
        employee_id=user.get("employee_id"),
        employee_name=user.get("full_name"),
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

    if payload.tenant_code != user["tenant_code"] and not is_super_admin(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")

    emp = _tenant_employee(conn, user["tenant_id"], payload.tenant_code, payload.employee_code)
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
    day_start_utc, day_end_utc, _ = get_kst_day_bounds_utc(event_at_utc)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_type, event_at
            FROM attendance_records
            WHERE tenant_id = %s
              AND employee_id = %s
              AND event_type IN ('check_in', 'check_out')
              AND event_at >= %s
              AND event_at < %s
            ORDER BY event_at ASC
            """,
            (
                user["tenant_id"],
                emp["id"],
                day_start_utc,
                day_end_utc,
            ),
        )
        day_rows = cur.fetchall() or []
        check_in_row = next((row for row in day_rows if str(row.get("event_type")) == "check_in"), None)
        check_out_candidates = [row for row in day_rows if str(row.get("event_type")) == "check_out"]
        check_out_row = check_out_candidates[-1] if check_out_candidates else None

        if payload.event_type == "check_in" and check_in_row:
            existing_out = _fetch_record_out_by_id(conn, str(check_in_row["id"]))
            return AttendanceRecordUpsertOut(record=existing_out, already_exists=True)
        if payload.event_type == "check_out":
            if not check_in_row:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="check_in required before check_out",
                )
            if check_out_row:
                existing_out = _fetch_record_out_by_id(conn, str(check_out_row["id"]))
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
                  AND event_at >= %s
                  AND event_at < %s
                ORDER BY event_at DESC
                LIMIT 1
                """,
                (
                    user["tenant_id"],
                    emp["id"],
                    payload.event_type,
                    day_start_utc,
                    day_end_utc,
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
    day_start_utc, day_end_utc = _kst_day_bounds_for_date(target_date)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id, ar.event_type, ar.event_at, ar.distance_meters, ar.is_within_radius,
                   COALESCE(ar.auto_checkout, FALSE) AS auto_checkout,
                   e.employee_code, e.full_name, s.site_code, s.site_name
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            WHERE ar.tenant_id = %s
              AND ar.event_at >= %s
              AND ar.event_at < %s
            ORDER BY ar.event_at DESC
            LIMIT 300
            """,
            (user["tenant_id"], day_start_utc, day_end_utc),
        )
        return [dict(r) for r in cur.fetchall()]


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

    range_start_utc, _ = _kst_day_bounds_for_date(range_start)
    _, range_end_utc = _kst_day_bounds_for_date(range_end)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                (ar.event_at AT TIME ZONE 'Asia/Seoul')::date AS work_date,
                COUNT(*) FILTER (WHERE ar.event_type = 'check_in') AS check_in_count,
                COUNT(*) FILTER (WHERE ar.event_type = 'check_out') AS check_out_count
            FROM attendance_records ar
            WHERE ar.tenant_id = %s
              AND ar.employee_id = %s
              AND ar.event_at >= %s
              AND ar.event_at < %s
              AND ar.event_type IN ('check_in', 'check_out')
            GROUP BY work_date
            ORDER BY work_date
            """,
            (user["tenant_id"], employee_id, range_start_utc, range_end_utc),
        )
        rows = cur.fetchall() or []

    summary_by_date: dict[str, dict[str, int]] = {}
    for row in rows:
        work_date = row.get("work_date")
        if isinstance(work_date, dt_date):
            key = work_date.isoformat()
        else:
            key = str(work_date or "").strip()
        if not key:
            continue
        summary_by_date[key] = {
            "check_in_count": int(row.get("check_in_count") or 0),
            "check_out_count": int(row.get("check_out_count") or 0),
        }

    current = range_start
    while current <= range_end:
        key = current.isoformat()
        summary = summary_by_date.get(key) or {"check_in_count": 0, "check_out_count": 0}
        entries.append(
            {
                "date": key,
                "check_in_count": int(summary.get("check_in_count") or 0),
                "check_out_count": int(summary.get("check_out_count") or 0),
            }
        )
        current += timedelta(days=1)

    return {
        "start_date": range_start.isoformat(),
        "end_date": range_end.isoformat(),
        "entries": entries,
    }
