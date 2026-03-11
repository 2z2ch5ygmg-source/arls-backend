from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone
from typing import Any

from ..db import get_connection
from .push_notifications import send_attendance_push_notification

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

_scheduler_started = False
_scheduler_lock = threading.Lock()
_schema_ready = False
_schema_lock = threading.Lock()
_attendance_has_schedule_id = False
_attendance_has_shift_id = False
_attendance_has_auto_checkout_reason = False
_has_monthly_schedules = False
AUTO_CHECKOUT_LOOP_SECONDS = 300
AUTO_CHECKOUT_ADVISORY_LOCK_KEY = 88121042


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.tables
              WHERE table_schema = 'public'
                AND table_name = %s
            ) AS exists_flag
            """,
            (table_name,),
        )
        row = cur.fetchone() or {}
    return bool(row.get("exists_flag"))


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM information_schema.columns
              WHERE table_schema = 'public'
                AND table_name = %s
                AND column_name = %s
            ) AS exists_flag
            """,
            (table_name, column_name),
        )
        row = cur.fetchone() or {}
    return bool(row.get("exists_flag"))


def ensure_attendance_runtime_schema(conn) -> None:
    global _schema_ready
    global _attendance_has_schedule_id
    global _attendance_has_shift_id
    global _attendance_has_auto_checkout_reason
    global _has_monthly_schedules
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = 'attendance_records'
                    ) THEN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'attendance_records'
                              AND column_name = 'auto_checkout'
                        ) THEN
                            ALTER TABLE attendance_records
                                ADD COLUMN auto_checkout boolean NOT NULL DEFAULT FALSE;
                        END IF;
                        IF NOT EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_schema = 'public'
                              AND table_name = 'attendance_records'
                              AND column_name = 'auto_checkout_reason'
                        ) THEN
                            ALTER TABLE attendance_records
                                ADD COLUMN auto_checkout_reason text;
                        END IF;
                    END IF;
                END $$;
                """
            )
        _attendance_has_schedule_id = _column_exists(conn, "attendance_records", "schedule_id")
        _attendance_has_shift_id = _column_exists(conn, "attendance_records", "shift_id")
        _attendance_has_auto_checkout_reason = _column_exists(conn, "attendance_records", "auto_checkout_reason")
        _has_monthly_schedules = _table_exists(conn, "monthly_schedules")
        _schema_ready = True


def _ensure_utc(value: datetime | None) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _bounds_for_kst_day(reference_utc: datetime) -> tuple[datetime, datetime, date]:
    reference_kst = reference_utc.astimezone(KST)
    target_day = reference_kst.date()
    start_kst = datetime.combine(target_day, dt_time.min, tzinfo=KST)
    end_kst = start_kst + timedelta(days=1)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc), target_day


def get_kst_day_bounds_utc(reference_utc: datetime | None = None) -> tuple[datetime, datetime, date]:
    return _bounds_for_kst_day(_ensure_utc(reference_utc))


def run_auto_checkout(
    conn,
    *,
    tenant_id: str | None = None,
    now_utc: datetime | None = None,
) -> list[dict[str, Any]]:
    ref_utc = _ensure_utc(now_utc)
    schedule_exemption_conditions: list[str] = []
    if _attendance_has_schedule_id:
        schedule_exemption_conditions.append("ci.schedule_id IS NOT NULL")
    if _attendance_has_shift_id:
        schedule_exemption_conditions.append("ci.shift_id IS NOT NULL")
    if _has_monthly_schedules:
        schedule_exemption_conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM monthly_schedules ms
                WHERE ms.tenant_id = ci.tenant_id
                  AND ms.employee_id = ci.employee_id
                  AND ms.schedule_date = (ci.event_at AT TIME ZONE 'Asia/Seoul')::date
                  AND lower(COALESCE(ms.shift_type, '')) NOT IN ('off', 'holiday')
                  AND (ms.site_id = ci.site_id OR ms.site_id IS NULL)
            )
            """
        )

    schedule_exemption_sql = " OR ".join(schedule_exemption_conditions) if schedule_exemption_conditions else "FALSE"
    tenant_clause = "AND ci.tenant_id = %s" if tenant_id else ""
    params: list[Any] = []
    if tenant_id:
        params.append(tenant_id)
    params.append(ref_utc)

    insert_reason_column = ", auto_checkout_reason" if _attendance_has_auto_checkout_reason else ""
    insert_reason_value = ", 'MAX_24H'" if _attendance_has_auto_checkout_reason else ""
    select_reason_value = ", COALESCE(i.auto_checkout_reason, '') AS auto_checkout_reason" if _attendance_has_auto_checkout_reason else ", ''::text AS auto_checkout_reason"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            WITH open_checkins AS (
                SELECT
                    ci.tenant_id,
                    ci.employee_id,
                    ci.site_id,
                    ci.event_at,
                    ci.latitude,
                    ci.longitude
                FROM attendance_records ci
                WHERE ci.event_type = 'check_in'
                  {tenant_clause}
                  AND ci.event_at <= (%s::timestamptz - INTERVAL '24 hours')
                  AND NOT ({schedule_exemption_sql})
                  AND NOT EXISTS (
                    SELECT 1
                    FROM attendance_records co
                    WHERE co.tenant_id = ci.tenant_id
                      AND co.employee_id = ci.employee_id
                      AND co.site_id = ci.site_id
                      AND co.event_type = 'check_out'
                      AND co.event_at > ci.event_at
                  )
            ),
            inserted AS (
                INSERT INTO attendance_records (
                    tenant_id,
                    employee_id,
                    site_id,
                    event_type,
                    event_at,
                    latitude,
                    longitude,
                    distance_meters,
                    is_within_radius,
                    auto_checkout
                    {insert_reason_column}
                )
                SELECT
                    oc.tenant_id,
                    oc.employee_id,
                    oc.site_id,
                    'check_out',
                    (oc.event_at + INTERVAL '24 hours'),
                    oc.latitude,
                    oc.longitude,
                    0,
                    TRUE,
                    TRUE
                    {insert_reason_value}
                FROM open_checkins oc
                ON CONFLICT (tenant_id, employee_id, event_type, event_at)
                DO NOTHING
                RETURNING id, tenant_id, employee_id, site_id, event_type, event_at, auto_checkout
                {insert_reason_column}
            )
            SELECT
                i.id,
                i.tenant_id,
                i.employee_id,
                i.site_id,
                i.event_type,
                i.event_at,
                i.auto_checkout
                {select_reason_value},
                e.full_name AS employee_name,
                s.site_name,
                s.site_code
            FROM inserted i
            LEFT JOIN employees e ON e.id = i.employee_id
            LEFT JOIN sites s ON s.id = i.site_id
            """,
            params,
        )
        rows = cur.fetchall() or []
    return [dict(row) for row in rows]


def fetch_today_status(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    ref_utc = _ensure_utc(now_utc)
    day_start_utc, day_end_utc, _ = _bounds_for_kst_day(ref_utc)
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
            (tenant_id, employee_id, day_start_utc, day_end_utc),
        )
        rows = cur.fetchall() or []

    check_in_row = next((row for row in rows if str(row.get("event_type")) == "check_in"), None)
    check_out_candidates = [row for row in rows if str(row.get("event_type")) == "check_out"]
    check_out_row = check_out_candidates[-1] if check_out_candidates else None

    if check_in_row and check_out_row:
        status = "DONE"
    elif check_in_row:
        status = "WORKING"
    else:
        status = "NONE"

    site_row = check_in_row or check_out_row or {}
    last_row = check_out_row or check_in_row or {}
    if status == "DONE":
        button_mode = "done"
    elif status == "WORKING":
        button_mode = "check_out"
    else:
        button_mode = "check_in"
    return {
        "status": status,
        "check_in_at": check_in_row.get("event_at") if check_in_row else None,
        "check_out_at": check_out_row.get("event_at") if check_out_row else None,
        "today_record_id": last_row.get("id"),
        "button_mode": button_mode,
        "auto_checkout": bool(check_out_row.get("auto_checkout")) if check_out_row else None,
        "auto_checkout_reason": str(check_out_row.get("auto_checkout_reason") or "").strip() if check_out_row else "",
        "site_id": site_row.get("site_id"),
        "site_code": site_row.get("site_code"),
        "site_name": site_row.get("site_name"),
    }


def _try_acquire_auto_checkout_lock(conn) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_try_advisory_lock(%s) AS locked",
            (AUTO_CHECKOUT_ADVISORY_LOCK_KEY,),
        )
        row = cur.fetchone() or {}
    return bool(row.get("locked"))


def _release_auto_checkout_lock(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT pg_advisory_unlock(%s)",
            (AUTO_CHECKOUT_ADVISORY_LOCK_KEY,),
        )


def _run_auto_checkout_job_once(reason: str = "manual") -> int:
    try:
        with get_connection() as conn:
            lock_acquired = False
            try:
                lock_acquired = _try_acquire_auto_checkout_lock(conn)
                if not lock_acquired:
                    logger.info("attendance auto checkout skipped reason=%s lock=busy", reason)
                    return 0
                rows = run_auto_checkout(conn, tenant_id=None)
                if rows:
                    for row in rows:
                        try:
                            send_attendance_push_notification(
                                conn,
                                tenant_id=str(row.get("tenant_id") or ""),
                                site_id=str(row.get("site_id") or ""),
                                site_name=str(row.get("site_name") or ""),
                                employee_id=str(row.get("employee_id") or ""),
                                employee_name=str(row.get("employee_name") or ""),
                                event_type="check_out",
                                event_at_iso=str(row.get("event_at") or ""),
                                auto_checkout=True,
                            )
                        except Exception:
                            logger.exception("attendance auto checkout push failed")
                    logger.info("attendance auto checkout rows=%s reason=%s", len(rows), reason)
                return len(rows)
            finally:
                if lock_acquired:
                    try:
                        _release_auto_checkout_lock(conn)
                    except Exception:
                        logger.exception("attendance auto checkout unlock failed reason=%s", reason)
    except Exception:
        logger.exception("attendance auto checkout job failed reason=%s", reason)
        return 0


def _auto_checkout_scheduler_loop() -> None:
    _run_auto_checkout_job_once(reason="startup")
    while True:
        time.sleep(AUTO_CHECKOUT_LOOP_SECONDS)
        _run_auto_checkout_job_once(reason="interval")


def start_attendance_auto_checkout_scheduler() -> None:
    global _scheduler_started
    with _scheduler_lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    thread = threading.Thread(
        target=_auto_checkout_scheduler_loop,
        name="attendance-auto-checkout-scheduler",
        daemon=True,
    )
    thread.start()
