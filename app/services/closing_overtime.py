from __future__ import annotations

import uuid
import json
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))
STORE_CLOSE_TIME = time(hour=22, minute=0)
OT_RULE_START_TIME = time(hour=22, minute=10)

SUPERVISOR_ROLES = [
    "branch_manager",
    "site_manager",
    "supervisor",
    "tenant_admin",
    "platform_admin",
    "dev",
]


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _work_bounds_utc(work_date: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(work_date, time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _close_overtime_units(local_checkout_at: datetime) -> float:
    work_date = local_checkout_at.date()
    at_2210 = datetime.combine(work_date, OT_RULE_START_TIME, tzinfo=KST)
    at_2230_end = datetime.combine(work_date, time(hour=22, minute=30, second=59), tzinfo=KST)
    at_2300_end = datetime.combine(work_date, time(hour=23, minute=0, second=59), tzinfo=KST)
    at_2300 = datetime.combine(work_date, time(hour=23, minute=0), tzinfo=KST)

    if local_checkout_at < at_2210:
        return 0.0
    if local_checkout_at <= at_2230_end:
        return 0.5
    if local_checkout_at <= at_2300_end:
        return 1.0

    minutes_after_23 = int((local_checkout_at - at_2300).total_seconds() // 60)
    extra_band = max(0, (minutes_after_23 - 1) // 30)
    return round(1.5 + (0.5 * extra_band), 2)


def _raw_close_minutes(local_checkout_at: datetime) -> int:
    store_close_at = datetime.combine(local_checkout_at.date(), STORE_CLOSE_TIME, tzinfo=KST)
    return max(0, int((local_checkout_at - store_close_at).total_seconds() // 60))


def _resolve_schedule_closer(conn, *, tenant_id, site_id, work_date: date):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.employee_id
            FROM monthly_schedules ms
            WHERE ms.tenant_id = %s
              AND ms.site_id = %s
              AND ms.schedule_date = %s
              AND (
                    lower(COALESCE(ms.schedule_note, '')) LIKE '%%closer%%'
                 OR lower(COALESCE(ms.schedule_note, '')) LIKE '%%closing%%'
                 OR lower(ms.shift_type) IN ('close', 'closing')
              )
            ORDER BY
              CASE
                WHEN lower(COALESCE(ms.schedule_note, '')) LIKE '%%closer%%' THEN 0
                WHEN lower(COALESCE(ms.schedule_note, '')) LIKE '%%closing%%' THEN 1
                ELSE 2
              END,
              ms.employee_id
            LIMIT 1
            """,
            (tenant_id, site_id, work_date),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"employee_id": row["employee_id"], "selection_rule": "schedule_closer", "priority": 30}


def _resolve_vice_supervisor_closer(conn, *, tenant_id, site_id, work_date: date):
    day_start_utc, day_end_utc = _work_bounds_utc(work_date)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.employee_id
            FROM attendance_records ar
            JOIN arls_users au
              ON au.tenant_id = ar.tenant_id
             AND au.employee_id = ar.employee_id
             AND au.is_active = TRUE
            WHERE ar.tenant_id = %s
              AND ar.site_id = %s
              AND ar.event_type = 'check_out'
              AND ar.event_at >= %s
              AND ar.event_at < %s
              AND lower(au.role) = ANY(%s)
            ORDER BY ar.event_at DESC
            LIMIT 1
            """,
            (
                tenant_id,
                site_id,
                day_start_utc,
                day_end_utc,
                SUPERVISOR_ROLES,
            ),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"employee_id": row["employee_id"], "selection_rule": "vice_supervisor_auto", "priority": 20}


def _resolve_closer_candidate(
    conn,
    *,
    tenant_id,
    site_id,
    work_date: date,
    fallback_employee_id,
) -> dict[str, Any]:
    schedule_closer = _resolve_schedule_closer(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        work_date=work_date,
    )
    if schedule_closer:
        return schedule_closer

    vice_supervisor_closer = _resolve_vice_supervisor_closer(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        work_date=work_date,
    )
    if vice_supervisor_closer:
        return vice_supervisor_closer

    return {
        "employee_id": fallback_employee_id,
        "selection_rule": "fallback_checkout_employee",
        "priority": 10,
    }


def _write_overtime_audit(
    conn,
    *,
    tenant_id,
    action_type: str,
    entity_id: str,
    before_json: dict[str, Any] | None,
    after_json: dict[str, Any] | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_log (
                id, tenant_id, actor_type, actor_id, action_type, entity_type, entity_id, before_json, after_json, created_at
            )
            VALUES (%s, %s, 'SYSTEM', 'attendance_close_policy', %s, 'OVERTIME', %s, %s::jsonb, %s::jsonb, timezone('utc', now()))
            """,
            (
                uuid.uuid4(),
                tenant_id,
                action_type,
                entity_id,
                json.dumps(before_json or {}, ensure_ascii=False),
                json.dumps(after_json or {}, ensure_ascii=False),
            ),
        )


def apply_closing_overtime_from_checkout(
    conn,
    *,
    tenant_id,
    site_id,
    employee_id,
    checkout_at: datetime,
    source_event_uid: str | None = None,
    source_label: str = "ATTENDANCE",
) -> dict[str, Any]:
    checkout_at_utc = _as_utc(checkout_at)
    checkout_at_local = checkout_at_utc.astimezone(KST)
    work_date = checkout_at_local.date()
    overtime_hours_step = _close_overtime_units(checkout_at_local)
    raw_minutes_total = _raw_close_minutes(checkout_at_local)

    if overtime_hours_step <= 0:
        return {
            "closing_ot": False,
            "applied": False,
            "reason": "checkout_before_22_10",
            "work_date": work_date.isoformat(),
            "overtime_hours_step": 0.0,
        }

    closer = _resolve_closer_candidate(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        work_date=work_date,
        fallback_employee_id=employee_id,
    )
    selected_employee_id = closer["employee_id"]
    selection_rule = closer["selection_rule"]
    selection_priority = int(closer["priority"])

    if str(selected_employee_id) != str(employee_id):
        return {
            "closing_ot": False,
            "applied": False,
            "reason": "not_selected_closer",
            "work_date": work_date.isoformat(),
            "selected_employee_id": str(selected_employee_id),
            "selection_rule": selection_rule,
            "selection_priority": selection_priority,
            "overtime_hours_step": overtime_hours_step,
        }

    approved_minutes = int(round(overtime_hours_step * 60))
    closing_uid = f"attendance_close:{tenant_id}:{site_id}:{work_date.isoformat()}"
    overtime_reason = f"{source_label} checkout close rule ({selection_rule})"

    with conn.cursor() as cur:
        closing_record_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO site_daily_closing_ot (
                id, tenant_id, site_id, work_date, employee_id, checkout_at, overtime_minutes, source_event_uid,
                policy_priority, closer_selection_rule, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, timezone('utc', now()), timezone('utc', now()))
            ON CONFLICT (tenant_id, site_id, work_date)
            DO UPDATE SET
                employee_id = EXCLUDED.employee_id,
                checkout_at = EXCLUDED.checkout_at,
                overtime_minutes = EXCLUDED.overtime_minutes,
                source_event_uid = EXCLUDED.source_event_uid,
                policy_priority = EXCLUDED.policy_priority,
                closer_selection_rule = EXCLUDED.closer_selection_rule,
                updated_at = timezone('utc', now())
            WHERE site_daily_closing_ot.policy_priority < EXCLUDED.policy_priority
               OR (
                    site_daily_closing_ot.policy_priority = EXCLUDED.policy_priority
                AND site_daily_closing_ot.checkout_at <= EXCLUDED.checkout_at
               )
            RETURNING id, employee_id, checkout_at, overtime_minutes, policy_priority, closer_selection_rule
            """,
            (
                closing_record_id,
                tenant_id,
                site_id,
                work_date,
                employee_id,
                checkout_at_utc,
                raw_minutes_total,
                source_event_uid or closing_uid,
                selection_priority,
                selection_rule,
            ),
        )
        closing_row = cur.fetchone()
        closing_action = "upserted"
        if not closing_row:
            cur.execute(
                """
                SELECT id, employee_id, checkout_at, overtime_minutes, policy_priority, closer_selection_rule
                FROM site_daily_closing_ot
                WHERE tenant_id = %s
                  AND site_id = %s
                  AND work_date = %s
                LIMIT 1
                """,
                (tenant_id, site_id, work_date),
            )
            closing_row = cur.fetchone()
            closing_action = "kept_existing"

        overtime_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO soc_overtime_approvals (
                id, tenant_id, employee_id, site_id, work_date, approved_minutes, overtime_units, reason,
                source_event_uid, source, ticket_id, overtime_source, overtime_policy, closer_user_id,
                raw_minutes_total, overtime_hours_step, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s, 'ATTENDANCE_CLOSE', NULL, 'ATTENDANCE_CLOSE', 'PAYROLL_CLOSE_RULE', %s,
                %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (source_event_uid)
            DO UPDATE SET
                employee_id = EXCLUDED.employee_id,
                site_id = EXCLUDED.site_id,
                approved_minutes = EXCLUDED.approved_minutes,
                overtime_units = EXCLUDED.overtime_units,
                reason = EXCLUDED.reason,
                source = EXCLUDED.source,
                overtime_source = EXCLUDED.overtime_source,
                overtime_policy = EXCLUDED.overtime_policy,
                closer_user_id = EXCLUDED.closer_user_id,
                raw_minutes_total = EXCLUDED.raw_minutes_total,
                overtime_hours_step = EXCLUDED.overtime_hours_step,
                updated_at = timezone('utc', now())
            RETURNING id
            """,
            (
                overtime_id,
                tenant_id,
                employee_id,
                site_id,
                work_date,
                approved_minutes,
                overtime_hours_step,
                overtime_reason[:300],
                closing_uid,
                employee_id,
                raw_minutes_total,
                overtime_hours_step,
            ),
        )
        overtime_row = cur.fetchone()

        cur.execute(
            """
            SELECT id, ticket_id, overtime_hours_step, source_event_uid
            FROM soc_overtime_approvals
            WHERE tenant_id = %s
              AND employee_id = %s
              AND work_date = %s
              AND COALESCE(overtime_source, 'SOC_TICKET') = 'SOC_TICKET'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (tenant_id, employee_id, work_date),
        )
        soc_priority_row = cur.fetchone()

    _write_overtime_audit(
        conn,
        tenant_id=tenant_id,
        action_type="ATTENDANCE_CLOSE_OT_APPLIED",
        entity_id=str(overtime_row["id"]) if overtime_row else "",
        before_json=None,
        after_json={
            "source_event_uid": source_event_uid,
            "selection_rule": selection_rule,
            "selection_priority": selection_priority,
            "work_date": work_date.isoformat(),
            "overtime_hours_step": overtime_hours_step,
            "approved_minutes": approved_minutes,
            "raw_minutes_total": raw_minutes_total,
            "closing_action": closing_action,
        },
    )

    if soc_priority_row:
        _write_overtime_audit(
            conn,
            tenant_id=tenant_id,
            action_type="ATTENDANCE_CLOSE_OT_SUPERSEDED_BY_SOC",
            entity_id=str(overtime_row["id"]) if overtime_row else "",
            before_json={
                "attendance_close_overtime_id": str(overtime_row["id"]) if overtime_row else "",
                "attendance_close_hours_step": overtime_hours_step,
            },
            after_json={
                "soc_overtime_id": str(soc_priority_row["id"]),
                "soc_ticket_id": soc_priority_row["ticket_id"],
                "soc_hours_step": float(soc_priority_row["overtime_hours_step"] or 0),
                "policy": "SOC_TICKET_FIRST",
                "work_date": work_date.isoformat(),
            },
        )

    return {
        "closing_ot": True,
        "applied": True,
        "work_date": work_date.isoformat(),
        "selection_rule": selection_rule,
        "selection_priority": selection_priority,
        "closing_action": closing_action,
        "closing_record_id": str(closing_row["id"]) if closing_row else "",
        "employee_id": str(employee_id),
        "selected_employee_id": str(selected_employee_id),
        "checkout_at": checkout_at_utc.isoformat(),
        "raw_minutes_total": raw_minutes_total,
        "approved_minutes": approved_minutes,
        "overtime_hours_step": overtime_hours_step,
        "overtime_source": "ATTENDANCE_CLOSE",
        "overtime_policy": "PAYROLL_CLOSE_RULE",
        "closer_user_id": str(employee_id),
        "soc_priority_exists": bool(soc_priority_row),
        "soc_priority_overtime_id": str(soc_priority_row["id"]) if soc_priority_row else "",
    }
