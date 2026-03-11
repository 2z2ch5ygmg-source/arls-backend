from __future__ import annotations

import re
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import HTTPException

APPLE_OT_REASON_MAP = {
    "customer complaint": "Customer complaint",
    "customer repair": "Customer Repair",
    "customer inquiry": "Customer Inquiry",
    "complaint": "Customer complaint",
    "repair": "Customer Repair",
    "inquiry": "Customer Inquiry",
}
APPLE_OT_REASON_ENUM_MAP = {
    "customer complaint": "complaint",
    "customer repair": "repair",
    "customer inquiry": "inquiry",
    "complaint": "complaint",
    "repair": "repair",
    "inquiry": "inquiry",
}
APPLE_OT_REASON_LABEL_MAP = {
    "complaint": "Customer complaint",
    "repair": "Customer Repair",
    "inquiry": "Customer Inquiry",
}
APPLE_OT_PENDING_STATUS = "PENDING_REASON"
APPLE_OT_APPROVED_STATUS = "APPROVED"
APPLE_OT_CANCELLED_STATUS = "CANCELLED"
APPLE_OT_ALLOWED_STATUSES = {
    APPLE_OT_PENDING_STATUS,
    APPLE_OT_APPROVED_STATUS,
    APPLE_OT_CANCELLED_STATUS,
}
APPLE_OT_CHECKOUT_WINDOW_START = time(hour=22, minute=0)
APPLE_OT_CHECKOUT_WINDOW_END = time(hour=23, minute=0)
KST = timezone(timedelta(hours=9))

SUPPORT_TYPE_ALIASES = {
    "F": "F",
    "FORWARD": "F",
    "BK": "BK",
    "BACK": "BK",
    "INTERNAL": "INTERNAL",
    "SELF": "INTERNAL",
    "자체": "INTERNAL",
    "UNAVAILABLE": "UNAVAILABLE",
    "NOT_AVAILABLE": "UNAVAILABLE",
    "지원불가": "UNAVAILABLE",
}


def _to_upper(value: str | None) -> str:
    return str(value or "").strip().upper()


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _is_weekend(work_date: date) -> bool:
    return work_date.weekday() >= 5


def _as_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(KST)
    return value.astimezone(KST)


def _is_checkout_in_apple_ot_window(checkout_at: datetime) -> bool:
    local = _as_kst(checkout_at).time()
    return APPLE_OT_CHECKOUT_WINDOW_START <= local <= APPLE_OT_CHECKOUT_WINDOW_END


def resolve_site(conn, *, tenant_id, site_code: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, company_id, site_code, site_name, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s
              AND upper(site_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, site_code),
        )
        return cur.fetchone()


def resolve_employee(conn, *, tenant_id, employee_code: str, site_id=None) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        if site_id:
            cur.execute(
                """
                SELECT id, tenant_id, company_id, site_id, employee_code, full_name, duty_role
                FROM employees
                WHERE tenant_id = %s
                  AND site_id = %s
                  AND upper(employee_code) = upper(%s)
                LIMIT 1
                """,
                (tenant_id, site_id, employee_code),
            )
        else:
            cur.execute(
                """
                SELECT id, tenant_id, company_id, site_id, employee_code, full_name, duty_role
                FROM employees
                WHERE tenant_id = %s
                  AND upper(employee_code) = upper(%s)
                LIMIT 1
                """,
                (tenant_id, employee_code),
            )
        return cur.fetchone()


def resolve_tenant(conn, *, tenant_code: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code, tenant_name, COALESCE(is_active, TRUE) AS is_active
            FROM tenants
            WHERE upper(tenant_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_code,),
        )
        return cur.fetchone()


