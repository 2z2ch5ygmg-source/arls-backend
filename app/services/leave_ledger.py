from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .groupware_foundation import GroupwareAuditService

logger = logging.getLogger(__name__)

DEFAULT_ANNUAL_POLICY_KEY = "annual_default"
DEFAULT_ANNUAL_POLICY_NAME = "기본 연차 정책"
DEFAULT_ANNUAL_ALLOWANCE_DAYS = Decimal("15.0")
LEAVE_CONSUMING_TYPES = {"annual", "half", "sick", "other", "early_leave"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utc_now().date()


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def _round_decimal(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.1")))


def _normalize_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return None


def calculate_leave_duration_days(start_at: Any, end_at: Any, half_day_slot: str | None) -> Decimal:
    start_date = _normalize_date(start_at)
    end_date = _normalize_date(end_at)
    if not start_date or not end_date:
        return Decimal("0")
    if half_day_slot and start_date == end_date:
        return Decimal("0.5")
    days = max((end_date - start_date).days + 1, 0)
    return Decimal(str(days))


def bucket_leave_duration_by_year(start_at: Any, end_at: Any, half_day_slot: str | None) -> dict[int, Decimal]:
    start_date = _normalize_date(start_at)
    end_date = _normalize_date(end_at)
    if not start_date or not end_date or end_date < start_date:
        return {}
    if half_day_slot and start_date == end_date:
        return {start_date.year: Decimal("0.5")}

    buckets: dict[int, Decimal] = {}
    current = start_date
    while current <= end_date:
        buckets[current.year] = buckets.get(current.year, Decimal("0")) + Decimal("1.0")
        current += timedelta(days=1)
    return buckets


def ensure_default_leave_policy(conn, *, tenant_id: str, actor_user_id: str | None = None) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_policies (
                id,
                tenant_id,
                policy_key,
                display_name,
                rules_json,
                is_active,
                created_by,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s::jsonb, TRUE, %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, policy_key)
            DO UPDATE
            SET display_name = EXCLUDED.display_name,
                rules_json = EXCLUDED.rules_json,
                is_active = TRUE,
                updated_at = timezone('utc', now())
            RETURNING id, tenant_id, policy_key, display_name, rules_json, is_active
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                DEFAULT_ANNUAL_POLICY_KEY,
                DEFAULT_ANNUAL_POLICY_NAME,
                '{"default_annual_days": 15, "consuming_leave_types": ["annual", "half", "sick", "other", "early_leave"]}',
                actor_user_id,
            ),
        )
        row = cur.fetchone()
    return dict(row or {})


def ensure_default_leave_grant(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    grant_year: int,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    policy = ensure_default_leave_policy(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    reference_key = f"annual_default:{grant_year}"
    effective_from = date(grant_year, 1, 1)
    effective_to = date(grant_year, 12, 31)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_grants (
                id,
                tenant_id,
                policy_id,
                employee_id,
                grant_type,
                granted_days,
                granted_hours,
                effective_from,
                effective_to,
                reference_key,
                meta_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, 'annual', %s, 0, %s, %s, %s, '{}'::jsonb, timezone('utc', now())
            )
            ON CONFLICT (tenant_id, employee_id, reference_key)
            DO UPDATE
            SET granted_days = EXCLUDED.granted_days,
                effective_to = EXCLUDED.effective_to
            RETURNING id, policy_id, employee_id, granted_days, effective_from, effective_to, reference_key
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                policy.get("id"),
                employee_id,
                DEFAULT_ANNUAL_ALLOWANCE_DAYS,
                effective_from,
                effective_to,
                reference_key,
            ),
        )
        row = cur.fetchone()
    return dict(row or {})


