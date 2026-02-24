from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ...deps import get_db_conn, get_current_user, apply_rate_limit, get_idempotency_key
from ...schemas import AttendanceCreate, AttendanceOut
from ...services.closing_overtime import apply_closing_overtime_from_checkout
from ...services.p1_schedule import upsert_pending_apple_daytime_ot_from_checkout
from ...utils.geo import haversine_meters
from ...utils.permissions import can_post_attendance, is_super_admin

router = APIRouter(prefix="/attendance", tags=["attendance"], dependencies=[Depends(apply_rate_limit)])


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
            SELECT id, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s AND site_code = %s
            """,
            (tenant_id, site_code),
        )
        return cur.fetchone()


@router.post("/records", response_model=AttendanceOut)
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

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM attendance_records
            WHERE tenant_id = %s
              AND employee_id = %s
              AND site_id = %s
              AND event_type = %s
              AND event_at >= %s::date
              AND event_at < (%s::date + interval '1 day')
            ORDER BY event_at DESC
            LIMIT 1
            """,
            (
                user["tenant_id"],
                emp["id"],
                site["id"],
                payload.event_type,
                payload.event_at,
                payload.event_at,
            ),
        )
        duplicate = cur.fetchone()

        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="duplicate event in same day")

        cur.execute(
            """
            INSERT INTO attendance_records (
              tenant_id, employee_id, site_id, event_type, event_at,
              latitude, longitude, distance_meters, is_within_radius
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, event_at
            """,
            (
                user["tenant_id"],
                emp["id"],
                site["id"],
                payload.event_type,
                payload.event_at,
                payload.latitude,
                payload.longitude,
                distance,
                within,
            ),
        )
        inserted = cur.fetchone()

        if payload.event_type == "check_out":
            apply_closing_overtime_from_checkout(
                conn,
                tenant_id=user["tenant_id"],
                site_id=site["id"],
                employee_id=emp["id"],
                checkout_at=payload.event_at,
                source_event_uid=f"attendance_record:{inserted['id']}",
                source_label="ATTENDANCE_RECORD",
            )
            upsert_pending_apple_daytime_ot_from_checkout(
                conn,
                tenant_id=user["tenant_id"],
                site_id=site["id"],
                checkout_at=payload.event_at,
                fallback_user_id=user.get("id"),
                source_event_uid=f"attendance_record:{inserted['id']}",
            )

        cur.execute(
            """
            SELECT ar.id, ar.employee_id, ar.event_type, ar.event_at, s.site_name,
                   ar.distance_meters, ar.is_within_radius, e.employee_code
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            WHERE ar.id = %s
            """,
            (inserted["id"],),
        )
        row = cur.fetchone()

    return AttendanceOut(
        id=row["id"],
        employee_code=row["employee_code"],
        event_type=row["event_type"],
        event_at=row["event_at"],
        site_name=row["site_name"],
        distance_meters=float(row["distance_meters"]),
        is_within_radius=bool(row["is_within_radius"]),
    )


@router.get("/records")
def list_records(date: str | None = None, conn=Depends(get_db_conn), user=Depends(get_current_user)):
    target = date or datetime.utcnow().date().isoformat()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id, ar.event_type, ar.event_at, ar.distance_meters, ar.is_within_radius,
                   e.employee_code, e.full_name, s.site_code, s.site_name
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            JOIN sites s ON s.id = ar.site_id
            WHERE ar.tenant_id = %s
              AND ar.event_at::date = %s::date
            ORDER BY ar.event_at DESC
            LIMIT 300
            """,
            (user["tenant_id"], target),
        )
        return [dict(r) for r in cur.fetchall()]