def _default_site_headcount(conn, *, tenant_id, site_id) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM employees
            WHERE tenant_id = %s
              AND site_id = %s
            """,
            (tenant_id, site_id),
        )
        row = cur.fetchone()
    count = int(row["cnt"] if row else 0)
    return max(1, count)


def get_or_create_site_shift_policy(conn, *, tenant_id, site_id) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            FROM site_apple_daytime_policy
            WHERE tenant_id = %s
              AND site_id = %s
            LIMIT 1
            """,
            (tenant_id, site_id),
        )
        row = cur.fetchone()
        if row:
            return row

        # Backfill from legacy policy table if present.
        cur.execute(
            """
            SELECT id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            FROM site_shift_policy
            WHERE tenant_id = %s
              AND site_id = %s
            LIMIT 1
            """,
            (tenant_id, site_id),
        )
        legacy = cur.fetchone()
        if legacy:
            cur.execute(
                """
                INSERT INTO site_apple_daytime_policy (
                    id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
                ON CONFLICT (tenant_id, site_id)
                DO UPDATE SET
                  weekday_headcount = EXCLUDED.weekday_headcount,
                  weekend_headcount = EXCLUDED.weekend_headcount,
                  updated_at = timezone('utc', now())
                RETURNING id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
                """,
                (
                    uuid.uuid4(),
                    tenant_id,
                    site_id,
                    int(legacy["weekday_headcount"]),
                    int(legacy["weekend_headcount"]),
                ),
            )
            return cur.fetchone()

        base_count = _default_site_headcount(conn, tenant_id=tenant_id, site_id=site_id)
        new_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO site_apple_daytime_policy (
                id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            RETURNING id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            """,
            (new_id, tenant_id, site_id, base_count, base_count),
        )
        created = cur.fetchone()

        # Keep legacy policy table synced for backward compatibility.
        cur.execute(
            """
            INSERT INTO site_shift_policy (id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at)
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id, site_id)
            DO UPDATE SET
              weekday_headcount = EXCLUDED.weekday_headcount,
              weekend_headcount = EXCLUDED.weekend_headcount,
              updated_at = timezone('utc', now())
            """,
            (uuid.uuid4(), tenant_id, site_id, base_count, base_count),
        )
        return created


def upsert_site_shift_policy(
    conn,
    *,
    tenant_id,
    site_id,
    weekday_headcount: int,
    weekend_headcount: int,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO site_apple_daytime_policy (
                id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id, site_id)
            DO UPDATE SET
              weekday_headcount = EXCLUDED.weekday_headcount,
              weekend_headcount = EXCLUDED.weekend_headcount,
              updated_at = timezone('utc', now())
            RETURNING id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at
            """,
            (uuid.uuid4(), tenant_id, site_id, int(weekday_headcount), int(weekend_headcount)),
        )
        row = cur.fetchone()

        # Keep legacy table mirrored to avoid regressions in existing P0/P1 flows.
        cur.execute(
            """
            INSERT INTO site_shift_policy (id, tenant_id, site_id, weekday_headcount, weekend_headcount, updated_at)
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id, site_id)
            DO UPDATE SET
              weekday_headcount = EXCLUDED.weekday_headcount,
              weekend_headcount = EXCLUDED.weekend_headcount,
              updated_at = timezone('utc', now())
            """,
            (uuid.uuid4(), tenant_id, site_id, int(weekday_headcount), int(weekend_headcount)),
        )
        return row


def generate_apple_daytime_shift(*, work_date: date, weekday_headcount: int, weekend_headcount: int) -> dict[str, Any]:
    weekend = _is_weekend(work_date)
    total = int(max(0, weekend_headcount if weekend else weekday_headcount))

    if weekend:
        supervisor_count = 0
        guard_count = total
    else:
        supervisor_count = 1 if total > 0 else 0
        guard_count = max(0, total - supervisor_count)

    return {
        "work_date": work_date,
        "is_weekend": weekend,
        "total_headcount": total,
        "supervisor_count": supervisor_count,
        "guard_count": guard_count,
        "supervisor_time": "08:00-18:00",
        "guard_time": "10:00-22:00",
        "supervisor_hours": 10.0,
        "guard_hours": 12.0,
    }


def normalize_apple_ot_reason(reason: str | None) -> str:
    raw = _to_text(reason)
    if not raw:
        raise HTTPException(status_code=400, detail="reason is required")
    normalized = APPLE_OT_REASON_MAP.get(raw.lower())
    if not normalized:
        raise HTTPException(status_code=400, detail="reason must be Customer complaint/Customer Repair/Customer Inquiry")
    return normalized


def normalize_apple_ot_reason_enum(reason: str | None) -> str:
    raw = _to_text(reason)
    if not raw:
        raise HTTPException(status_code=400, detail="reason is required")
    normalized = APPLE_OT_REASON_ENUM_MAP.get(raw.lower())
    if not normalized:
        raise HTTPException(status_code=400, detail="reason must be Customer complaint/Customer Repair/Customer Inquiry")
    return normalized


def _normalize_apple_ot_reason_output(value: str | None) -> str | None:
    raw = _to_text(value).lower()
    if not raw:
        return None
    if raw in APPLE_OT_REASON_LABEL_MAP:
        return APPLE_OT_REASON_LABEL_MAP[raw]
    return APPLE_OT_REASON_MAP.get(raw, None)