def list_leave_policies(conn, *, tenant_id: str, actor_user_id: str | None = None) -> list[dict[str, Any]]:
    ensure_default_leave_policy(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   policy_key,
                   display_name,
                   rules_json,
                   is_active,
                   created_at,
                   updated_at
            FROM leave_policies
            WHERE tenant_id = %s
            ORDER BY created_at ASC
            """,
            (tenant_id,),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows


def _aggregate_leave_balance_components(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    policy_id: str,
    grant_year: int,
) -> dict[str, Decimal]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                COALESCE(SUM(granted_days), 0) AS granted_days
            FROM leave_grants
            WHERE tenant_id = %s
              AND employee_id = %s
              AND policy_id = %s
              AND EXTRACT(YEAR FROM effective_from) = %s
            """,
            (tenant_id, employee_id, policy_id, grant_year),
        )
        grant_row = cur.fetchone() or {}

        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN entry_type = 'consume' THEN amount ELSE 0 END), 0) AS consumed_days,
                COALESCE(SUM(CASE WHEN entry_type = 'restore' THEN amount ELSE 0 END), 0) AS restored_days,
                COALESCE(SUM(CASE WHEN entry_type = 'grant' THEN amount ELSE 0 END), 0) AS granted_ledger_days
            FROM leave_ledger
            WHERE tenant_id = %s
              AND employee_id = %s
              AND policy_id = %s
              AND EXTRACT(YEAR FROM effective_date) = %s
            """,
            (tenant_id, employee_id, policy_id, grant_year),
        )
        ledger_row = cur.fetchone() or {}

    return {
        "granted_days": _decimal(grant_row.get("granted_days")),
        "consumed_days": _decimal(ledger_row.get("consumed_days")),
        "restored_days": _decimal(ledger_row.get("restored_days")),
        "granted_ledger_days": _decimal(ledger_row.get("granted_ledger_days")),
    }


def _upsert_leave_balance_snapshot(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    policy_id: str,
    snapshot_date: date,
    remaining_days: Decimal,
    remaining_hours: Decimal = Decimal("0"),
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_balance_snapshots (
                id,
                tenant_id,
                employee_id,
                policy_id,
                snapshot_date,
                remaining_days,
                remaining_hours,
                source_revision,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (tenant_id, employee_id, policy_id, snapshot_date)
            DO UPDATE
            SET remaining_days = EXCLUDED.remaining_days,
                remaining_hours = EXCLUDED.remaining_hours,
                source_revision = EXCLUDED.source_revision
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                employee_id,
                policy_id,
                snapshot_date,
                remaining_days,
                remaining_hours,
                f"leave-ledger:{snapshot_date.isoformat()}",
            ),
        )


def compute_employee_leave_balance_summary(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    grant_year: int | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    target_year = int(grant_year or _today().year)
    policy = ensure_default_leave_policy(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    ensure_default_leave_grant(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        grant_year=target_year,
        actor_user_id=actor_user_id,
    )
    components = _aggregate_leave_balance_components(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        policy_id=str(policy.get("id") or ""),
        grant_year=target_year,
    )
    granted_days = components["granted_days"] + components["granted_ledger_days"]
    used_days = max(components["consumed_days"] - components["restored_days"], Decimal("0"))
    remaining_days = max(granted_days - used_days, Decimal("0"))
    _upsert_leave_balance_snapshot(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        policy_id=str(policy.get("id") or ""),
        snapshot_date=_today(),
        remaining_days=remaining_days,
    )
    return {
        "tenant_id": tenant_id,
        "employee_id": employee_id,
        "policy_id": policy.get("id"),
        "policy_key": policy.get("policy_key"),
        "policy_name": policy.get("display_name"),
        "year": target_year,
        "granted_days": _round_decimal(granted_days),
        "used_days": _round_decimal(used_days),
        "remaining_days": _round_decimal(remaining_days),
        "restored_days": _round_decimal(components["restored_days"]),
    }


def _find_approval_document_id_for_leave(conn, *, tenant_id: str, leave_request_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM approval_documents
            WHERE tenant_id = %s
              AND legacy_source_type = 'leave_request'
              AND legacy_source_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, leave_request_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    return str(row.get("id") or "").strip() or None


def _leave_ledger_entry_exists(conn, *, tenant_id: str, employee_id: str, reference_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM leave_ledger
            WHERE tenant_id = %s
              AND employee_id = %s
              AND reference_key = %s
            LIMIT 1
            """,
            (tenant_id, employee_id, reference_key),
        )
        row = cur.fetchone()
    return bool(row)


def _insert_leave_ledger_entry(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    policy_id: str,
    approval_document_id: str | None,
    legacy_leave_request_id: str,
    reference_key: str,
    entry_type: str,
    direction: str,
    amount: Decimal,
    effective_date: date,
    reason: str,
    actor_user_id: str | None,
    meta: dict[str, Any] | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO leave_ledger (
                id,
                tenant_id,
                employee_id,
                policy_id,
                approval_document_id,
                legacy_leave_request_id,
                reference_key,
                entry_type,
                direction,
                unit,
                amount,
                effective_date,
                reason,
                balance_after,
                meta_json,
                created_by,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'day', %s, %s, %s, NULL, %s::jsonb, %s, timezone('utc', now())
            )
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                employee_id,
                policy_id,
                approval_document_id,
                legacy_leave_request_id,
                reference_key,
                entry_type,
                direction,
                amount,
                effective_date,
                reason,
                json.dumps(meta or {}, ensure_ascii=False, default=str),
                actor_user_id,
            ),
        )