def _resolve_default_apple_ot_leader_user_id(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    fallback_user_id=None,
) -> Any:
    with conn.cursor() as cur:
        # Priority 1: on-duty vice supervisor for the date/site.
        cur.execute(
            """
            SELECT au.id
            FROM monthly_schedules ms
            JOIN employees e ON e.id = ms.employee_id
            JOIN arls_users au
              ON au.tenant_id = ms.tenant_id
             AND au.employee_id = ms.employee_id
             AND au.is_active = TRUE
            WHERE ms.tenant_id = %s
              AND ms.site_id = %s
              AND ms.schedule_date = %s
              AND lower(ms.shift_type) NOT IN ('off', 'holiday')
              AND upper(COALESCE(e.duty_role, '')) = 'VICE_SUPERVISOR'
            ORDER BY ms.employee_id
            LIMIT 1
            """,
            (tenant_id, site_id, work_date),
        )
        row = cur.fetchone()
        if row:
            return row["id"]

        # Priority 2: on-duty guard for the date/site.
        cur.execute(
            """
            SELECT au.id
            FROM monthly_schedules ms
            JOIN employees e ON e.id = ms.employee_id
            JOIN arls_users au
              ON au.tenant_id = ms.tenant_id
             AND au.employee_id = ms.employee_id
             AND au.is_active = TRUE
            WHERE ms.tenant_id = %s
              AND ms.site_id = %s
              AND ms.schedule_date = %s
              AND lower(ms.shift_type) NOT IN ('off', 'holiday')
              AND upper(COALESCE(e.duty_role, '')) = 'GUARD'
            ORDER BY ms.employee_id
            LIMIT 1
            """,
            (tenant_id, site_id, work_date),
        )
        row = cur.fetchone()
        if row:
            return row["id"]

    return fallback_user_id


def _resolve_default_closer_user_id(conn, *, tenant_id, site_id, work_date: date, fallback_user_id=None):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT employee_id
            FROM site_daily_closing_ot
            WHERE tenant_id = %s
              AND site_id = %s
              AND work_date = %s
            LIMIT 1
            """,
            (tenant_id, site_id, work_date),
        )
        row = cur.fetchone()
        if row and row.get("employee_id"):
            cur.execute(
                """
                SELECT id
                FROM arls_users
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND is_active = TRUE
                LIMIT 1
                """,
                (tenant_id, row["employee_id"]),
            )
            user_row = cur.fetchone()
            if user_row:
                return user_row["id"]
    return fallback_user_id


def _leader_checkout_in_window(conn, *, tenant_id, site_id, leader_user_id, work_date: date) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id
            FROM arls_users u
            JOIN attendance_records ar
              ON ar.tenant_id = u.tenant_id
             AND ar.employee_id = u.employee_id
            WHERE u.tenant_id = %s
              AND u.id = %s
              AND u.employee_id IS NOT NULL
              AND ar.site_id = %s
              AND ar.event_type = 'check_out'
              AND (ar.event_at AT TIME ZONE 'Asia/Seoul')::date = %s
              AND (ar.event_at AT TIME ZONE 'Asia/Seoul')::time >= time '22:00'
              AND (ar.event_at AT TIME ZONE 'Asia/Seoul')::time <= time '23:00'
            LIMIT 1
            """,
            (tenant_id, leader_user_id, site_id, work_date),
        )
        return cur.fetchone() is not None


def upsert_pending_apple_daytime_ot_from_checkout(
    conn,
    *,
    tenant_id,
    site_id,
    checkout_at: datetime,
    fallback_user_id=None,
    source_event_uid: str | None = None,
) -> dict[str, Any] | None:
    if not _is_checkout_in_apple_ot_window(checkout_at):
        return None

    local = _as_kst(checkout_at)
    work_date = local.date()
    leader_user_id = _resolve_default_apple_ot_leader_user_id(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        work_date=work_date,
        fallback_user_id=fallback_user_id,
    )
    if not leader_user_id:
        return None

    closer_user_id = _resolve_default_closer_user_id(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        work_date=work_date,
        fallback_user_id=leader_user_id,
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO apple_daytime_ot (
                id, tenant_id, site_id, work_date, leader_user_id, reason,
                status, hours, closer_user_id, source, source_event_uid, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, NULL,
                %s, 1.0, %s, 'APPLE_DAYTIME_OT', %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, site_id, work_date, leader_user_id)
            DO UPDATE SET
                hours = 1.0,
                closer_user_id = COALESCE(EXCLUDED.closer_user_id, apple_daytime_ot.closer_user_id),
                source_event_uid = COALESCE(EXCLUDED.source_event_uid, apple_daytime_ot.source_event_uid),
                updated_at = timezone('utc', now())
            RETURNING id, tenant_id, site_id, work_date, leader_user_id, reason, status, hours,
                      closer_user_id, source, source_event_uid, created_at, updated_at
            """,
            (
                uuid.uuid4(),
                tenant_id,
                site_id,
                work_date,
                leader_user_id,
                APPLE_OT_PENDING_STATUS,
                closer_user_id,
                _to_text(source_event_uid) or None,
            ),
        )
        return cur.fetchone()


def create_apple_overtime_log(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    leader_user_id,
    reason: str,
) -> dict[str, Any]:
    normalized_reason = normalize_apple_ot_reason_enum(reason)
    if not _leader_checkout_in_window(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        leader_user_id=leader_user_id,
        work_date=work_date,
    ):
        raise HTTPException(status_code=400, detail="leader checkout must be between 22:00 and 23:00 (KST)")

    with conn.cursor() as cur:
        closer_user_id = _resolve_default_closer_user_id(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            work_date=work_date,
            fallback_user_id=leader_user_id,
        )
        cur.execute(
            """
            INSERT INTO apple_daytime_ot (
                id, tenant_id, site_id, work_date, leader_user_id, reason, status,
                hours, closer_user_id, source, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                1.0, %s, 'APPLE_DAYTIME_OT', timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, site_id, work_date, leader_user_id)
            DO UPDATE SET
                reason = EXCLUDED.reason,
                status = EXCLUDED.status,
                hours = EXCLUDED.hours,
                closer_user_id = COALESCE(EXCLUDED.closer_user_id, apple_daytime_ot.closer_user_id),
                updated_at = timezone('utc', now())
            RETURNING id, tenant_id, site_id, work_date, leader_user_id, reason, status, hours,
                      closer_user_id, source, source_event_uid, created_at, updated_at
            """,
            (
                uuid.uuid4(),
                tenant_id,
                site_id,
                work_date,
                leader_user_id,
                normalized_reason,
                APPLE_OT_APPROVED_STATUS,
                closer_user_id,
            ),
        )
        row = cur.fetchone()

        # Legacy mirror write for backward compatibility with existing P1 dashboards.
        cur.execute(
            """
            INSERT INTO apple_overtime_log (
                id, tenant_id, site_id, work_date, leader_user_id, reason, hours, source, created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 1.0, 'APPLE_DAYTIME_OT', timezone('utc', now())
            )
            """,
            (
                uuid.uuid4(),
                tenant_id,
                site_id,
                work_date,
                leader_user_id,
                APPLE_OT_REASON_LABEL_MAP.get(normalized_reason, normalized_reason),
            ),
        )
        return row


def list_apple_overtime_logs(conn, *, tenant_id, work_date: date | None = None, site_id=None) -> list[dict[str, Any]]:
    clauses = ["ao.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("ao.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("ao.site_id = %s")
        params.append(site_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ao.id, t.tenant_code, s.site_code, ao.work_date, ao.leader_user_id,
                   u.username AS leader_username, u.full_name AS leader_full_name,
                   ao.reason, ao.status, ao.hours, ao.source, ao.created_at, ao.updated_at,
                   ao.closer_user_id,
                   cu.username AS closer_username, cu.full_name AS closer_full_name
            FROM apple_daytime_ot ao
            JOIN tenants t ON t.id = ao.tenant_id
            JOIN sites s ON s.id = ao.site_id
            LEFT JOIN arls_users u ON u.id = ao.leader_user_id
            LEFT JOIN arls_users cu ON cu.id = ao.closer_user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY ao.work_date DESC, ao.updated_at DESC, ao.created_at DESC
            """,
            tuple(params),
        )
        rows = cur.fetchall()

    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["reason"] = _normalize_apple_ot_reason_output(item.get("reason"))
        if item.get("status") not in APPLE_OT_ALLOWED_STATUSES:
            item["status"] = APPLE_OT_PENDING_STATUS
        normalized.append(item)
    return normalized


def create_late_shift_log(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    employee_id,
    minutes_late: int,
    note: str | None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        row_id = uuid.uuid4()
        cur.execute(
            """
            SELECT full_name
            FROM employees
            WHERE id = %s
            LIMIT 1
            """,
            (employee_id,),
        )
        employee = cur.fetchone() or {}
        employee_name = _to_text(employee.get("full_name")) or "Unknown"
        cur.execute(
            """
            INSERT INTO late_shift_log (id, tenant_id, site_id, work_date, employee_id, minutes_late, note, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, timezone('utc', now()))
            RETURNING id, tenant_id, site_id, work_date, employee_id, minutes_late, note, created_at
            """,
            (row_id, tenant_id, site_id, work_date, employee_id, int(minutes_late), _to_text(note) or None),
        )
        inserted = cur.fetchone()

        # Apple 보고 전용 Late Shift 미러 테이블에 upsert.
        cur.execute(
            """
            INSERT INTO apple_late_shift (
                id, tenant_id, site_id, work_date, employee_id, employee_name, note, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id, site_id, work_date, lower(employee_name))
            DO UPDATE SET
                employee_id = EXCLUDED.employee_id,
                note = EXCLUDED.note
            """,
            (
                uuid.uuid4(),
                tenant_id,
                site_id,
                work_date,
                employee_id,
                employee_name,
                _to_text(note) or None,
            ),
        )
        return inserted


def list_late_shift_logs(conn, *, tenant_id, work_date: date | None = None, site_id=None) -> list[dict[str, Any]]:
    clauses = ["ls.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("ls.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("ls.site_id = %s")
        params.append(site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ls.id, t.tenant_code, s.site_code, ls.work_date, ls.employee_id, e.employee_code,
                   e.full_name AS employee_name, ls.minutes_late, ls.note, ls.created_at
            FROM late_shift_log ls
            JOIN tenants t ON t.id = ls.tenant_id
            JOIN sites s ON s.id = ls.site_id
            JOIN employees e ON e.id = ls.employee_id
            WHERE {' AND '.join(clauses)}
            ORDER BY ls.work_date DESC, e.employee_code, ls.created_at DESC
            """,
            tuple(params),
        )
        return cur.fetchall()


def delete_late_shift_log(conn, *, tenant_id, row_id) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM late_shift_log
            WHERE id = %s
              AND tenant_id = %s
            """,
            (row_id, tenant_id),
        )
        return cur.rowcount > 0


def create_daily_event_log(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    event_type: str,
    description: str,
) -> dict[str, Any]:
    normalized = _to_upper(event_type)
    if normalized not in {"EVENT", "ADDITIONAL"}:
        raise HTTPException(status_code=400, detail="type must be EVENT/ADDITIONAL")
    text = _to_text(description)
    if not text:
        raise HTTPException(status_code=400, detail="description is required")
    with conn.cursor() as cur:
        row_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO daily_event_log (id, tenant_id, site_id, work_date, type, description, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, timezone('utc', now()))
            RETURNING id, tenant_id, site_id, work_date, type, description, created_at
            """,
            (row_id, tenant_id, site_id, work_date, normalized, text),
        )
        return cur.fetchone()


def list_daily_event_logs(conn, *, tenant_id, work_date: date | None = None, site_id=None) -> list[dict[str, Any]]:
    clauses = ["de.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("de.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("de.site_id = %s")
        params.append(site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT de.id, t.tenant_code, s.site_code, de.work_date, de.type, de.description, de.created_at
            FROM daily_event_log de
            JOIN tenants t ON t.id = de.tenant_id
            JOIN sites s ON s.id = de.site_id
            WHERE {' AND '.join(clauses)}
            ORDER BY de.work_date DESC, de.created_at DESC
            """,
            tuple(params),
        )
        return cur.fetchall()


def delete_daily_event_log(conn, *, tenant_id, row_id) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM daily_event_log
            WHERE id = %s
              AND tenant_id = %s
            """,
            (row_id, tenant_id),
        )
        return cur.rowcount > 0


def parse_support_entry_text(raw: str) -> tuple[str, str]:
    text = _to_text(raw)
    if not text:
        raise HTTPException(status_code=400, detail="support entry text is empty")

    parts = re.split(r"\s+", text, maxsplit=1)
    if not parts:
        raise HTTPException(status_code=400, detail="support entry text is empty")

    token = _to_upper(parts[0])
    worker_type = SUPPORT_TYPE_ALIASES.get(token)
    if worker_type:
        name = _to_text(parts[1] if len(parts) > 1 else "")
        if not name:
            raise HTTPException(status_code=400, detail="support worker name is required")
        return worker_type, name

    return "INTERNAL", text


def _resolve_employee_by_name(conn, *, tenant_id, site_id, full_name: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, full_name
            FROM employees
            WHERE tenant_id = %s
              AND site_id = %s
              AND lower(full_name) = lower(%s)
            LIMIT 1
            """,
            (tenant_id, site_id, full_name),
        )
        return cur.fetchone()


def _remember_external_support_worker(conn, *, tenant_id, site_id, worker_type: str, worker_name: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM external_support_workers
            WHERE tenant_id = %s
              AND COALESCE(site_id::text, '') = COALESCE(%s::text, '')
              AND worker_type = %s
              AND lower(worker_name) = lower(%s)
            LIMIT 1
            """,
            (tenant_id, site_id, worker_type, worker_name),
        )
        if cur.fetchone():
            return
        cur.execute(
            """
            INSERT INTO external_support_workers (id, tenant_id, site_id, worker_type, worker_name, created_at)
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            """,
            (uuid.uuid4(), tenant_id, site_id, worker_type, worker_name),
        )


def _hydrate_support_assignment_row(conn, *, row_id) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sa.id,
                   t.tenant_code,
                   s.site_code,
                   sa.work_date,
                   sa.support_period,
                   sa.slot_index,
                   sa.worker_type,
                   sa.employee_id,
                   e.employee_code,
                   e.full_name AS employee_name,
                   COALESCE(e.soc_role, '') AS soc_role,
                   COALESCE(e.duty_role, '') AS duty_role,
                   sa.name,
                   sa.affiliation,
                   sa.source,
                   sa.source_ticket_id,
                   sa.source_event_uid,
                   sa.created_at,
                   sa.updated_at
            FROM support_assignment sa
            JOIN tenants t ON t.id = sa.tenant_id
            JOIN sites s ON s.id = sa.site_id
            LEFT JOIN employees e ON e.id = sa.employee_id
            WHERE sa.id = %s
            LIMIT 1
            """,
            (row_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    payload = dict(row)
    payload["is_internal"] = str(payload.get("worker_type") or "").strip().upper() == "INTERNAL"
    payload["worker_name"] = str(payload.get("employee_name") or payload.get("name") or "").strip()
    return payload


def upsert_support_assignment(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    worker_type: str,
    name: str,
    support_period: str = "day",
    slot_index: int | None = None,
    source: str = "SHEET",
    employee_id=None,
    affiliation: str | None = None,
    source_ticket_id=None,
    source_event_uid: str | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    normalized_name = _to_text(name)
    if not normalized_name:
        raise HTTPException(status_code=400, detail="support worker name is required")

    normalized_type = SUPPORT_TYPE_ALIASES.get(_to_upper(worker_type))
    if not normalized_type:
        raise HTTPException(status_code=400, detail="worker_type must be F/BK/INTERNAL/UNAVAILABLE")
    normalized_period = str(support_period or "day").strip().lower() or "day"
    if normalized_period not in {"day", "night"}:
        raise HTTPException(status_code=400, detail="support_period must be day/night")
    normalized_slot_index = int(slot_index or 0)
    if normalized_slot_index <= 0:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(MAX(slot_index), 0) AS max_slot_index
                FROM support_assignment
                WHERE tenant_id = %s
                  AND site_id = %s
                  AND work_date = %s
                  AND support_period = %s
                """,
                (tenant_id, site_id, work_date, normalized_period),
            )
            max_slot_row = cur.fetchone()
        normalized_slot_index = int((max_slot_row or {}).get("max_slot_index") or 0) + 1
    normalized_affiliation = _to_text(affiliation)
    normalized_source = _to_text(source) or "SHEET"
    normalized_event_uid = _to_text(source_event_uid)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sa.id
            FROM support_assignment sa
            WHERE sa.tenant_id = %s
              AND sa.site_id = %s
              AND sa.work_date = %s
              AND sa.support_period = %s
              AND sa.slot_index = %s
            LIMIT 1
            """,
            (tenant_id, site_id, work_date, normalized_period, normalized_slot_index),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE support_assignment
                SET worker_type = %s,
                    employee_id = %s,
                    name = %s,
                    affiliation = %s,
                    source = %s,
                    source_ticket_id = COALESCE(%s, source_ticket_id),
                    source_event_uid = COALESCE(%s, source_event_uid),
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (
                    normalized_type,
                    employee_id,
                    normalized_name,
                    normalized_affiliation,
                    normalized_source,
                    source_ticket_id,
                    normalized_event_uid,
                    existing["id"],
                ),
            )
            hydrated = _hydrate_support_assignment_row(conn, row_id=existing["id"])
            return hydrated, False

        row_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO support_assignment (
                id, tenant_id, site_id, work_date, support_period,
                slot_index, worker_type, employee_id, name, affiliation, source,
                source_ticket_id, source_event_uid, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            RETURNING id
            """,
            (
                row_id,
                tenant_id,
                site_id,
                work_date,
                normalized_period,
                normalized_slot_index,
                normalized_type,
                employee_id,
                normalized_name,
                normalized_affiliation,
                normalized_source,
                source_ticket_id,
                normalized_event_uid,
            ),
        )
        created = cur.fetchone()

    if not employee_id:
        _remember_external_support_worker(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            worker_type=normalized_type,
            worker_name=normalized_name,
        )

    hydrated = _hydrate_support_assignment_row(conn, row_id=created["id"])
    return hydrated, True


def list_support_assignments(
    conn,
    *,
    tenant_id,
    work_date: date | None = None,
    site_id=None,
    support_period: str | None = None,
    source: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["sa.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("sa.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("sa.site_id = %s")
        params.append(site_id)
    if support_period:
        clauses.append("sa.support_period = %s")
        params.append(str(support_period).strip().lower())
    if source:
        clauses.append("sa.source = %s")
        params.append(str(source).strip())
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT sa.id,
                   t.tenant_code,
                   s.site_code,
                   sa.work_date,
                   sa.support_period,
                   sa.slot_index,
                   sa.worker_type,
                   sa.employee_id,
                   e.employee_code,
                   e.full_name AS employee_name,
                   COALESCE(e.soc_role, '') AS soc_role,
                   COALESCE(e.duty_role, '') AS duty_role,
                   sa.name,
                   sa.affiliation,
                   sa.source,
                   sa.source_ticket_id,
                   sa.source_event_uid,
                   sa.created_at,
                   sa.updated_at
            FROM support_assignment sa
            JOIN tenants t ON t.id = sa.tenant_id
            JOIN sites s ON s.id = sa.site_id
            LEFT JOIN employees e ON e.id = sa.employee_id
            WHERE {' AND '.join(clauses)}
            ORDER BY sa.work_date DESC, sa.support_period, sa.slot_index, sa.worker_type, sa.name
            """,
            tuple(params),
        )
        rows = [dict(row) for row in cur.fetchall()]
    for row in rows:
        row["is_internal"] = str(row.get("worker_type") or "").strip().upper() == "INTERNAL"
        row["worker_name"] = str(row.get("employee_name") or row.get("name") or "").strip()
    return rows


def delete_support_assignments_by_source_ticket(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    support_period: str,
    source_ticket_id,
    source: str | None = None,
) -> int:
    clauses = [
        "tenant_id = %s",
        "site_id = %s",
        "work_date = %s",
        "support_period = %s",
        "source_ticket_id = %s",
    ]
    params: list[Any] = [tenant_id, site_id, work_date, str(support_period or "day").strip().lower(), source_ticket_id]
    if source:
        clauses.append("source = %s")
        params.append(str(source).strip())
    with conn.cursor() as cur:
        cur.execute(
            f"""
            DELETE FROM support_assignment
            WHERE {' AND '.join(clauses)}
            """,
            tuple(params),
        )
        return int(cur.rowcount or 0)


def delete_support_assignment(conn, *, tenant_id, row_id) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM support_assignment
            WHERE id = %s
              AND tenant_id = %s
            """,
            (row_id, tenant_id),
        )
        return cur.rowcount > 0


def resolve_support_entries_to_assignments(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    entries: list[str],
    source: str = "SHEET",
) -> dict[str, Any]:
    inserted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for raw in entries:
        worker_type, name = parse_support_entry_text(raw)
        employee = _resolve_employee_by_name(conn, tenant_id=tenant_id, site_id=site_id, full_name=name)
        row, created = upsert_support_assignment(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            work_date=work_date,
            worker_type=worker_type,
            name=name,
            employee_id=employee["id"] if employee else None,
            source=source,
        )
        if row:
            if created:
                inserted.append(row)
            else:
                skipped.append(row)
    return {
        "inserted": inserted,
        "skipped": skipped,
    }


def upsert_apple_report_overnight_record(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    headcount: int,
    source_ticket_id: int | None = None,
    source_event_uid: str | None = None,
) -> dict[str, Any]:
    safe_headcount = max(0, int(headcount))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO apple_report_overnight_records (
                id, tenant_id, site_id, work_date, headcount, time_range, hours,
                source_ticket_id, source_event_uid, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, '22:00-08:00', 10.0,
                %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, site_id, work_date)
            DO UPDATE SET
                headcount = EXCLUDED.headcount,
                source_ticket_id = COALESCE(EXCLUDED.source_ticket_id, apple_report_overnight_records.source_ticket_id),
                source_event_uid = COALESCE(EXCLUDED.source_event_uid, apple_report_overnight_records.source_event_uid),
                updated_at = timezone('utc', now())
            RETURNING id, tenant_id, site_id, work_date, headcount, time_range, hours,
                      source_ticket_id, source_event_uid, created_at, updated_at
            """,
            (
                uuid.uuid4(),
                tenant_id,
                site_id,
                work_date,
                safe_headcount,
                source_ticket_id,
                _to_text(source_event_uid) or None,
            ),
        )
        return cur.fetchone()


def delete_apple_report_overnight_records_by_source_ticket(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    source_ticket_id: int,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM apple_report_overnight_records ao
            WHERE ao.tenant_id = %s
              AND ao.work_date = %s
              AND ao.source_ticket_id = %s
              AND (%s IS NULL OR ao.site_id = %s)
            RETURNING ao.id, ao.tenant_id, ao.site_id, ao.work_date, ao.headcount,
                      ao.time_range, ao.hours, ao.source_ticket_id, ao.source_event_uid
            """,
            (
                tenant_id,
                work_date,
                source_ticket_id,
                site_id,
                site_id,
            ),
        )
        return cur.fetchall()


def list_apple_late_shift_logs(conn, *, tenant_id, work_date: date | None = None, site_id=None) -> list[dict[str, Any]]:
    clauses = ["als.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("als.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("als.site_id = %s")
        params.append(site_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT als.id, t.tenant_code, s.site_code, als.work_date,
                   als.employee_id, als.employee_name, als.note, als.created_at
            FROM apple_late_shift als
            JOIN tenants t ON t.id = als.tenant_id
            JOIN sites s ON s.id = als.site_id
            WHERE {' AND '.join(clauses)}
            ORDER BY als.work_date DESC, als.employee_name, als.created_at DESC
            """,
            tuple(params),
        )
        return cur.fetchall()


def list_apple_report_overnight_records(conn, *, tenant_id, work_date: date | None = None, site_id=None) -> list[dict[str, Any]]:
    clauses = ["ao.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if work_date:
        clauses.append("ao.work_date = %s")
        params.append(work_date)
    if site_id:
        clauses.append("ao.site_id = %s")
        params.append(site_id)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ao.id, t.tenant_code, s.site_code, ao.work_date, ao.headcount, ao.time_range, ao.hours,
                   ao.source_ticket_id, ao.source_event_uid, ao.created_at, ao.updated_at
            FROM apple_report_overnight_records ao
            JOIN tenants t ON t.id = ao.tenant_id
            JOIN sites s ON s.id = ao.site_id
            WHERE {' AND '.join(clauses)}
            ORDER BY ao.work_date DESC, s.site_code
            """,
            tuple(params),
        )
        return cur.fetchall()


def build_apple_total_shift_rows(
    conn,
    *,
    tenant_id,
    start_date: date,
    end_date: date,
    total_source: str = "policy",
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS site_id, s.site_code, s.site_name, t.tenant_code,
                   COALESCE(p.weekday_headcount,
                            GREATEST((SELECT COUNT(*) FROM employees e WHERE e.tenant_id = s.tenant_id AND e.site_id = s.id), 1)
                   ) AS weekday_headcount,
                   COALESCE(p.weekend_headcount,
                            GREATEST((SELECT COUNT(*) FROM employees e WHERE e.tenant_id = s.tenant_id AND e.site_id = s.id), 1)
                   ) AS weekend_headcount
            FROM sites s
            JOIN tenants t ON t.id = s.tenant_id
            LEFT JOIN site_apple_daytime_policy p
              ON p.tenant_id = s.tenant_id
             AND p.site_id = s.id
            WHERE s.tenant_id = %s
              AND COALESCE(s.is_active, TRUE) = TRUE
            ORDER BY s.site_code
            """,
            (tenant_id,),
        )
        sites = cur.fetchall()

    attendance_counts: dict[tuple[str, date], int] = {}
    if _to_text(total_source).lower() == "attendance":
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ar.site_id, (ar.event_at AT TIME ZONE 'Asia/Seoul')::date AS work_date,
                       COUNT(DISTINCT ar.employee_id) AS cnt
                FROM attendance_records ar
                WHERE ar.tenant_id = %s
                  AND ar.event_type = 'check_in'
                  AND (ar.event_at AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
                GROUP BY ar.site_id, (ar.event_at AT TIME ZONE 'Asia/Seoul')::date
                """,
                (tenant_id, start_date, end_date),
            )
            for row in cur.fetchall():
                attendance_counts[(str(row["site_id"]), row["work_date"])] = int(row["cnt"] or 0)

    rows: list[dict[str, Any]] = []
    cursor = start_date
    while cursor <= end_date:
        for site in sites:
            generated = generate_apple_daytime_shift(
                work_date=cursor,
                weekday_headcount=int(site["weekday_headcount"]),
                weekend_headcount=int(site["weekend_headcount"]),
            )
            policy_headcount = int(generated["total_headcount"])
            effective_headcount = policy_headcount
            if _to_text(total_source).lower() == "attendance":
                effective_headcount = attendance_counts.get((str(site["site_id"]), cursor), 0)
            rows.append(
                {
                    "tenant_code": site["tenant_code"],
                    "site_code": site["site_code"],
                    "site_name": site["site_name"],
                    "work_date": cursor.isoformat(),
                    "headcount_source": "attendance" if _to_text(total_source).lower() == "attendance" else "policy",
                    "headcount": int(max(0, effective_headcount)),
                    "policy_headcount": policy_headcount,
                    "total_shifts": int(max(0, effective_headcount) * 4),
                    "row_type": "apple_total_shifts",
                }
            )
        cursor = cursor + timedelta(days=1)
    return rows


def build_duty_log(conn, *, tenant_id, employee_id, month: str) -> list[dict[str, Any]]:
    try:
        month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM") from exc
    if month_start.month == 12:
        month_end_exclusive = date(month_start.year + 1, 1, 1)
    else:
        month_end_exclusive = date(month_start.year, month_start.month + 1, 1)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT schedule_date, shift_type, source
            FROM monthly_schedules
            WHERE tenant_id = %s
              AND employee_id = %s
              AND schedule_date >= %s
              AND schedule_date < %s
            """,
            (tenant_id, employee_id, month_start, month_end_exclusive),
        )
        schedule_rows = {row["schedule_date"]: row for row in cur.fetchall()}

        cur.execute(
            """
            SELECT start_at, end_at, leave_type
            FROM leave_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND status = 'approved'
              AND end_at >= %s
              AND start_at < %s
            """,
            (tenant_id, employee_id, month_start, month_end_exclusive),
        )
        leave_rows = cur.fetchall()

    leave_by_date: dict[date, str] = {}
    for row in leave_rows:
        leave_type = _to_text(row.get("leave_type")).lower()
        cursor = row["start_at"]
        end = row["end_at"]
        while cursor <= end:
            if month_start <= cursor < month_end_exclusive:
                leave_by_date[cursor] = leave_type
            cursor = cursor + timedelta(days=1)

    rows: list[dict[str, Any]] = []
    cursor = month_start
    while cursor < month_end_exclusive:
        leave_type = leave_by_date.get(cursor)
        schedule = schedule_rows.get(cursor)
        shift_type = _to_text(schedule.get("shift_type")) if schedule else ""
        source = _to_text(schedule.get("source")) if schedule else ""

        if leave_type in {"annual", "sick", "early_leave", "half"}:
            mark = "연차"
        elif shift_type.lower() == "day":
            mark = "주간"
        else:
            mark = ""

        rows.append(
            {
                "work_date": cursor,
                "mark": mark,
                "shift_type": shift_type or None,
                "leave_type": leave_type or None,
                "source": source or None,
            }
        )
        cursor = cursor + timedelta(days=1)
    return rows