def sync_leave_request_ledger(
    conn,
    *,
    leave_row: dict[str, Any],
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, Any] | None:
    tenant_id = str(leave_row.get("tenant_id") or "").strip()
    employee_id = str(leave_row.get("employee_id") or "").strip()
    leave_request_id = str(leave_row.get("id") or "").strip()
    leave_type = str(leave_row.get("leave_type") or "").strip().lower()
    status_value = str(leave_row.get("status") or "").strip().lower()
    start_date = _normalize_date(leave_row.get("start_at"))
    end_date = _normalize_date(leave_row.get("end_at"))
    half_day_slot = str(leave_row.get("half_day_slot") or "").strip().lower() or None

    if not tenant_id or not employee_id or not leave_request_id or not start_date or not end_date:
        return None
    if leave_type not in LEAVE_CONSUMING_TYPES:
        return None

    yearly_buckets = bucket_leave_duration_by_year(start_date, end_date, half_day_slot)
    if not yearly_buckets:
        return None

    policy = ensure_default_leave_policy(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    approval_document_id = _find_approval_document_id_for_leave(conn, tenant_id=tenant_id, leave_request_id=leave_request_id)

    if status_value == "approved":
        for year, amount in yearly_buckets.items():
            ensure_default_leave_grant(
                conn,
                tenant_id=tenant_id,
                employee_id=employee_id,
                grant_year=year,
                actor_user_id=actor_user_id,
            )
            reference_key = f"leave:{leave_request_id}:consume:{year}"
            if _leave_ledger_entry_exists(conn, tenant_id=tenant_id, employee_id=employee_id, reference_key=reference_key):
                continue
            _insert_leave_ledger_entry(
                conn,
                tenant_id=tenant_id,
                employee_id=employee_id,
                policy_id=str(policy.get("id") or ""),
                approval_document_id=approval_document_id,
                legacy_leave_request_id=leave_request_id,
                reference_key=reference_key,
                entry_type="consume",
                direction="debit",
                amount=amount,
                effective_date=date(year, 1, 1) if start_date.year != year else start_date,
                reason=f"leave_request:{leave_request_id}",
                actor_user_id=actor_user_id,
                meta={"leave_type": leave_type, "status": status_value},
            )
    elif status_value in {"rejected", "cancelled", "recalled"}:
        for year, amount in yearly_buckets.items():
            consume_reference_key = f"leave:{leave_request_id}:consume:{year}"
            restore_reference_key = f"leave:{leave_request_id}:restore:{year}"
            if not _leave_ledger_entry_exists(conn, tenant_id=tenant_id, employee_id=employee_id, reference_key=consume_reference_key):
                continue
            if _leave_ledger_entry_exists(conn, tenant_id=tenant_id, employee_id=employee_id, reference_key=restore_reference_key):
                continue
            _insert_leave_ledger_entry(
                conn,
                tenant_id=tenant_id,
                employee_id=employee_id,
                policy_id=str(policy.get("id") or ""),
                approval_document_id=approval_document_id,
                legacy_leave_request_id=leave_request_id,
                reference_key=restore_reference_key,
                entry_type="restore",
                direction="credit",
                amount=amount,
                effective_date=date(year, 1, 1) if start_date.year != year else start_date,
                reason=f"leave_request_restore:{leave_request_id}",
                actor_user_id=actor_user_id,
                meta={"leave_type": leave_type, "status": status_value},
            )
    else:
        return None

    for year in yearly_buckets:
        compute_employee_leave_balance_summary(
            conn,
            tenant_id=tenant_id,
            employee_id=employee_id,
            grant_year=year,
            actor_user_id=actor_user_id,
        )

    GroupwareAuditService(conn).write_event(
        tenant_id=tenant_id,
        module_key="leave-ledger",
        action_type="synced",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type="leave_request",
        target_id=leave_request_id,
        detail={
            "leave_type": leave_type,
            "status": status_value,
            "years": sorted(yearly_buckets.keys()),
        },
    )

    return compute_employee_leave_balance_summary(
        conn,
        tenant_id=tenant_id,
        employee_id=employee_id,
        grant_year=start_date.year,
        actor_user_id=actor_user_id,
    )


def list_holiday_calendar_entries(
    conn,
    *,
    tenant_id: str,
    year: int | None = None,
) -> list[dict[str, Any]]:
    target_year = int(year or _today().year)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   holiday_date,
                   holiday_name,
                   region_code,
                   meta_json
            FROM holiday_calendar
            WHERE tenant_id = %s
              AND EXTRACT(YEAR FROM holiday_date) = %s
            ORDER BY holiday_date ASC
            """,
            (tenant_id, target_year),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows


def list_leave_blackout_rules(
    conn,
    *,
    tenant_id: str,
    site_id: str | None = None,
    year: int | None = None,
    month: int | None = None,
) -> list[dict[str, Any]]:
    clauses = ["tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if site_id:
        clauses.append("(site_id = %s OR site_id IS NULL)")
        params.append(site_id)
    if year:
        clauses.append(
            """
            (
              EXTRACT(YEAR FROM starts_on) = %s
              OR EXTRACT(YEAR FROM ends_on) = %s
            )
            """
        )
        params.extend([int(year), int(year)])
    if month:
        clauses.append(
            """
            (
              EXTRACT(MONTH FROM starts_on) = %s
              OR EXTRACT(MONTH FROM ends_on) = %s
            )
            """
        )
        params.extend([int(month), int(month)])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id,
                   policy_id,
                   site_id,
                   title,
                   starts_on,
                   ends_on,
                   rule_type,
                   meta_json
            FROM leave_blackout_rules
            WHERE {' AND '.join(clauses)}
            ORDER BY starts_on ASC, ends_on ASC
            """,
            tuple(params),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows
