from __future__ import annotations

import hashlib
import hmac
import json
import math
import uuid
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, status

from ...config import settings
from ...db import get_connection
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...integration_center import (
    APPLE_REPORT_DAYTIME_ENABLED,
    APPLE_REPORT_OT_ENABLED,
    APPLE_REPORT_OVERNIGHT_ENABLED,
    APPLE_REPORT_TOTAL_LATE_ENABLED,
    PAYROLL_SHEET_ENABLED,
    SHEETS_SYNC_ENABLED,
    SOC_INTEGRATION_ENABLED,
    AuditLogService,
    EventIdempotencyStore,
    HrDomainApplier,
    SheetsAdapter,
    SheetsSyncOrchestrator,
    SocEventReceiver,
    build_feature_flag_defaults,
    normalize_flag_key,
)
from ...integration_center.feature_flags import FeatureFlagService
from ...schemas import (
    GoogleSheetProfileCreate,
    GoogleSheetProfileOut,
    GoogleSheetSyncLogOut,
    GoogleSheetProfileUpdate,
    GoogleSheetSyncOut,
    GoogleSheetSyncRequest,
    IntegrationFeatureFlagOut,
    IntegrationFeatureFlagUpdate,
    SocEventEnvelopeIn,
    SocEventIn,
    SocEventIngestOut,
    SupportSheetWebhookIn,
)
from ...services.closing_overtime import apply_closing_overtime_from_checkout
from ...services.p1_schedule import (
    build_apple_total_shift_rows,
    build_duty_log,
    generate_apple_daytime_shift,
    list_apple_late_shift_logs,
    list_apple_report_overnight_records,
    list_daily_event_logs,
    list_support_assignments,
    resolve_support_entries_to_assignments,
    upsert_apple_report_overnight_record,
    upsert_pending_apple_daytime_ot_from_checkout,
)
from ...utils.permissions import normalize_role
from ...utils.tenant_context import canonical_tenant_identifier, fetch_tenant_row_any, resolve_scoped_tenant

router = APIRouter(prefix="/integrations", tags=["integrations"])

KST = timezone(timedelta(hours=9))
KST_CLOSING_CUTOFF = time(hour=22, minute=10)

SOC_LEAVE_EVENT_TYPES = {
    "leave_approved",
    "leave_override",
    "annual_leave_approved",
    "sick_leave_approved",
    "early_leave_approved",
    "dayoff_approved",
}
SOC_OVERNIGHT_EVENT_TYPES = {
    "overnight_approved",
    "night_work_approved",
    "apple_overnight_approved",
}
SOC_OVERTIME_EVENT_TYPES = {
    "overtime_approved",
    "ot_approved",
    "extra_work_approved",
}
SOC_ATTENDANCE_CHECKIN_EVENT_TYPES = {"attendance_check_in", "check_in"}
SOC_ATTENDANCE_CHECKOUT_EVENT_TYPES = {"attendance_check_out", "check_out", "checkout"}
SOC_CLOSING_EVENT_TYPES = SOC_ATTENDANCE_CHECKOUT_EVENT_TYPES | {"closing_checkout", "closing_ot"}
SOC_WEBHOOK_EVENT_TYPE_MAP = {
    "OVERTIME_APPROVED": "overtime_approved",
    "OVERNIGHT_APPROVED": "overnight_approved",
    "LEAVE_APPROVED": "leave_approved",
}

FEATURE_FLAG_DEFAULTS = build_feature_flag_defaults(settings)

PROFILE_SCOPE_APPLE_OVERNIGHT = "APPLE_OVERNIGHT"
PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME = "PAYROLL_LEAVE_OVERTIME"
PROFILE_SCOPE_APPLE_DAYTIME = "APPLE_DAYTIME"
PROFILE_SCOPE_APPLE_DAYTIME_P1 = "APPLE_DAYTIME_P1"  # legacy alias
PROFILE_SCOPE_APPLE_OT = "APPLE_OT"
PROFILE_SCOPE_APPLE_TOTAL_LATE = "APPLE_TOTAL_LATE"
PROFILE_SCOPE_DUTY_LOG = "DUTY_LOG"
PROFILE_SCOPE_SUPPORT_ASSIGNMENT = "SUPPORT_ASSIGNMENT"
PROFILE_SCOPE_ALIASES = {
    "APPLE": PROFILE_SCOPE_APPLE_OVERNIGHT,
    "OVERNIGHT": PROFILE_SCOPE_APPLE_OVERNIGHT,
    "APPLE_OVERNIGHT": PROFILE_SCOPE_APPLE_OVERNIGHT,
    "APPLE_DAYTIME": PROFILE_SCOPE_APPLE_DAYTIME,
    "DAYTIME": PROFILE_SCOPE_APPLE_DAYTIME,
    "APPLE_DAYTIME_P1": PROFILE_SCOPE_APPLE_DAYTIME,
    "APPLE_OT": PROFILE_SCOPE_APPLE_OT,
    "OT": PROFILE_SCOPE_APPLE_OT,
    "APPLE_TOTAL_LATE": PROFILE_SCOPE_APPLE_TOTAL_LATE,
    "TOTAL_LATE": PROFILE_SCOPE_APPLE_TOTAL_LATE,
    "DUTY": PROFILE_SCOPE_DUTY_LOG,
    "DUTY_LOG": PROFILE_SCOPE_DUTY_LOG,
    "SUPPORT": PROFILE_SCOPE_SUPPORT_ASSIGNMENT,
    "SUPPORT_ASSIGNMENT": PROFILE_SCOPE_SUPPORT_ASSIGNMENT,
    "SHEET_TO_DB_SUPPORT": PROFILE_SCOPE_SUPPORT_ASSIGNMENT,
    "PAYROLL": PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME,
    "PAYROLL_LEAVE_OT": PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME,
    "PAYROLL_LEAVE_OVERTIME": PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME,
}

PROFILE_TYPE_KEY_ROW = "KEY_ROW"
PROFILE_TYPE_NAMED_RANGE = "NAMED_RANGE"
PROFILE_TYPE_TO_SYNC_MODE = {
    PROFILE_TYPE_KEY_ROW: "key_row",
    PROFILE_TYPE_NAMED_RANGE: "named_range",
}
SYNC_MODE_TO_PROFILE_TYPE = {value: key for key, value in PROFILE_TYPE_TO_SYNC_MODE.items()}

SYNC_INTENT_APPLE_OVERNIGHT = "apple_overnight"
SYNC_INTENT_APPLE_DAYTIME = "apple_daytime"
SYNC_INTENT_APPLE_OT = "apple_ot"
SYNC_INTENT_APPLE_TOTAL_LATE = "apple_total_late"
SYNC_INTENT_PAYROLL = "payroll_leave_overtime"


def _normalize_profile_scope(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    return PROFILE_SCOPE_ALIASES.get(normalized, PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME)


def _scope_to_sync_intent(scope: str | None) -> str:
    normalized = _normalize_profile_scope(scope)
    if normalized == PROFILE_SCOPE_APPLE_OVERNIGHT:
        return SYNC_INTENT_APPLE_OVERNIGHT
    if normalized == PROFILE_SCOPE_APPLE_DAYTIME:
        return SYNC_INTENT_APPLE_DAYTIME
    if normalized == PROFILE_SCOPE_APPLE_OT:
        return SYNC_INTENT_APPLE_OT
    if normalized == PROFILE_SCOPE_APPLE_TOTAL_LATE:
        return SYNC_INTENT_APPLE_TOTAL_LATE
    return SYNC_INTENT_PAYROLL


def _is_sync_intent_enabled(conn, tenant_id, intent: str) -> bool:
    if intent == SYNC_INTENT_APPLE_OVERNIGHT:
        return _is_feature_enabled(conn, tenant_id, APPLE_REPORT_OVERNIGHT_ENABLED)
    if intent == SYNC_INTENT_APPLE_DAYTIME:
        return _is_feature_enabled(conn, tenant_id, APPLE_REPORT_DAYTIME_ENABLED)
    if intent == SYNC_INTENT_APPLE_OT:
        return _is_feature_enabled(conn, tenant_id, APPLE_REPORT_OT_ENABLED)
    if intent == SYNC_INTENT_APPLE_TOTAL_LATE:
        return _is_feature_enabled(conn, tenant_id, APPLE_REPORT_TOTAL_LATE_ENABLED)
    return _is_feature_enabled(conn, tenant_id, PAYROLL_SHEET_ENABLED)


def _normalize_profile_type(value: str | None) -> str:
    normalized = str(value or "").strip().upper()
    if normalized in PROFILE_TYPE_TO_SYNC_MODE:
        return normalized
    if normalized in SYNC_MODE_TO_PROFILE_TYPE:
        return SYNC_MODE_TO_PROFILE_TYPE[normalized]
    return PROFILE_TYPE_KEY_ROW


def _resolve_profile_scope_from_row(row: dict[str, Any]) -> str:
    options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    raw_scope = str(options.get("profile_scope") or "").strip()
    if raw_scope:
        return _normalize_profile_scope(raw_scope)

    has_schedule = bool(str(row.get("worksheet_schedule") or "").strip())
    has_overtime = bool(str(row.get("worksheet_overtime") or "").strip())
    has_overnight = bool(str(row.get("worksheet_overnight") or "").strip())
    if has_overnight and not has_schedule and not has_overtime:
        return PROFILE_SCOPE_APPLE_OVERNIGHT
    return PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME


def _resolve_profile_type_from_row(row: dict[str, Any]) -> str:
    options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    raw_mode = str(options.get("sync_mode") or row.get("auth_mode") or "").strip().lower()
    if raw_mode in SYNC_MODE_TO_PROFILE_TYPE:
        return SYNC_MODE_TO_PROFILE_TYPE[raw_mode]
    return PROFILE_TYPE_KEY_ROW


def _normalize_site_codes(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    candidates: list[str] = []
    if isinstance(value, str):
        candidates = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value]
    else:
        return []

    normalized: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if not item:
            continue
        code = item.upper()
        if code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return normalized


def _resolve_profile_site_codes_from_row(row: dict[str, Any]) -> list[str]:
    options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    return _normalize_site_codes(options.get("site_codes"))


def _filter_rows_by_site_codes(
    rows_by_section: dict[str, list[dict[str, Any]]],
    site_codes: list[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized_codes = _normalize_site_codes(site_codes)
    if not normalized_codes:
        return rows_by_section

    allow = set(normalized_codes)

    def pick_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for row in rows or []:
            site_code = str(row.get("site_code") or "").strip().upper()
            if site_code in allow:
                output.append(row)
        return output

    return {
        "schedule": pick_rows(rows_by_section.get("schedule") or []),
        "overtime": pick_rows(rows_by_section.get("overtime") or []),
        "overnight": pick_rows(rows_by_section.get("overnight") or []),
    }


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    return value


def _safe_json(value: Any) -> str:
    serialized = _serialize_value(value)
    return json.dumps(serialized, ensure_ascii=False, default=str)


def _normalize_event_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    return normalized


def _canonical_key(value: str) -> str:
    return "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())


def _pick_from_mapping(data: dict[str, Any] | None, *keys: str) -> Any | None:
    if not isinstance(data, dict):
        return None
    key_set = {_canonical_key(item) for item in keys}
    for key, value in data.items():
        if _canonical_key(str(key)) in key_set and value not in (None, ""):
            return value
    return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _as_id_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            text = _as_text(item)
            if text:
                result.append(text)
        return result
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
            except Exception:
                parsed = None
            if isinstance(parsed, list):
                return _as_id_list(parsed)
        return [part.strip() for part in raw.split(",") if part.strip()]
    text = _as_text(value)
    return [text] if text else []


def _extract_id_list_from_fields(template_fields: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        value = _pick_from_mapping(template_fields, key)
        ids = _as_id_list(value)
        if ids:
            return ids
    return []


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(KST).date()
    text = _as_text(value)
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = _as_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_soc_webhook_event_type(value: str | None) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if normalized in SOC_WEBHOOK_EVENT_TYPE_MAP:
        return SOC_WEBHOOK_EVENT_TYPE_MAP[normalized]
    return _normalize_event_type(normalized)


def _to_internal_soc_event(payload: SocEventEnvelopeIn) -> SocEventIn:
    template_fields_raw = payload.template_fields if isinstance(payload.template_fields, dict) else {}
    template_fields = {str(key): value for key, value in template_fields_raw.items()}
    ticket = payload.ticket
    canonical_event_type = _normalize_soc_webhook_event_type(payload.event_type)

    tenant_code = _as_text(ticket.tenant_id) or _as_text(
        _pick_from_mapping(template_fields, "tenant_code", "tenantCode", "tenant_id", "tenantId", "테넌트코드")
    )
    if not tenant_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ticket.tenant_id is required")

    employee_code = _as_text(
        _pick_from_mapping(
            template_fields,
            "employee_code",
            "employeeCode",
            "emp_code",
            "empCode",
            "사번",
            "직원코드",
            "근무자코드",
        )
    )
    if not employee_code:
        if canonical_event_type in SOC_LEAVE_EVENT_TYPES or canonical_event_type in SOC_OVERTIME_EVENT_TYPES:
            employee_code = "__SOC_MULTI__"
        elif canonical_event_type in SOC_OVERNIGHT_EVENT_TYPES:
            employee_code = "__SOC_OVERNIGHT__"

    if not employee_code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="template_fields.employee_code is required")

    site_code = _as_text(ticket.site_id) or _as_text(
        _pick_from_mapping(template_fields, "site_code", "siteCode", "site_id", "siteId", "현장코드")
    )
    company_code = _as_text(
        _pick_from_mapping(template_fields, "company_code", "companyCode", "company_id", "companyId", "회사코드")
    )
    work_date = _as_date(
        _pick_from_mapping(template_fields, "work_date", "workDate", "date", "근무일", "근무일자")
    )
    approved_minutes = _as_int(
        _pick_from_mapping(
            template_fields,
            "approved_minutes",
            "approvedMinutes",
            "minutes",
            "overtime_minutes",
            "overtimeMinutes",
            "ot_minutes",
            "연장분",
            "초과근무분",
        )
    )
    leave_type = _as_text(_pick_from_mapping(template_fields, "leave_type", "leaveType", "휴가유형", "휴가타입"))
    reason = (
        _as_text(ticket.reason)
        or _as_text(ticket.memo)
        or _as_text(_pick_from_mapping(template_fields, "reason", "memo", "사유", "메모"))
    )
    occurred_at = (
        _as_datetime(ticket.decision_at)
        or _as_datetime(payload.occurred_at)
        or _as_datetime(_pick_from_mapping(template_fields, "decision_at", "decisionAt", "approvedAt", "occurred_at"))
    )

    metadata = {
        "ticket_id": ticket.id,
        "template_type": ticket.template_type,
        "tenant_id": tenant_code,
        "site_id": site_code,
        "status": ticket.status,
        "decision_at": ticket.decision_at.isoformat() if isinstance(ticket.decision_at, datetime) else _as_text(ticket.decision_at),
        "approver_user_id": ticket.approver_user_id,
        "reporter_user_id": ticket.reporter_user_id,
        "source": _as_text(payload.source) or "SOC",
    }

    return SocEventIn(
        event_uid=payload.event_id,
        event_type=canonical_event_type,
        tenant_code=tenant_code.upper(),
        employee_code=employee_code,
        site_code=site_code,
        company_code=company_code,
        work_date=work_date,
        occurred_at=occurred_at,
        leave_type=leave_type,
        approved_minutes=approved_minutes,
        reason=reason,
        metadata=metadata,
        payload=template_fields,
    )


def _normalize_leave_type(value: str | None, event_type: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        if "sick" in event_type:
            raw = "sick"
        elif "half" in event_type:
            raw = "half"
        elif "early" in event_type:
            raw = "annual"
        else:
            raw = "annual"

    alias = {
        "annual": "annual",
        "dayoff": "annual",
        "day_off": "annual",
        "day-off": "annual",
        "holiday": "annual",
        "early_leave": "annual",
        "early": "annual",
        "sick": "sick",
        "sick_leave": "sick",
        "half": "half",
        "half_day": "half",
        "half-day": "half",
        "other": "other",
    }
    return alias.get(raw, "annual")


def _extract_half_day_slot(payload: SocEventIn) -> str | None:
    candidate = payload.metadata.get("half_day_slot")
    if candidate is None:
        candidate = payload.payload.get("half_day_slot")
    normalized = str(candidate or "").strip().lower()
    if normalized in {"am", "pm"}:
        return normalized
    return None


def _extract_int(payload: SocEventIn, *keys: str) -> int | None:
    for key in keys:
        if key in payload.metadata:
            try:
                return int(float(payload.metadata[key]))
            except Exception:
                pass
        if key in payload.payload:
            try:
                return int(float(payload.payload[key]))
            except Exception:
                pass
    return None


def _extract_float(payload: SocEventIn, *keys: str) -> float | None:
    for key in keys:
        if key in payload.metadata:
            try:
                return float(payload.metadata[key])
            except Exception:
                pass
        if key in payload.payload:
            try:
                return float(payload.payload[key])
            except Exception:
                pass
    return None


def _extract_bool(payload: SocEventIn, *keys: str) -> bool | None:
    for key in keys:
        if key in payload.metadata:
            return bool(payload.metadata[key])
        if key in payload.payload:
            return bool(payload.payload[key])
    return None


def _derive_work_date(payload: SocEventIn) -> date:
    if payload.work_date:
        return payload.work_date
    if payload.occurred_at:
        return payload.occurred_at.astimezone(KST).date()
    return datetime.now(KST).date()


def _derive_occurred_at(payload: SocEventIn, work_date: date) -> datetime:
    if payload.occurred_at:
        occurred_at = payload.occurred_at
        if occurred_at.tzinfo is None:
            return occurred_at.replace(tzinfo=timezone.utc)
        return occurred_at.astimezone(timezone.utc)
    return datetime.combine(work_date, time(hour=9, minute=0, tzinfo=KST)).astimezone(timezone.utc)


def _minutes_to_half_step_units(minutes: int) -> float:
    safe_minutes = max(0, int(minutes))
    if safe_minutes == 0:
        return 0.0
    return round(math.ceil(safe_minutes / 30.0) / 2.0, 2)


def _require_integration_manager(user: dict) -> str:
    role = normalize_role(user.get("role"))
    if role not in {"dev", "branch_manager"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return role


def _normalize_tenant_code(value: str | None) -> str:
    return canonical_tenant_identifier(value)


def _resolve_tenant_by_code(conn, tenant_code: str):
    row = fetch_tenant_row_any(conn, tenant_code)
    if not row:
        return None
    if not bool(row.get("is_active", True)) or bool(row.get("is_deleted", False)):
        return None
    return row


def _resolve_target_tenant(conn, user: dict, tenant_code: str | None):
    _require_integration_manager(user)
    return resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )


def _resolve_employee(conn, tenant_id, employee_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, company_id, site_id, employee_code, full_name,
                   external_employee_key, linked_employee_id
            FROM employees
            WHERE tenant_id = %s
              AND employee_code = %s
            LIMIT 1
            """,
            (tenant_id, employee_code),
        )
        return cur.fetchone()


def _resolve_employee_by_external_key(conn, *, tenant_id, site_id, external_key: str):
    key_text = str(external_key or "").strip()
    if not key_text:
        return None

    with conn.cursor() as cur:
        if site_id:
            cur.execute(
                """
                SELECT id, tenant_id, company_id, site_id, employee_code, full_name,
                       external_employee_key, linked_employee_id
                FROM employees
                WHERE tenant_id = %s
                  AND site_id = %s
                  AND (
                    linked_employee_id = %s
                    OR external_employee_key = %s
                    OR employee_code = %s
                  )
                ORDER BY CASE
                  WHEN linked_employee_id = %s THEN 1
                  WHEN external_employee_key = %s THEN 2
                  WHEN employee_code = %s THEN 3
                  ELSE 9
                END
                LIMIT 1
                """,
                (
                    tenant_id,
                    site_id,
                    key_text,
                    key_text,
                    key_text,
                    key_text,
                    key_text,
                    key_text,
                ),
            )
            matched = cur.fetchone()
            if matched:
                return matched

        cur.execute(
            """
            SELECT id, tenant_id, company_id, site_id, employee_code, full_name,
                   external_employee_key, linked_employee_id
            FROM employees
            WHERE tenant_id = %s
              AND (
                linked_employee_id = %s
                OR external_employee_key = %s
                OR employee_code = %s
              )
            ORDER BY CASE
              WHEN linked_employee_id = %s THEN 1
              WHEN external_employee_key = %s THEN 2
              WHEN employee_code = %s THEN 3
              ELSE 9
            END
            LIMIT 1
            """,
            (
                tenant_id,
                key_text,
                key_text,
                key_text,
                key_text,
                key_text,
                key_text,
            ),
        )
        return cur.fetchone()


def _extract_soc_employee_keys(payload: SocEventIn, event_type: str) -> list[str]:
    template_fields = payload.payload if isinstance(payload.payload, dict) else {}
    if event_type in SOC_LEAVE_EVENT_TYPES:
        return _extract_id_list_from_fields(
            template_fields,
            "internal_staff_employee_ids",
            "internalStaffEmployeeIds",
            "internal_staff_employee_id",
            "internalStaffEmployeeId",
        )
    if event_type in SOC_OVERTIME_EVENT_TYPES:
        return _extract_id_list_from_fields(
            template_fields,
            "target_employee_ids",
            "targetEmployeeIds",
            "target_employee_id",
            "targetEmployeeId",
        )
    if event_type in SOC_OVERNIGHT_EVENT_TYPES:
        return _extract_id_list_from_fields(
            template_fields,
            "internal_staff_employee_ids",
            "internalStaffEmployeeIds",
            "internal_staff_employee_id",
            "internalStaffEmployeeId",
            "target_employee_ids",
            "targetEmployeeIds",
            "target_employee_id",
            "targetEmployeeId",
        )
    return []


def _resolve_soc_target_employees(conn, *, tenant_id, site, payload: SocEventIn, event_type: str) -> list[dict[str, Any]]:
    target_keys = _extract_soc_employee_keys(payload, event_type)
    if not target_keys:
        raise ValueError("EMPLOYEE_NOT_FOUND")

    resolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    site_id = site["id"] if site else None
    for target_key in target_keys:
        employee = _resolve_employee_by_external_key(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            external_key=target_key,
        )
        if not employee:
            raise ValueError("EMPLOYEE_NOT_FOUND")
        employee_id = str(employee["id"])
        if employee_id in seen_ids:
            continue
        seen_ids.add(employee_id)
        resolved.append(employee)
    return resolved


def _resolve_site_by_code(conn, tenant_id, site_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, company_id, site_code, site_name, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s
              AND (
                site_code = %s
                OR id::text = %s
              )
            LIMIT 1
            """,
            (tenant_id, site_code, site_code),
        )
        return cur.fetchone()


def _resolve_site_by_id(conn, tenant_id, site_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, company_id, site_code, site_name, latitude, longitude, radius_meters
            FROM sites
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, site_id),
        )
        return cur.fetchone()


def _write_audit_log(
    conn,
    *,
    tenant_id=None,
    action_type: str,
    source: str = "hr",
    actor_user_id=None,
    actor_role: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    AuditLogService(conn).write(
        tenant_id=tenant_id,
        action_type=action_type,
        source=source,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type=target_type,
        target_id=target_id,
        detail=detail or {},
    )


def _write_sheets_sync_log(
    conn,
    *,
    tenant_id,
    profile_id: uuid.UUID,
    direction: str,
    ok: bool,
    error_message: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sheets_sync_log (
                id, tenant_id, profile_id, direction, status, error_message, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, timezone('utc', now()))
            """,
            (
                uuid.uuid4(),
                tenant_id,
                profile_id,
                direction,
                "SUCCESS" if ok else "FAIL",
                None if ok else error_message,
            ),
        )


def _get_feature_flag(conn, tenant_id, flag_key: str) -> bool | None:
    feature_flags = FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS)
    return feature_flags.get_override(tenant_id, flag_key)


def _is_feature_enabled(conn, tenant_id, flag_key: str) -> bool:
    feature_flags = FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS)
    return feature_flags.is_enabled(tenant_id, flag_key)


def _set_feature_flag(conn, tenant_id, flag_key: str, enabled: bool, updated_by=None) -> None:
    feature_flags = FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS)
    feature_flags.set_flag(tenant_id, flag_key, bool(enabled), updated_by=updated_by)


def _upsert_monthly_schedule(
    conn,
    tenant_id,
    company_id,
    site_id,
    employee_id,
    work_date: date,
    shift_type: str,
    *,
    source: str | None = None,
    source_ticket_id: int | None = None,
    schedule_note: str | None = None,
) -> dict[str, Any]:
    if not company_id or not site_id:
        raise ValueError("employee company/site mapping is missing")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, shift_type, company_id, site_id
            FROM monthly_schedules
            WHERE tenant_id = %s
              AND employee_id = %s
              AND schedule_date = %s
            LIMIT 1
            """,
            (tenant_id, employee_id, work_date),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute(
                """
                UPDATE monthly_schedules
                SET shift_type = %s,
                    company_id = %s,
                    site_id = %s,
                    source = COALESCE(%s, source),
                    source_ticket_id = COALESCE(%s, source_ticket_id),
                    schedule_note = COALESCE(%s, schedule_note)
                WHERE id = %s
                """,
                (
                    shift_type,
                    company_id,
                    site_id,
                    source,
                    source_ticket_id,
                    schedule_note,
                    existing["id"],
                ),
            )
            return {
                "action": "updated",
                "schedule_id": str(existing["id"]),
                "shift_type": shift_type,
                "schedule_date": work_date.isoformat(),
                "source": source,
                "source_ticket_id": source_ticket_id,
                "schedule_note": schedule_note,
            }

        cur.execute(
            """
            INSERT INTO monthly_schedules (
                tenant_id, company_id, site_id, employee_id, schedule_date, shift_type, source, source_ticket_id, schedule_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant_id,
                company_id,
                site_id,
                employee_id,
                work_date,
                shift_type,
                source,
                source_ticket_id,
                schedule_note,
            ),
        )
        inserted = cur.fetchone()
        return {
            "action": "inserted",
            "schedule_id": str(inserted["id"]) if inserted else "",
            "shift_type": shift_type,
            "schedule_date": work_date.isoformat(),
            "source": source,
            "source_ticket_id": source_ticket_id,
            "schedule_note": schedule_note,
        }


def _extract_ticket_id_from_payload(payload: SocEventIn) -> int | None:
    value = _pick_from_mapping(payload.metadata, "ticket_id", "ticketId")
    if value is None:
        ticket = payload.metadata.get("ticket")
        if isinstance(ticket, dict):
            value = _pick_from_mapping(ticket, "id", "ticket_id", "ticketId")
    if value is None:
        value = _pick_from_mapping(payload.payload if isinstance(payload.payload, dict) else {}, "ticket_id", "ticketId")
    return _as_int(value)


def _extract_request_date_from_payload(payload: SocEventIn) -> date:
    value = _pick_from_mapping(payload.payload if isinstance(payload.payload, dict) else {}, "request_date", "requestDate", "date", "work_date")
    extracted = _as_date(value)
    if extracted:
        return extracted
    return _derive_work_date(payload)


def _extract_leave_reason_text(payload: SocEventIn) -> str:
    value = _pick_from_mapping(
        payload.payload if isinstance(payload.payload, dict) else {},
        "request_reason",
        "requestReason",
        "leave_reason",
        "leaveReason",
        "reason",
    )
    return str(_as_text(value) or _as_text(payload.reason) or "").strip()


def _map_leave_reason(reason_text: str, fallback_leave_type: str | None, event_type: str) -> tuple[str, str, str]:
    normalized = str(reason_text or "").strip().lower().replace(" ", "")
    if "병가" in normalized:
        return "sick", "annual", "sick"
    if "조퇴" in normalized:
        return "early_leave", "annual", "early_leave"
    if "반차" in normalized:
        return "half", "half", "half"
    if "연차" in normalized:
        return "annual", "annual", "annual"

    fallback = _normalize_leave_type(fallback_leave_type, event_type)
    if fallback == "sick":
        return "sick", "annual", "sick"
    if fallback == "half":
        return "half", "half", "half"
    return "annual", "annual", "annual"


def _extract_overtime_minutes_total(payload: SocEventIn) -> int | None:
    if payload.approved_minutes is not None:
        return int(max(0, int(payload.approved_minutes)))

    fields = payload.payload if isinstance(payload.payload, dict) else {}
    hours = _as_int(_pick_from_mapping(fields, "request_hours", "requestHours", "hours"))
    minutes = _as_int(_pick_from_mapping(fields, "request_minutes", "requestMinutes", "minutes"))
    total_minutes = _as_int(
        _pick_from_mapping(
            fields,
            "minutes_total",
            "minutesTotal",
            "total_minutes",
            "totalMinutes",
            "approved_minutes",
            "approvedMinutes",
            "overtime_minutes",
            "overtimeMinutes",
        )
    )

    if hours is not None or minutes is not None:
        safe_hours = max(0, int(hours or 0))
        safe_minutes = max(0, int(minutes or 0))
        return safe_hours * 60 + safe_minutes
    if total_minutes is not None:
        return max(0, int(total_minutes))
    return None


def _minutes_to_soc_ticket_overtime_step(minutes_total: int) -> float:
    safe_minutes = max(0, int(minutes_total))
    if safe_minutes <= 30:
        return 0.0
    return round(math.ceil(safe_minutes / 30.0) * 0.5, 2)


def _extract_overnight_need_count(payload: SocEventIn) -> int:
    fields = payload.payload if isinstance(payload.payload, dict) else {}
    total_need = _as_int(_pick_from_mapping(fields, "total_need_count", "totalNeedCount"))
    if total_need is not None:
        return max(0, int(total_need))
    external_count = _as_int(_pick_from_mapping(fields, "external_request_count", "externalRequestCount"))
    internal_count = _as_int(_pick_from_mapping(fields, "internal_staff_count", "internalStaffCount"))
    computed = int(max(0, int(external_count or 0)) + max(0, int(internal_count or 0)))
    return computed


def _build_soc_source_event_uid(base_event_uid: str, suffix: str | None = None) -> str:
    root = str(base_event_uid or "").strip()
    if not suffix:
        return root
    return f"{root}:{suffix}"


def _upsert_overnight_assignment(
    conn,
    *,
    tenant,
    site,
    work_date: date,
    requested_count: int,
    event_uid: str,
    ticket_id: int | None,
    detail: dict[str, Any],
) -> dict[str, Any]:
    if not site:
        raise ValueError("site is required for overnight assignment")

    shift_start_at = datetime.combine(work_date, time(hour=22, minute=0, tzinfo=KST)).astimezone(timezone.utc)
    shift_end_at = (shift_start_at + timedelta(hours=10)).astimezone(timezone.utc)
    with conn.cursor() as cur:
        assignment_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO overnight_assignments (
                id, tenant_id, site_id, work_date, shift_start_at, shift_end_at, shift_hours,
                requested_count, source, ticket_id, source_event_uid, detail, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, 10,
                %s, 'SOC', %s, %s, %s::jsonb, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (source_event_uid)
            DO UPDATE SET
                site_id = EXCLUDED.site_id,
                work_date = EXCLUDED.work_date,
                shift_start_at = EXCLUDED.shift_start_at,
                shift_end_at = EXCLUDED.shift_end_at,
                requested_count = EXCLUDED.requested_count,
                ticket_id = EXCLUDED.ticket_id,
                detail = EXCLUDED.detail,
                updated_at = timezone('utc', now())
            RETURNING id, requested_count
            """,
            (
                assignment_id,
                tenant["id"],
                site["id"],
                work_date,
                shift_start_at,
                shift_end_at,
                max(0, int(requested_count)),
                ticket_id,
                event_uid,
                _safe_json(detail),
            ),
        )
        row = cur.fetchone()
    return {
        "overnight_assignment_id": str(row["id"]) if row else "",
        "requested_count": int(row["requested_count"]) if row else max(0, int(requested_count)),
        "shift_start_at": shift_start_at.isoformat(),
        "shift_end_at": shift_end_at.isoformat(),
        "shift_hours": 10,
    }


def _apply_leave_override(
    conn,
    *,
    tenant,
    employee,
    site,
    work_date: date,
    event_type: str,
    payload: SocEventIn,
    leave_reason_text: str | None = None,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    leave_type, report_display_leave_type, leave_reason_code = _map_leave_reason(
        leave_reason_text or "",
        payload.leave_type,
        event_type,
    )
    half_day_slot = _extract_half_day_slot(payload) if leave_type == "half" else None
    reason_segments = [f"SOC:{event_type}"]
    if leave_reason_text:
        reason_segments.append(str(leave_reason_text).strip())
    if payload.reason:
        reason_segments.append(str(payload.reason).strip())
    reason = " | ".join(part for part in reason_segments if part)[:300]
    review_note = (
        f"SOC leave override "
        f"(reason_code={leave_reason_code}, display={report_display_leave_type}, ticket_id={ticket_id or ''})"
    ).strip()
    schedule_note = (
        f"SOC leave override | reason={leave_reason_code} | display={report_display_leave_type}"
    )[:400]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM leave_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND start_at = %s
              AND end_at = %s
            ORDER BY requested_at DESC
            LIMIT 1
            """,
            (tenant["id"], employee["id"], work_date, work_date),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE leave_requests
                SET leave_type = %s,
                    half_day_slot = %s,
                    reason = %s,
                    status = 'approved',
                    review_note = %s,
                    reviewed_at = timezone('utc', now())
                WHERE id = %s
                """,
                (leave_type, half_day_slot, reason, review_note, existing["id"]),
            )
            leave_request_id = existing["id"]
            leave_action = "updated"
        else:
            leave_request_id = uuid.uuid4()
            cur.execute(
                """
                INSERT INTO leave_requests (
                    id, tenant_id, employee_id, leave_type, half_day_slot, start_at, end_at,
                    reason, status, requested_at, review_note, reviewed_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, 'approved', timezone('utc', now()), %s, timezone('utc', now())
                )
                """,
                (
                    leave_request_id,
                    tenant["id"],
                    employee["id"],
                    leave_type,
                    half_day_slot,
                    work_date,
                    work_date,
                    reason,
                    review_note,
                ),
            )
            leave_action = "inserted"

    schedule_result = _upsert_monthly_schedule(
        conn,
        tenant["id"],
        employee.get("company_id") or (site["company_id"] if site else None),
        employee.get("site_id") or (site["id"] if site else None),
        employee["id"],
        work_date,
        "off",
        source="SOC",
        source_ticket_id=ticket_id,
        schedule_note=schedule_note,
    )

    return {
        "leave_override": True,
        "leave_action": leave_action,
        "leave_request_id": str(leave_request_id),
        "leave_type": leave_type,
        "leave_reason_code": leave_reason_code,
        "report_display_leave_type": report_display_leave_type,
        "half_day_slot": half_day_slot,
        "ticket_id": ticket_id,
        "schedule": schedule_result,
    }


def _apply_overnight(
    conn,
    *,
    tenant,
    employee,
    site,
    work_date: date,
    event_uid: str,
    ticket_id: int | None = None,
) -> dict[str, Any]:
    schedule_result = _upsert_monthly_schedule(
        conn,
        tenant["id"],
        employee.get("company_id") or (site["company_id"] if site else None),
        employee.get("site_id") or (site["id"] if site else None),
        employee["id"],
        work_date,
        "night",
        source="SOC",
        source_ticket_id=ticket_id,
        schedule_note="SOC overnight assignment",
    )

    with conn.cursor() as cur:
        overnight_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO apple_overnight_reports (
                id, tenant_id, employee_id, site_id, work_date, overnight_approved, source_event_uid, source, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, TRUE, %s, 'soc', timezone('utc', now()), timezone('utc', now()))
            ON CONFLICT (tenant_id, employee_id, work_date, source)
            DO UPDATE SET
                overnight_approved = EXCLUDED.overnight_approved,
                site_id = EXCLUDED.site_id,
                source_event_uid = EXCLUDED.source_event_uid,
                updated_at = timezone('utc', now())
            RETURNING id
            """,
            (
                overnight_id,
                tenant["id"],
                employee["id"],
                employee.get("site_id") or (site["id"] if site else None),
                work_date,
                event_uid,
            ),
        )
        row = cur.fetchone()

    return {
        "overnight": True,
        "apple_overnight_report_id": str(row["id"]) if row else "",
        "ticket_id": ticket_id,
        "schedule": schedule_result,
    }


def _apply_overtime(
    conn,
    *,
    tenant,
    employee,
    site,
    work_date: date,
    event_uid: str,
    payload: SocEventIn,
    ticket_id: int | None = None,
    raw_minutes_total: int | None = None,
) -> dict[str, Any]:
    if raw_minutes_total is None:
        raw_minutes_total = _extract_overtime_minutes_total(payload)
    if raw_minutes_total is None:
        raise ValueError("INVALID_OVERTIME_MINUTES")
    approved_minutes = int(max(0, int(raw_minutes_total)))
    overtime_units = _minutes_to_soc_ticket_overtime_step(approved_minutes)
    reason_text = str(payload.reason or "").strip()
    if ticket_id:
        reason_text = f"[ticket:{ticket_id}] {reason_text}".strip()

    with conn.cursor() as cur:
        overtime_id = uuid.uuid4()
        cur.execute(
            """
            INSERT INTO soc_overtime_approvals (
                id, tenant_id, employee_id, site_id, work_date, approved_minutes, overtime_units, reason,
                source_event_uid, source, ticket_id, overtime_source, raw_minutes_total, overtime_hours_step, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, 'SOC_TICKET',
                %s, 'SOC_TICKET', %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (source_event_uid)
            DO UPDATE SET
                approved_minutes = EXCLUDED.approved_minutes,
                overtime_units = EXCLUDED.overtime_units,
                reason = EXCLUDED.reason,
                site_id = EXCLUDED.site_id,
                ticket_id = EXCLUDED.ticket_id,
                overtime_source = EXCLUDED.overtime_source,
                raw_minutes_total = EXCLUDED.raw_minutes_total,
                overtime_hours_step = EXCLUDED.overtime_hours_step,
                updated_at = timezone('utc', now())
            RETURNING id
            """,
            (
                overtime_id,
                tenant["id"],
                employee["id"],
                employee.get("site_id") or (site["id"] if site else None),
                work_date,
                approved_minutes,
                overtime_units,
                reason_text[:300] or None,
                event_uid,
                ticket_id,
                approved_minutes,
                overtime_units,
            ),
        )
        row = cur.fetchone()

    return {
        "overtime": True,
        "overtime_approval_id": str(row["id"]) if row else "",
        "approved_minutes": approved_minutes,
        "overtime_units": overtime_units,
        "raw_minutes_total": approved_minutes,
        "overtime_hours_step": overtime_units,
        "ticket_id": ticket_id,
    }


def _apply_leave_for_targets(
    conn,
    *,
    tenant,
    site,
    payload: SocEventIn,
    event_type: str,
    work_date: date,
    ticket_id: int | None,
) -> dict[str, Any]:
    employees = _resolve_soc_target_employees(
        conn,
        tenant_id=tenant["id"],
        site=site,
        payload=payload,
        event_type=event_type,
    )
    leave_reason_text = _extract_leave_reason_text(payload)
    applied_rows: list[dict[str, Any]] = []
    for employee in employees:
        applied_rows.append(
            _apply_leave_override(
                conn,
                tenant=tenant,
                employee=employee,
                site=site,
                work_date=work_date,
                event_type=event_type,
                payload=payload,
                leave_reason_text=leave_reason_text,
                ticket_id=ticket_id,
            )
        )

    return {
        "leave_override": True,
        "ticket_id": ticket_id,
        "work_date": work_date.isoformat(),
        "target_count": len(applied_rows),
        "targets": applied_rows,
    }


def _apply_overtime_for_targets(
    conn,
    *,
    tenant,
    site,
    payload: SocEventIn,
    event_type: str,
    event_uid: str,
    work_date: date,
    ticket_id: int | None,
) -> dict[str, Any]:
    employees = _resolve_soc_target_employees(
        conn,
        tenant_id=tenant["id"],
        site=site,
        payload=payload,
        event_type=event_type,
    )
    raw_minutes_total = _extract_overtime_minutes_total(payload)
    if raw_minutes_total is None:
        raise ValueError("INVALID_OVERTIME_MINUTES")

    applied_rows: list[dict[str, Any]] = []
    for employee in employees:
        source_uid = _build_soc_source_event_uid(event_uid, str(employee["id"]))
        row = _apply_overtime(
            conn,
            tenant=tenant,
            employee=employee,
            site=site,
            work_date=work_date,
            event_uid=source_uid,
            payload=payload,
            ticket_id=ticket_id,
            raw_minutes_total=raw_minutes_total,
        )
        row["employee_id"] = str(employee["id"])
        row["employee_code"] = employee["employee_code"]
        applied_rows.append(row)

    return {
        "overtime": True,
        "ticket_id": ticket_id,
        "work_date": work_date.isoformat(),
        "raw_minutes_total": int(raw_minutes_total),
        "overtime_hours_step": _minutes_to_soc_ticket_overtime_step(int(raw_minutes_total)),
        "target_count": len(applied_rows),
        "targets": applied_rows,
    }


def _apply_overnight_for_ticket(
    conn,
    *,
    tenant,
    site,
    payload: SocEventIn,
    event_uid: str,
    work_date: date,
    ticket_id: int | None,
) -> dict[str, Any]:
    target_keys = _extract_soc_employee_keys(payload, "overnight_approved")
    employees: list[dict[str, Any]] = []
    if target_keys:
        employees = _resolve_soc_target_employees(
            conn,
            tenant_id=tenant["id"],
            site=site,
            payload=payload,
            event_type="overnight_approved",
        )
        if not site and employees and employees[0].get("site_id"):
            site = _resolve_site_by_id(conn, tenant["id"], employees[0]["site_id"])

    request_count = _extract_overnight_need_count(payload)
    assignment = _upsert_overnight_assignment(
        conn,
        tenant=tenant,
        site=site,
        work_date=work_date,
        requested_count=request_count,
        event_uid=event_uid,
        ticket_id=ticket_id,
        detail={
            "template_fields": payload.payload if isinstance(payload.payload, dict) else {},
            "metadata": payload.metadata if isinstance(payload.metadata, dict) else {},
        },
    )

    apple_report_record: dict[str, Any] | None = None
    if site:
        headcount = max(0, int(request_count))
        if headcount == 0 and assignment and assignment.get("requested_count") is not None:
            try:
                headcount = max(0, int(assignment.get("requested_count") or 0))
            except Exception:
                headcount = 0
        if headcount == 0 and employees:
            headcount = len(employees)
        overnight_row = upsert_apple_report_overnight_record(
            conn,
            tenant_id=tenant["id"],
            site_id=site["id"],
            work_date=work_date,
            headcount=headcount,
            source_ticket_id=ticket_id,
            source_event_uid=event_uid,
        )
        if overnight_row:
            apple_report_record = _serialize_value(dict(overnight_row))

    overnight_targets: list[dict[str, Any]] = []
    if employees:
        for employee in employees:
            source_uid = _build_soc_source_event_uid(event_uid, str(employee["id"]))
            row = _apply_overnight(
                conn,
                tenant=tenant,
                employee=employee,
                site=site,
                work_date=work_date,
                event_uid=source_uid,
                ticket_id=ticket_id,
            )
            row["employee_id"] = str(employee["id"])
            row["employee_code"] = employee["employee_code"]
            overnight_targets.append(row)

    return {
        "overnight": True,
        "ticket_id": ticket_id,
        "work_date": work_date.isoformat(),
        "assignment": assignment,
        "apple_report_record": apple_report_record,
        "target_count": len(overnight_targets),
        "targets": overnight_targets,
    }


def _sync_attendance_event(
    conn,
    *,
    tenant,
    employee,
    site,
    payload: SocEventIn,
    event_type: str,
    occurred_at: datetime,
) -> dict[str, Any]:
    if not site:
        raise ValueError("site is required for attendance events")

    if event_type in SOC_ATTENDANCE_CHECKIN_EVENT_TYPES:
        normalized_event = "check_in"
    else:
        normalized_event = "check_out"

    latitude = _extract_float(payload, "latitude", "lat")
    longitude = _extract_float(payload, "longitude", "lng")
    distance_meters = _extract_float(payload, "distance_meters", "distance")
    is_within_radius = _extract_bool(payload, "is_within_radius", "within_radius")

    if latitude is None:
        latitude = float(site["latitude"])
    if longitude is None:
        longitude = float(site["longitude"])
    if distance_meters is None:
        distance_meters = 0.0
    if is_within_radius is None:
        is_within_radius = True

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM attendance_records
            WHERE tenant_id = %s
              AND employee_id = %s
              AND site_id = %s
              AND event_type = %s
              AND event_at >= %s::date
              AND event_at < (%s::date + interval '1 day')
            LIMIT 1
            """,
            (tenant["id"], employee["id"], site["id"], normalized_event, occurred_at, occurred_at),
        )
        existing = cur.fetchone()
        if existing:
            return {
                "event_type": normalized_event,
                "attendance_action": "existing",
                "attendance_record_id": str(existing["id"]),
            }

        cur.execute(
            """
            INSERT INTO attendance_records (
                tenant_id, employee_id, site_id, event_type, event_at,
                latitude, longitude, distance_meters, is_within_radius
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                tenant["id"],
                employee["id"],
                site["id"],
                normalized_event,
                occurred_at,
                latitude,
                longitude,
                distance_meters,
                is_within_radius,
            ),
        )
        inserted = cur.fetchone()

    pending_apple_ot = None
    if normalized_event == "check_out" and inserted:
        pending_apple_ot = upsert_pending_apple_daytime_ot_from_checkout(
            conn,
            tenant_id=tenant["id"],
            site_id=site["id"],
            checkout_at=occurred_at,
            source_event_uid=_build_soc_source_event_uid(str(payload.event_uid or ""), str(inserted["id"])),
        )

    return {
        "event_type": normalized_event,
        "attendance_action": "inserted",
        "attendance_record_id": str(inserted["id"]) if inserted else "",
        "apple_ot_pending_id": str(pending_apple_ot["id"]) if isinstance(pending_apple_ot, dict) and pending_apple_ot.get("id") else None,
    }


def _apply_closing_overtime(
    conn,
    *,
    tenant,
    employee,
    site,
    work_date: date,
    occurred_at: datetime,
    event_uid: str,
) -> dict[str, Any]:
    if not site:
        raise ValueError("site is required for closing overtime")
    return apply_closing_overtime_from_checkout(
        conn,
        tenant_id=tenant["id"],
        site_id=site["id"],
        employee_id=employee["id"],
        checkout_at=occurred_at,
        source_event_uid=event_uid,
        source_label="SOC_EVENT",
    )


def _apply_soc_event(conn, *, tenant, payload: SocEventIn, event_type: str) -> dict[str, Any]:
    metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
    template_fields = payload.payload if isinstance(payload.payload, dict) else {}
    ticket_id = _extract_ticket_id_from_payload(payload)

    site_code_hint = (
        _as_text(payload.site_code)
        or _as_text(_pick_from_mapping(metadata, "site_id", "siteId"))
        or _as_text(_pick_from_mapping(template_fields, "site_code", "siteCode", "site_id", "siteId"))
    )
    site = _resolve_site_by_code(conn, tenant["id"], site_code_hint) if site_code_hint else None

    if event_type in SOC_LEAVE_EVENT_TYPES or event_type in SOC_OVERNIGHT_EVENT_TYPES or event_type in SOC_OVERTIME_EVENT_TYPES:
        work_date = _extract_request_date_from_payload(payload)
    else:
        work_date = _derive_work_date(payload)
    occurred_at = _derive_occurred_at(payload, work_date)

    applied_changes: dict[str, Any] = {
        "event_type": event_type,
        "tenant_code": tenant["tenant_code"],
        "work_date": work_date.isoformat(),
        "ticket_id": ticket_id,
    }
    if site:
        applied_changes["site_code"] = site["site_code"]

    handlers_run: list[str] = []
    flag_states = {
        SOC_INTEGRATION_ENABLED: _is_feature_enabled(conn, tenant["id"], SOC_INTEGRATION_ENABLED),
        SHEETS_SYNC_ENABLED: _is_feature_enabled(conn, tenant["id"], SHEETS_SYNC_ENABLED),
        APPLE_REPORT_OVERNIGHT_ENABLED: _is_feature_enabled(conn, tenant["id"], APPLE_REPORT_OVERNIGHT_ENABLED),
        APPLE_REPORT_DAYTIME_ENABLED: _is_feature_enabled(conn, tenant["id"], APPLE_REPORT_DAYTIME_ENABLED),
        APPLE_REPORT_OT_ENABLED: _is_feature_enabled(conn, tenant["id"], APPLE_REPORT_OT_ENABLED),
        APPLE_REPORT_TOTAL_LATE_ENABLED: _is_feature_enabled(conn, tenant["id"], APPLE_REPORT_TOTAL_LATE_ENABLED),
        PAYROLL_SHEET_ENABLED: _is_feature_enabled(conn, tenant["id"], PAYROLL_SHEET_ENABLED),
        "soc_leave_override_enabled": _is_feature_enabled(conn, tenant["id"], "soc_leave_override_enabled"),
        "soc_overnight_enabled": _is_feature_enabled(conn, tenant["id"], "soc_overnight_enabled"),
        "soc_overtime_enabled": _is_feature_enabled(conn, tenant["id"], "soc_overtime_enabled"),
        "soc_closing_ot_enabled": _is_feature_enabled(conn, tenant["id"], "soc_closing_ot_enabled"),
    }

    if event_type in SOC_LEAVE_EVENT_TYPES:
        handlers_run.append("leave_override")
        if flag_states["soc_leave_override_enabled"]:
            applied_changes["leave_override"] = _apply_leave_for_targets(
                conn,
                tenant=tenant,
                site=site,
                payload=payload,
                work_date=work_date,
                event_type=event_type,
                ticket_id=ticket_id,
            )
        else:
            applied_changes["leave_override"] = {"skipped": True, "reason": "feature_disabled"}

    if event_type in SOC_OVERNIGHT_EVENT_TYPES:
        handlers_run.append("overnight")
        if flag_states["soc_overnight_enabled"]:
            applied_changes["overnight"] = _apply_overnight_for_ticket(
                conn,
                tenant=tenant,
                site=site,
                payload=payload,
                work_date=work_date,
                event_uid=payload.event_uid,
                ticket_id=ticket_id,
            )
        else:
            applied_changes["overnight"] = {"skipped": True, "reason": "feature_disabled"}

    if event_type in SOC_OVERTIME_EVENT_TYPES:
        handlers_run.append("overtime")
        if flag_states["soc_overtime_enabled"]:
            applied_changes["overtime"] = _apply_overtime_for_targets(
                conn,
                tenant=tenant,
                site=site,
                payload=payload,
                event_type=event_type,
                work_date=work_date,
                event_uid=payload.event_uid,
                ticket_id=ticket_id,
            )
        else:
            applied_changes["overtime"] = {"skipped": True, "reason": "feature_disabled"}

    attendance_or_closing_event = (
        event_type in SOC_ATTENDANCE_CHECKIN_EVENT_TYPES
        or event_type in SOC_ATTENDANCE_CHECKOUT_EVENT_TYPES
        or event_type in SOC_CLOSING_EVENT_TYPES
    )
    if attendance_or_closing_event:
        employee = _resolve_employee(conn, tenant["id"], payload.employee_code)
        if not employee:
            raise ValueError("EMPLOYEE_NOT_FOUND")
        applied_changes["employee_code"] = employee["employee_code"]
        if not site and employee.get("site_id"):
            site = _resolve_site_by_id(conn, tenant["id"], employee["site_id"])
            if site:
                applied_changes["site_code"] = site["site_code"]

        if event_type in SOC_ATTENDANCE_CHECKIN_EVENT_TYPES:
            handlers_run.append("attendance")
            applied_changes["attendance"] = _sync_attendance_event(
                conn,
                tenant=tenant,
                employee=employee,
                site=site,
                payload=payload,
                event_type=event_type,
                occurred_at=occurred_at,
            )

        if event_type in SOC_ATTENDANCE_CHECKOUT_EVENT_TYPES:
            handlers_run.append("attendance")
            applied_changes["attendance"] = _sync_attendance_event(
                conn,
                tenant=tenant,
                employee=employee,
                site=site,
                payload=payload,
                event_type=event_type,
                occurred_at=occurred_at,
            )

    if event_type in SOC_CLOSING_EVENT_TYPES:
        handlers_run.append("closing_ot")
        if flag_states["soc_closing_ot_enabled"]:
            applied_changes["closing_ot"] = _apply_closing_overtime(
                conn,
                tenant=tenant,
                employee=employee,
                site=site,
                work_date=work_date,
                occurred_at=occurred_at,
                event_uid=payload.event_uid,
            )
        else:
            applied_changes["closing_ot"] = {"skipped": True, "reason": "feature_disabled"}

    if not handlers_run:
        applied_changes["handled"] = False
        applied_changes["reason"] = "unsupported_event_type"
    else:
        applied_changes["handled"] = True
        applied_changes["handlers"] = handlers_run

    applied_changes["flag_states"] = flag_states
    return applied_changes


def _fetch_soc_ingest_row(conn, *, event_uid: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_uid, event_type, tenant_code, status, received_at, processed_at, error_text, applied_changes
            FROM soc_event_ingests
            WHERE event_uid = %s
            LIMIT 1
            """,
            (event_uid,),
        )
        return cur.fetchone()


def _fetch_integration_event_row(conn, *, event_id: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_id, event_type, tenant_id, status, error_message, created_at
            FROM integration_event_log
            WHERE event_id = %s
            LIMIT 1
            """,
            (event_id,),
        )
        return cur.fetchone()


def _row_to_soc_out(row, *, duplicate: bool = False) -> SocEventIngestOut:
    applied = row.get("applied_changes") if isinstance(row.get("applied_changes"), dict) else {}
    return SocEventIngestOut(
        id=row["id"],
        event_uid=row["event_uid"],
        event_type=row["event_type"],
        tenant_code=row.get("tenant_code"),
        status=row["status"],
        duplicate=duplicate,
        received_at=row["received_at"],
        processed_at=row.get("processed_at"),
        error_text=row.get("error_text"),
        applied_changes=applied,
    )


def _resolve_soc_token(x_soc_token: str | None, authorization: str | None) -> str:
    if x_soc_token:
        return x_soc_token.strip()
    header = str(authorization or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _normalize_signature(value: str | None) -> str:
    signature = str(value or "").strip()
    if signature.lower().startswith("sha256="):
        signature = signature.split("=", 1)[1].strip()
    return signature.lower()


def _build_soc_signature(secret: str, raw_body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _assert_soc_ingest_hmac_authorized(
    *,
    raw_body: bytes,
    x_source: str | None,
    x_event_id: str | None,
    x_signature: str | None,
    body_event_id: str,
) -> bool:
    if not settings.soc_integration_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="soc ingest disabled")

    if str(x_source or "").strip().upper() != "SOC":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid source header")

    header_event_id = str(x_event_id or "").strip()
    if not header_event_id or not hmac.compare_digest(header_event_id, body_event_id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="event header mismatch")

    if not settings.soc_ingest_require_hmac:
        return False

    secret = settings.soc_ingest_hmac_secret
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="soc ingest hmac secret is not configured",
        )

    expected = _build_soc_signature(secret, raw_body)
    provided = _normalize_signature(x_signature)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid signature")
    return True


def _assert_soc_ingest_authorized(x_soc_token: str | None, authorization: str | None) -> bool:
    if not settings.soc_integration_enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="soc ingest disabled")

    if not settings.soc_ingest_require_token:
        return False

    provided = _resolve_soc_token(x_soc_token, authorization)
    expected = settings.soc_ingest_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="soc ingest token is not configured",
        )
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid soc token")
    return True


def _resolve_sheets_ingest_token(x_sheets_token: str | None, authorization: str | None) -> str:
    direct = str(x_sheets_token or "").strip()
    if direct:
        return direct
    auth = str(authorization or "").strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return ""


def _assert_sheets_ingest_authorized(x_sheets_token: str | None, authorization: str | None) -> bool:
    expected = str(settings.google_sheets_ingest_token or "").strip()
    if not expected:
        return False
    provided = _resolve_sheets_ingest_token(x_sheets_token, authorization)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid sheets ingest token")
    return True


def _row_to_google_profile_out(row) -> GoogleSheetProfileOut:
    profile_scope = _resolve_profile_scope_from_row(row)
    profile_type = _resolve_profile_type_from_row(row)
    site_codes = _resolve_profile_site_codes_from_row(row)
    return GoogleSheetProfileOut(
        id=row["id"],
        tenant_code=row["tenant_code"],
        profile_name=row["profile_name"],
        profile_scope=profile_scope,
        profile_type=profile_type,
        site_codes=site_codes,
        spreadsheet_id=row.get("spreadsheet_id"),
        worksheet_schedule=row.get("worksheet_schedule"),
        worksheet_overtime=row.get("worksheet_overtime"),
        worksheet_overnight=row.get("worksheet_overnight"),
        webhook_url=row.get("webhook_url"),
        auth_mode=row.get("auth_mode") or "webhook",
        credential_ref=row.get("credential_ref"),
        mapping_json=row.get("mapping_json") if isinstance(row.get("mapping_json"), dict) else {},
        options_json=row.get("options_json") if isinstance(row.get("options_json"), dict) else {},
        is_active=bool(row.get("is_active")),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


def _fetch_google_profile(conn, profile_id, tenant_id=None):
    clauses = ["gp.id = %s"]
    params: list[Any] = [profile_id]
    if tenant_id is not None:
        clauses.append("gp.tenant_id = %s")
        params.append(tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT gp.*, t.tenant_code
            FROM google_sheet_profiles gp
            JOIN tenants t ON t.id = gp.tenant_id
            WHERE {' AND '.join(clauses)}
            LIMIT 1
            """,
            tuple(params),
        )
        return cur.fetchone()


def _fetch_active_google_profiles(conn, tenant_id) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT gp.*, t.tenant_code
            FROM google_sheet_profiles gp
            JOIN tenants t ON t.id = gp.tenant_id
            WHERE gp.tenant_id = %s
              AND COALESCE(gp.is_active, FALSE) = TRUE
            ORDER BY gp.updated_at DESC
            """,
            (tenant_id,),
        )
        return cur.fetchall()


def _event_type_to_sync_intents(event_type: str | None) -> set[str]:
    normalized = _normalize_event_type(event_type)
    intents: set[str] = set()
    if normalized in SOC_OVERNIGHT_EVENT_TYPES:
        intents.add(SYNC_INTENT_APPLE_OVERNIGHT)
    if normalized in SOC_LEAVE_EVENT_TYPES or normalized in SOC_OVERTIME_EVENT_TYPES:
        intents.add(SYNC_INTENT_PAYROLL)
    if normalized in SOC_ATTENDANCE_CHECKOUT_EVENT_TYPES or normalized in SOC_CLOSING_EVENT_TYPES:
        intents.add(SYNC_INTENT_APPLE_OT)
        intents.add(SYNC_INTENT_APPLE_TOTAL_LATE)
    return intents


def _parse_work_date(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _fetch_sync_schedule_leave_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, c.company_code, s.site_code, e.employee_code,
                   ms.schedule_date, ms.shift_type, ms.source, ms.source_ticket_id, ms.schedule_note
            FROM monthly_schedules ms
            JOIN tenants t ON t.id = ms.tenant_id
            JOIN companies c ON c.id = ms.company_id
            JOIN sites s ON s.id = ms.site_id
            JOIN employees e ON e.id = ms.employee_id
            WHERE ms.tenant_id = %s
              AND ms.schedule_date BETWEEN %s AND %s
              AND COALESCE(ms.source, '') = 'SOC'
              AND lower(ms.shift_type) = 'off'
            ORDER BY ms.schedule_date, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows = [_serialize_value(dict(row)) for row in cur.fetchall()]
    for row in rows:
        row["row_type"] = "leave_override"
    return rows


def _build_rows_by_scope(
    conn,
    *,
    tenant_id,
    scope: str,
    start_date: date,
    end_date: date,
    profile_options: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    normalized_scope = _normalize_profile_scope(scope)
    if normalized_scope == PROFILE_SCOPE_APPLE_OVERNIGHT:
        return {
            "schedule": [],
            "overtime": [],
            "overnight": _fetch_sync_apple_overnight_rows(conn, tenant_id, start_date, end_date),
        }

    if normalized_scope == PROFILE_SCOPE_APPLE_DAYTIME:
        return {
            "schedule": _fetch_sync_apple_daytime_shift_rows(conn, tenant_id, start_date, end_date),
            "overtime": [],
            "overnight": [],
        }

    if normalized_scope == PROFILE_SCOPE_APPLE_OT:
        return {
            "schedule": [],
            "overtime": _fetch_sync_apple_daytime_ot_rows(conn, tenant_id, start_date, end_date),
            "overnight": [],
        }

    if normalized_scope == PROFILE_SCOPE_APPLE_TOTAL_LATE:
        total_source = str((profile_options or {}).get("total_source") or "policy").strip().lower()
        return {
            "schedule": _fetch_sync_apple_total_shift_rows(
                conn,
                tenant_id,
                start_date,
                end_date,
                total_source=total_source,
            ),
            "overtime": _fetch_sync_apple_late_shift_rows(conn, tenant_id, start_date, end_date),
            "overnight": [],
        }

    if normalized_scope == PROFILE_SCOPE_DUTY_LOG:
        return {
            "schedule": _fetch_sync_duty_log_rows(conn, tenant_id, start_date, end_date),
            "overtime": [],
            "overnight": [],
        }

    if normalized_scope == PROFILE_SCOPE_SUPPORT_ASSIGNMENT:
        return {
            "schedule": _fetch_sync_support_assignment_rows(conn, tenant_id, start_date, end_date),
            "overtime": [],
            "overnight": [],
        }

    overtime_rows = _fetch_sync_overtime_rows(conn, tenant_id, start_date, end_date)
    closing_ot_rows = _fetch_sync_closing_ot_rows(conn, tenant_id, start_date, end_date)
    apple_daytime_ot_rows = _fetch_sync_apple_daytime_ot_rows(conn, tenant_id, start_date, end_date)
    late_shift_rows = _fetch_sync_late_shift_rows(conn, tenant_id, start_date, end_date)
    support_rows = _fetch_sync_support_assignment_rows(conn, tenant_id, start_date, end_date)
    event_rows = _fetch_sync_daily_event_rows(conn, tenant_id, start_date, end_date)
    duty_rows = _fetch_sync_duty_log_rows(conn, tenant_id, start_date, end_date)
    leave_rows = _fetch_sync_schedule_leave_rows(conn, tenant_id, start_date, end_date)
    daytime_rows = _fetch_sync_apple_daytime_shift_rows(conn, tenant_id, start_date, end_date)
    return {
        "schedule": leave_rows + daytime_rows + support_rows + event_rows + duty_rows,
        "overtime": overtime_rows + closing_ot_rows + apple_daytime_ot_rows + late_shift_rows,
        "overnight": [],
    }


def _make_sheets_retry_request_key(
    *,
    tenant_id,
    profile_id,
    trigger_event_type: str | None,
    profile_scope: str,
    period: dict[str, str],
) -> str:
    raw = "|".join(
        [
            str(tenant_id),
            str(profile_id),
            str(trigger_event_type or ""),
            str(profile_scope),
            str(period.get("start_date") or ""),
            str(period.get("end_date") or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _enqueue_sheets_retry_job(
    conn,
    *,
    tenant_id,
    tenant_code: str,
    profile_id,
    trigger_event_type: str | None,
    profile_scope: str,
    period: dict[str, str],
    dispatch_input: dict[str, Any],
    error_message: str | None,
) -> None:
    request_key = _make_sheets_retry_request_key(
        tenant_id=tenant_id,
        profile_id=profile_id,
        trigger_event_type=trigger_event_type,
        profile_scope=profile_scope,
        period=period,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sheets_sync_retry_queue (
                id, tenant_id, tenant_code, profile_id, request_key, trigger_event_type,
                profile_scope, dispatch_input, retry_count, max_retries, next_retry_at,
                status, last_error, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s::jsonb, 0, 3, timezone('utc', now()) + interval '3 minutes',
                'pending', %s, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (request_key)
            DO UPDATE SET
                tenant_code = EXCLUDED.tenant_code,
                trigger_event_type = EXCLUDED.trigger_event_type,
                profile_scope = EXCLUDED.profile_scope,
                dispatch_input = EXCLUDED.dispatch_input,
                retry_count = 0,
                max_retries = EXCLUDED.max_retries,
                status = 'pending',
                last_error = EXCLUDED.last_error,
                next_retry_at = timezone('utc', now()) + interval '3 minutes',
                updated_at = timezone('utc', now())
            """,
            (
                uuid.uuid4(),
                tenant_id,
                tenant_code,
                profile_id,
                request_key,
                trigger_event_type,
                profile_scope,
                _safe_json(dispatch_input),
                (str(error_message or "").strip() or None),
            ),
        )


def _process_sheets_retry_queue(conn, *, tenant_id) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, tenant_code, profile_id, trigger_event_type, profile_scope,
                   dispatch_input, retry_count, max_retries
            FROM sheets_sync_retry_queue
            WHERE tenant_id = %s
              AND status = 'pending'
              AND next_retry_at <= timezone('utc', now())
            ORDER BY next_retry_at ASC
            LIMIT 20
            """,
            (tenant_id,),
        )
        jobs = cur.fetchall()

    if not jobs:
        return

    orchestrator = SheetsSyncOrchestrator(default_webhook_url=settings.google_sheets_default_webhook)
    for job in jobs:
        dispatch_input = job.get("dispatch_input") if isinstance(job.get("dispatch_input"), dict) else {}
        profile = dispatch_input.get("profile") if isinstance(dispatch_input.get("profile"), dict) else {}
        period = dispatch_input.get("period") if isinstance(dispatch_input.get("period"), dict) else {}
        rows = dispatch_input.get("rows") if isinstance(dispatch_input.get("rows"), dict) else {}
        generated_at = str(dispatch_input.get("generated_at") or _utc_now().isoformat())
        tenant_code = str(job.get("tenant_code") or dispatch_input.get("tenant_code") or "").strip()

        if not profile or not tenant_code:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sheets_sync_retry_queue
                    SET status = 'dead',
                        last_error = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    ("retry payload is invalid", job["id"]),
                )
            continue

        dispatch = orchestrator.dispatch(
            profile=profile,
            tenant_code=tenant_code,
            period=period,
            generated_at=generated_at,
            rows=rows,
            payload_json_serializer=_safe_json,
        )
        ok = bool(dispatch.get("ok"))
        message = str(dispatch.get("sync_message") or "")

        _write_sheets_sync_log(
            conn,
            tenant_id=job["tenant_id"],
            profile_id=job["profile_id"],
            direction="DB_TO_SHEET",
            ok=ok,
            error_message=message,
        )

        if ok:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sheets_sync_retry_queue
                    SET status = 'success',
                        last_error = NULL,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (job["id"],),
                )
        else:
            retry_count = int(job.get("retry_count") or 0) + 1
            max_retries = int(job.get("max_retries") or 3)
            backoff_minutes = min(30, 2 ** min(retry_count, 5))
            next_retry = _utc_now() + timedelta(minutes=backoff_minutes)
            next_status = "dead" if retry_count >= max_retries else "pending"
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE sheets_sync_retry_queue
                    SET retry_count = %s,
                        next_retry_at = %s,
                        status = %s,
                        last_error = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (retry_count, next_retry, next_status, message[:1000] if message else None, job["id"]),
                )


def _dispatch_profile_sync(
    conn,
    *,
    orchestrator: SheetsSyncOrchestrator,
    tenant_id,
    tenant_code: str,
    profile: dict[str, Any],
    profile_scope: str,
    trigger: str,
    trigger_event_type: str | None,
    period: dict[str, str],
    rows_by_section: dict[str, list[dict[str, Any]]],
    enqueue_retry: bool = True,
    actor_user_id=None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    generated_at = _utc_now().isoformat()
    dispatch = orchestrator.dispatch(
        profile=profile,
        tenant_code=tenant_code,
        period=period,
        generated_at=generated_at,
        rows=rows_by_section,
        payload_json_serializer=_safe_json,
    )

    ok = bool(dispatch.get("ok"))
    message = str(dispatch.get("sync_message") or "")
    profile_id = profile["id"]
    _write_sheets_sync_log(
        conn,
        tenant_id=tenant_id,
        profile_id=profile_id,
        direction="DB_TO_SHEET",
        ok=ok,
        error_message=message,
    )

    if enqueue_retry and not ok:
        dispatch_input = {
            "profile": _serialize_value(profile),
            "tenant_code": tenant_code,
            "period": period,
            "generated_at": generated_at,
            "rows": rows_by_section,
        }
        _enqueue_sheets_retry_job(
            conn,
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            profile_id=profile_id,
            trigger_event_type=trigger_event_type,
            profile_scope=profile_scope,
            period=period,
            dispatch_input=dispatch_input,
            error_message=message,
        )

    row_counts = {
        "schedule": len(rows_by_section.get("schedule") or []),
        "overtime": len(rows_by_section.get("overtime") or []),
        "overnight": len(rows_by_section.get("overnight") or []),
    }
    _write_audit_log(
        conn,
        tenant_id=tenant_id,
        action_type="google_sheet_sync",
        source="system" if trigger != "manual_sync" else "hr_ui",
        actor_user_id=actor_user_id,
        actor_role=actor_role or ("system" if trigger != "manual_sync" else "operator"),
        target_type="google_sheet_profile",
        target_id=str(profile_id),
        detail={
            "trigger": trigger,
            "trigger_event_type": trigger_event_type,
            "profile_scope": profile_scope,
            "site_codes": _resolve_profile_site_codes_from_row(profile),
            "ok": ok,
            "sent": bool(dispatch.get("sent")),
            "message": message,
            "period": period,
            "row_counts": row_counts,
        },
    )

    return {
        "ok": ok,
        "sent": bool(dispatch.get("sent")),
        "sync_message": message,
        "payload": dispatch.get("payload") if isinstance(dispatch.get("payload"), dict) else {},
        "row_counts": row_counts,
    }


def _run_soc_post_commit_sheet_sync(
    tenant_id: str,
    tenant_code: str,
    event_type: str | None = None,
    work_date_iso: str | None = None,
) -> None:
    tenant_ref = tenant_id
    try:
        tenant_ref = uuid.UUID(str(tenant_id))
    except Exception:
        tenant_ref = tenant_id

    with get_connection() as conn:
        if not _is_feature_enabled(conn, tenant_ref, SHEETS_SYNC_ENABLED):
            return

        # Opportunistically flush pending retries first.
        _process_sheets_retry_queue(conn, tenant_id=tenant_ref)

        intents = _event_type_to_sync_intents(event_type)
        if not intents:
            intents = {
                SYNC_INTENT_APPLE_OVERNIGHT,
                SYNC_INTENT_APPLE_DAYTIME,
                SYNC_INTENT_APPLE_OT,
                SYNC_INTENT_APPLE_TOTAL_LATE,
                SYNC_INTENT_PAYROLL,
            }

        enabled_intents = {intent for intent in intents if _is_sync_intent_enabled(conn, tenant_ref, intent)}
        if not enabled_intents:
            return

        profiles = _fetch_active_google_profiles(conn, tenant_ref)
        if not profiles:
            return

        today = datetime.now(KST).date()
        work_date = _parse_work_date(work_date_iso)
        if work_date:
            start_date = work_date
            end_date = work_date
        else:
            start_date = today.replace(day=1)
            end_date = today

        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }

        orchestrator = SheetsSyncOrchestrator(default_webhook_url=settings.google_sheets_default_webhook)
        rows_cache: dict[tuple[str, str], dict[str, list[dict[str, Any]]]] = {}
        for profile in profiles:
            profile_scope = _resolve_profile_scope_from_row(profile)
            profile_site_codes = _resolve_profile_site_codes_from_row(profile)
            intent = _scope_to_sync_intent(profile_scope)
            if intent not in enabled_intents:
                continue

            profile_options = profile.get("options_json") if isinstance(profile.get("options_json"), dict) else {}
            total_source = str(profile_options.get("total_source") or "policy").strip().lower()
            rows_cache_key = (profile_scope, total_source if profile_scope == PROFILE_SCOPE_APPLE_TOTAL_LATE else "")
            if rows_cache_key not in rows_cache:
                rows_cache[rows_cache_key] = _build_rows_by_scope(
                    conn,
                    tenant_id=tenant_ref,
                    scope=profile_scope,
                    start_date=start_date,
                    end_date=end_date,
                    profile_options=profile_options,
                )
            rows_by_section = _filter_rows_by_site_codes(rows_cache[rows_cache_key], profile_site_codes)

            _dispatch_profile_sync(
                conn,
                orchestrator=orchestrator,
                tenant_id=tenant_ref,
                tenant_code=tenant_code,
                profile=profile,
                profile_scope=profile_scope,
                trigger="soc_event_post_commit",
                trigger_event_type=event_type,
                period=period,
                rows_by_section=rows_by_section,
                enqueue_retry=True,
            )


def _fetch_sync_schedule_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, c.company_code, s.site_code, e.employee_code, ms.schedule_date, ms.shift_type
            FROM monthly_schedules ms
            JOIN tenants t ON t.id = ms.tenant_id
            JOIN companies c ON c.id = ms.company_id
            JOIN sites s ON s.id = ms.site_id
            JOIN employees e ON e.id = ms.employee_id
            WHERE ms.tenant_id = %s
              AND ms.schedule_date BETWEEN %s AND %s
            ORDER BY ms.schedule_date, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        return [_serialize_value(dict(row)) for row in cur.fetchall()]


def _fetch_sync_overtime_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, e.employee_code, s.site_code, so.work_date,
                   so.approved_minutes, so.overtime_units, so.raw_minutes_total, so.overtime_hours_step,
                   so.ticket_id, so.overtime_source, so.reason, so.source, so.source_event_uid, so.updated_at
            FROM soc_overtime_approvals so
            JOIN tenants t ON t.id = so.tenant_id
            JOIN employees e ON e.id = so.employee_id
            LEFT JOIN sites s ON s.id = so.site_id
            WHERE so.tenant_id = %s
              AND so.work_date BETWEEN %s AND %s
              AND COALESCE(so.overtime_source, 'SOC_TICKET') = 'SOC_TICKET'
            ORDER BY so.work_date, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows = [_serialize_value(dict(row)) for row in cur.fetchall()]

    for row in rows:
        row["row_type"] = "soc_approved_overtime"
    return rows


def _fetch_sync_closing_ot_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, e.employee_code, s.site_code, so.work_date,
                   so.approved_minutes, so.overtime_units, so.raw_minutes_total, so.overtime_hours_step,
                   so.overtime_policy, so.closer_user_id, so.source_event_uid, so.updated_at
            FROM soc_overtime_approvals so
            JOIN tenants t ON t.id = so.tenant_id
            JOIN employees e ON e.id = so.employee_id
            LEFT JOIN sites s ON s.id = so.site_id
            WHERE so.tenant_id = %s
              AND so.work_date BETWEEN %s AND %s
              AND so.overtime_source = 'ATTENDANCE_CLOSE'
              AND NOT EXISTS (
                SELECT 1
                FROM soc_overtime_approvals st
                WHERE st.tenant_id = so.tenant_id
                  AND st.employee_id = so.employee_id
                  AND st.work_date = so.work_date
                  AND COALESCE(st.overtime_source, 'SOC_TICKET') = 'SOC_TICKET'
              )
            ORDER BY so.work_date, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows = [_serialize_value(dict(row)) for row in cur.fetchall()]

    for row in rows:
        row["row_type"] = "closing_ot_auto"
        row["priority_policy"] = "SOC_TICKET_FIRST"
    return rows


def _fetch_sync_apple_overnight_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    # A1 primary source: dedicated Apple overnight automation table.
    rows = [
        _serialize_value(dict(row))
        for row in list_apple_report_overnight_records(
            conn,
            tenant_id=tenant_id,
            work_date=None,
            site_id=None,
        )
    ]
    filtered = []
    for row in rows:
        work_date = _parse_work_date(str(row.get("work_date") or ""))
        if not work_date:
            continue
        if work_date < start_date or work_date > end_date:
            continue
        row["row_type"] = "apple_overnight_record"
        filtered.append(row)
    if filtered:
        return filtered

    # Backward-compatible fallback.
    rows: list[dict[str, Any]] = []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, e.employee_code, s.site_code, ao.work_date, ao.overnight_approved,
                   ao.source_event_uid, ao.updated_at
            FROM apple_overnight_reports ao
            JOIN tenants t ON t.id = ao.tenant_id
            JOIN employees e ON e.id = ao.employee_id
            LEFT JOIN sites s ON s.id = ao.site_id
            WHERE ao.tenant_id = %s
              AND ao.work_date BETWEEN %s AND %s
            ORDER BY ao.work_date, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows.extend(_serialize_value(dict(row)) for row in cur.fetchall())

        cur.execute(
            """
            SELECT t.tenant_code,
                   ''::text AS employee_code,
                   s.site_code,
                   oa.work_date,
                   TRUE AS overnight_approved,
                   oa.source_event_uid,
                   oa.updated_at,
                   oa.requested_count
            FROM overnight_assignments oa
            JOIN tenants t ON t.id = oa.tenant_id
            LEFT JOIN sites s ON s.id = oa.site_id
            WHERE oa.tenant_id = %s
              AND oa.work_date BETWEEN %s AND %s
            ORDER BY oa.work_date, s.site_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows.extend(_serialize_value(dict(row)) for row in cur.fetchall())

    for row in rows:
        row["row_type"] = "overnight_assignment" if row.get("requested_count") is not None else "overnight_employee"
    return rows


def _fetch_sync_apple_daytime_shift_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.tenant_code,
                s.id AS site_id,
                s.site_code,
                s.site_name,
                COALESCE(
                    p.weekday_headcount,
                    GREATEST(
                        (
                            SELECT COUNT(*)
                            FROM employees e
                            WHERE e.tenant_id = s.tenant_id
                              AND e.site_id = s.id
                        ),
                        1
                    )
                ) AS weekday_headcount,
                COALESCE(
                    p.weekend_headcount,
                    GREATEST(
                        (
                            SELECT COUNT(*)
                            FROM employees e
                            WHERE e.tenant_id = s.tenant_id
                              AND e.site_id = s.id
                        ),
                        1
                    )
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
        site_rows = cur.fetchall()

    output: list[dict[str, Any]] = []
    current = start_date
    while current <= end_date:
        for site in site_rows:
            generated = generate_apple_daytime_shift(
                work_date=current,
                weekday_headcount=int(site["weekday_headcount"]),
                weekend_headcount=int(site["weekend_headcount"]),
            )
            output.append(
                {
                    "tenant_code": site["tenant_code"],
                    "site_code": site["site_code"],
                    "site_name": site["site_name"],
                    "work_date": current.isoformat(),
                    "weekday_headcount": int(site["weekday_headcount"]),
                    "weekend_headcount": int(site["weekend_headcount"]),
                    "total_headcount": int(generated["total_headcount"]),
                    "supervisor_count": int(generated["supervisor_count"]),
                    "guard_count": int(generated["guard_count"]),
                    "supervisor_time": generated["supervisor_time"],
                    "guard_time": generated["guard_time"],
                    "supervisor_hours": float(generated["supervisor_hours"]),
                    "guard_hours": float(generated["guard_hours"]),
                    "is_weekend": bool(generated["is_weekend"]),
                    "row_type": "apple_daytime_shift",
                }
            )
        current = current + timedelta(days=1)
    return output


def _fetch_sync_apple_daytime_ot_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.tenant_code,
                s.site_code,
                ao.work_date,
                ao.leader_user_id,
                u.username AS leader_username,
                u.full_name AS leader_full_name,
                ao.closer_user_id,
                cu.username AS closer_username,
                cu.full_name AS closer_full_name,
                ao.reason,
                ao.status,
                ao.hours,
                ao.source,
                ao.created_at,
                ao.updated_at
            FROM apple_daytime_ot ao
            JOIN tenants t ON t.id = ao.tenant_id
            JOIN sites s ON s.id = ao.site_id
            LEFT JOIN arls_users u ON u.id = ao.leader_user_id
            LEFT JOIN arls_users cu ON cu.id = ao.closer_user_id
            WHERE ao.tenant_id = %s
              AND ao.work_date BETWEEN %s AND %s
            ORDER BY ao.work_date, s.site_code, ao.updated_at, ao.created_at
            """,
            (tenant_id, start_date, end_date),
        )
        rows = [_serialize_value(dict(row)) for row in cur.fetchall()]

    for row in rows:
        raw_reason = str(row.get("reason") or "").strip().lower()
        if raw_reason == "complaint":
            row["reason_text"] = "Customer complaint"
        elif raw_reason == "repair":
            row["reason_text"] = "Customer Repair"
        elif raw_reason == "inquiry":
            row["reason_text"] = "Customer Inquiry"
        else:
            row["reason_text"] = None
        row["row_type"] = "apple_daytime_ot"
    return rows


def _fetch_sync_late_shift_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                t.tenant_code,
                s.site_code,
                ls.work_date,
                e.employee_code,
                e.full_name AS employee_name,
                ls.minutes_late,
                ls.note,
                ls.created_at
            FROM late_shift_log ls
            JOIN tenants t ON t.id = ls.tenant_id
            JOIN sites s ON s.id = ls.site_id
            JOIN employees e ON e.id = ls.employee_id
            WHERE ls.tenant_id = %s
              AND ls.work_date BETWEEN %s AND %s
            ORDER BY ls.work_date, s.site_code, e.employee_code
            """,
            (tenant_id, start_date, end_date),
        )
        rows = [_serialize_value(dict(row)) for row in cur.fetchall()]

    for row in rows:
        row["row_type"] = "late_shift_manual"
    return rows


def _fetch_sync_apple_late_shift_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows = [
        _serialize_value(dict(row))
        for row in list_apple_late_shift_logs(
            conn,
            tenant_id=tenant_id,
            work_date=None,
            site_id=None,
        )
    ]
    output: list[dict[str, Any]] = []
    for row in rows:
        work_date = _parse_work_date(str(row.get("work_date") or ""))
        if not work_date:
            continue
        if work_date < start_date or work_date > end_date:
            continue
        row["row_type"] = "apple_late_shift"
        output.append(row)
    return output


def _fetch_sync_apple_total_shift_rows(
    conn,
    tenant_id,
    start_date: date,
    end_date: date,
    *,
    total_source: str = "policy",
) -> list[dict[str, Any]]:
    return build_apple_total_shift_rows(
        conn,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        total_source=total_source,
    )


def _fetch_sync_support_assignment_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows = list_support_assignments(conn, tenant_id=tenant_id, work_date=None, site_id=None)
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = _serialize_value(dict(raw))
        work_date = _parse_work_date(str(row.get("work_date") or ""))
        if not work_date:
            continue
        if work_date < start_date or work_date > end_date:
            continue
        row["row_type"] = "support_assignment"
        output.append(row)
    return output


def _fetch_sync_daily_event_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    rows = list_daily_event_logs(conn, tenant_id=tenant_id, work_date=None, site_id=None)
    output: list[dict[str, Any]] = []
    for raw in rows:
        row = _serialize_value(dict(raw))
        work_date = _parse_work_date(str(row.get("work_date") or ""))
        if not work_date:
            continue
        if work_date < start_date or work_date > end_date:
            continue
        row["row_type"] = "daily_event"
        output.append(row)
    return output


def _iter_month_keys(start_date: date, end_date: date) -> list[str]:
    if end_date < start_date:
        return []
    keys: list[str] = []
    cursor = date(start_date.year, start_date.month, 1)
    while cursor <= end_date:
        keys.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return keys


def _fetch_sync_duty_log_rows(conn, tenant_id, start_date: date, end_date: date) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code, e.id AS employee_id, e.employee_code
            FROM employees e
            JOIN tenants t ON t.id = e.tenant_id
            WHERE e.tenant_id = %s
            ORDER BY e.employee_code
            """,
            (tenant_id,),
        )
        employees = cur.fetchall()

    month_keys = _iter_month_keys(start_date, end_date)
    rows: list[dict[str, Any]] = []
    for employee in employees:
        for month in month_keys:
            duty_rows = build_duty_log(
                conn,
                tenant_id=tenant_id,
                employee_id=employee["employee_id"],
                month=month,
            )
            for row in duty_rows:
                work_date = row.get("work_date")
                if not isinstance(work_date, date):
                    continue
                if work_date < start_date or work_date > end_date:
                    continue
                rows.append(
                    {
                        "tenant_code": employee["tenant_code"],
                        "employee_code": employee["employee_code"],
                        "work_date": work_date.isoformat(),
                        "mark": row.get("mark"),
                        "shift_type": row.get("shift_type"),
                        "leave_type": row.get("leave_type"),
                        "source": row.get("source"),
                        "row_type": "duty_log",
                    }
                )
    return rows


def _post_webhook(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = _safe_json(payload).encode("utf-8")
    request = UrlRequest(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "rg-arls-dev/1.0",
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            status_code = int(getattr(response, "status", 200))
            response_body = response.read(3000).decode("utf-8", errors="ignore")
            return {
                "status_code": status_code,
                "body_excerpt": response_body,
            }
    except HTTPError as exc:
        response_body = exc.read(3000).decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
        raise RuntimeError(f"webhook http error {exc.code}: {response_body}") from exc
    except URLError as exc:
        raise RuntimeError(f"webhook url error: {exc.reason}") from exc


@router.post("/soc/events", response_model=SocEventIngestOut)
async def ingest_soc_event(
    request: Request,
    background_tasks: BackgroundTasks,
    x_source: str | None = Header(default=None, alias="X-Source"),
    x_event_id: str | None = Header(default=None, alias="X-Event-Id"),
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    x_soc_token: str | None = Header(default=None, alias="X-SOC-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    conn=Depends(get_db_conn),
):
    raw_body = await request.body()
    if not raw_body.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="request body is required")
    try:
        payload_obj = json.loads(raw_body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid json body") from exc
    if not isinstance(payload_obj, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="json object body is required")

    is_webhook_envelope = "event_id" in payload_obj or "eventId" in payload_obj
    if is_webhook_envelope:
        envelope = SocEventEnvelopeIn.model_validate(payload_obj)
        event_uid = str(envelope.event_id or "").strip()
        event_type = _normalize_soc_webhook_event_type(envelope.event_type)
        signature_valid = _assert_soc_ingest_hmac_authorized(
            raw_body=raw_body,
            x_source=x_source,
            x_event_id=x_event_id,
            x_signature=x_signature,
            body_event_id=event_uid,
        )
        existing = _fetch_integration_event_row(conn, event_id=event_uid)
        if existing and str(existing.get("status") or "").upper() == "SUCCESS":
            existing_ingest = _fetch_soc_ingest_row(conn, event_uid=event_uid)
            if existing_ingest:
                return _row_to_soc_out(existing_ingest, duplicate=True)
            now = _utc_now()
            return SocEventIngestOut(
                id=uuid.uuid4(),
                event_uid=event_uid,
                event_type=event_type,
                tenant_code=None,
                status="processed",
                duplicate=True,
                received_at=now,
                processed_at=now,
                error_text=None,
                applied_changes={"already_processed": True},
            )
        payload = _to_internal_soc_event(envelope)
    else:
        payload = SocEventIn.model_validate(payload_obj)
        signature_valid = _assert_soc_ingest_authorized(x_soc_token, authorization)
        event_uid = str(payload.event_uid or "").strip()
        event_type = _normalize_event_type(payload.event_type)

    tenant_code = str(payload.tenant_code or "").strip().upper()

    receiver = SocEventReceiver(
        idempotency_store=EventIdempotencyStore(conn),
        feature_flags=FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS),
        hr_domain_applier=HrDomainApplier(
            lambda *, tenant, payload, event_type: _apply_soc_event(conn, tenant=tenant, payload=payload, event_type=event_type),
        ),
        audit_log=AuditLogService(conn),
        tenant_resolver=lambda code: _resolve_tenant_by_code(conn, code),
    )
    result = receiver.receive(
        payload=payload,
        event_uid=event_uid,
        event_type=event_type,
        tenant_code=tenant_code,
        signature_valid=signature_valid,
    )
    row = result.get("row")
    if not row:
        raise HTTPException(status_code=500, detail="event ingest row missing")
    status_text = str(result.get("status_text") or row.get("status") or "").lower()
    if status_text == "failed":
        conn.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"soc event apply failed: {row.get('error_text') or 'unknown error'}",
        )

    tenant = result.get("tenant")
    if tenant and status_text == "processed":
        sheets_enabled = _is_feature_enabled(conn, tenant["id"], SHEETS_SYNC_ENABLED)
        intents = _event_type_to_sync_intents(event_type)
        enabled_intents = {intent for intent in intents if _is_sync_intent_enabled(conn, tenant["id"], intent)}
        applied_changes = row.get("applied_changes") if isinstance(row.get("applied_changes"), dict) else {}
        work_date_iso = str(applied_changes.get("work_date") or "").strip() or None
        if sheets_enabled and enabled_intents:
            background_tasks.add_task(
                _run_soc_post_commit_sheet_sync,
                str(tenant["id"]),
                str(tenant["tenant_code"] or tenant_code),
                event_type,
                work_date_iso,
            )

    return _row_to_soc_out(row, duplicate=bool(result.get("duplicate")))


@router.post("/google-sheets/support-assignments/webhook", dependencies=[Depends(apply_rate_limit)])
def ingest_support_assignments_from_sheet(
    payload: SupportSheetWebhookIn,
    profile_id: uuid.UUID | None = Query(default=None),
    x_sheets_token: str | None = Header(default=None, alias="X-Sheets-Token"),
    authorization: str | None = Header(default=None, alias="Authorization"),
    conn=Depends(get_db_conn),
):
    _assert_sheets_ingest_authorized(x_sheets_token, authorization)

    tenant_code = str(payload.tenant_code or "").strip().upper()
    site_code = str(payload.site_code or "").strip().upper()
    tenant = _resolve_tenant_by_code(conn, tenant_code)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    if not bool(tenant.get("is_active", True)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant is disabled")
    site = _resolve_site_by_code(conn, tenant["id"], site_code)
    if not site:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="site not found")

    entries = [str(item.text or "").strip() for item in (payload.entries or []) if str(item.text or "").strip()]
    if not entries:
        _write_sheets_sync_log(
            conn,
            tenant_id=tenant["id"],
            profile_id=profile_id,
            direction="SHEET_TO_DB",
            ok=True,
            error_message=None,
        )
        return {
            "ok": True,
            "tenant_code": tenant_code,
            "site_code": site_code,
            "work_date": payload.work_date.isoformat(),
            "inserted_count": 0,
            "skipped_count": 0,
            "inserted": [],
            "skipped": [],
        }

    try:
        resolved = resolve_support_entries_to_assignments(
            conn,
            tenant_id=tenant["id"],
            site_id=site["id"],
            work_date=payload.work_date,
            entries=entries,
            source=payload.source or "SHEET",
        )
        inserted = resolved.get("inserted") if isinstance(resolved.get("inserted"), list) else []
        skipped = resolved.get("skipped") if isinstance(resolved.get("skipped"), list) else []
        _write_sheets_sync_log(
            conn,
            tenant_id=tenant["id"],
            profile_id=profile_id,
            direction="SHEET_TO_DB",
            ok=True,
            error_message=None,
        )
        _write_audit_log(
            conn,
            tenant_id=tenant["id"],
            action_type="support_assignment_sheet_ingested",
            source="sheet_webhook",
            actor_role="system",
            target_type="support_assignment",
            target_id=site_code,
            detail={
                "site_code": site_code,
                "work_date": payload.work_date.isoformat(),
                "source": payload.source or "SHEET",
                "inserted_count": len(inserted),
                "skipped_count": len(skipped),
                "entries_count": len(entries),
            },
        )
        return {
            "ok": True,
            "tenant_code": tenant_code,
            "site_code": site_code,
            "work_date": payload.work_date.isoformat(),
            "inserted_count": len(inserted),
            "skipped_count": len(skipped),
            "inserted": [_serialize_value(dict(row)) for row in inserted],
            "skipped": [_serialize_value(dict(row)) for row in skipped],
        }
    except HTTPException as exc:
        _write_sheets_sync_log(
            conn,
            tenant_id=tenant["id"],
            profile_id=profile_id,
            direction="SHEET_TO_DB",
            ok=False,
            error_message=str(exc.detail),
        )
        raise
    except Exception as exc:
        _write_sheets_sync_log(
            conn,
            tenant_id=tenant["id"],
            profile_id=profile_id,
            direction="SHEET_TO_DB",
            ok=False,
            error_message=str(exc),
        )
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="support sheet ingest failed") from exc


@router.get("/soc/events", response_model=list[SocEventIngestOut], dependencies=[Depends(apply_rate_limit)])
def list_soc_events(
    tenant_code: str | None = Query(default=None, max_length=64),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
    limit: int = Query(default=50, ge=1, le=300),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, tenant_code)

    clauses = ["se.tenant_id = %s"]
    params: list[Any] = [tenant["id"]]
    if status_filter:
        clauses.append("se.status = %s")
        params.append(status_filter.strip().lower())
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT se.id, se.event_uid, se.event_type, se.tenant_code, se.status,
                   se.received_at, se.processed_at, se.error_text, se.applied_changes
            FROM soc_event_ingests se
            WHERE {' AND '.join(clauses)}
            ORDER BY se.received_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()

    return [_row_to_soc_out(row) for row in rows]


@router.get("/audit-logs", dependencies=[Depends(apply_rate_limit)])
def list_integration_audit_logs(
    tenant_code: str | None = Query(default=None, max_length=64),
    action_type: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, tenant_code)

    clauses = ["al.tenant_id = %s"]
    params: list[Any] = [tenant["id"]]
    if action_type:
        clauses.append("al.action_type = %s")
        params.append(action_type.strip())
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT al.id, al.action_type, al.source, al.actor_user_id, al.actor_role,
                   al.target_type, al.target_id, al.detail, al.created_at
            FROM integration_audit_logs al
            WHERE {' AND '.join(clauses)}
            ORDER BY al.created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()

    return [_serialize_value(dict(row)) for row in rows]


@router.get("/feature-flags", response_model=list[IntegrationFeatureFlagOut], dependencies=[Depends(apply_rate_limit)])
def list_integration_feature_flags(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    feature_flags = FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS)

    results: list[IntegrationFeatureFlagOut] = []
    for item in feature_flags.list_effective(tenant["id"]):
        flag_key = str(item["flag_key"])
        override = _get_feature_flag(conn, tenant["id"], flag_key)
        updated_at = None
        if override is not None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT updated_at
                    FROM integration_feature_flags
                    WHERE tenant_id = %s
                      AND flag_key = ANY(%s::text[])
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (
                        tenant["id"],
                        [
                            flag_key,
                            "soc_ingest_enabled" if flag_key == SOC_INTEGRATION_ENABLED else flag_key,
                            "google_sheets_sync_enabled" if flag_key == SHEETS_SYNC_ENABLED else flag_key,
                            "soc_overnight_enabled" if flag_key == APPLE_REPORT_OVERNIGHT_ENABLED else flag_key,
                        ],
                    ),
                )
                row = cur.fetchone()
            updated_at = row["updated_at"] if row else None

        results.append(
            IntegrationFeatureFlagOut(
                tenant_code=tenant["tenant_code"],
                flag_key=flag_key,
                enabled=bool(item["enabled"]),
                updated_at=updated_at,
            ),
        )
    return sorted(results, key=lambda x: x.flag_key)


@router.patch("/feature-flags", response_model=IntegrationFeatureFlagOut, dependencies=[Depends(apply_rate_limit)])
def update_integration_feature_flag(
    payload: IntegrationFeatureFlagUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    flag_key = normalize_flag_key(payload.flag_key)
    if flag_key not in FEATURE_FLAG_DEFAULTS:
        raise HTTPException(status_code=400, detail="unsupported flag_key")

    tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    _set_feature_flag(conn, tenant["id"], flag_key, bool(payload.enabled), updated_by=user["id"])

    _write_audit_log(
        conn,
        tenant_id=tenant["id"],
        action_type="integration_flag_updated",
        source="hr_ui",
        actor_user_id=user["id"],
        actor_role=normalize_role(user.get("role")),
        target_type="feature_flag",
        target_id=flag_key,
        detail={"enabled": bool(payload.enabled)},
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT enabled, updated_at
            FROM integration_feature_flags
            WHERE tenant_id = %s
              AND flag_key = %s
            LIMIT 1
            """,
            (tenant["id"], flag_key),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=500, detail="flag update failed")

    return IntegrationFeatureFlagOut(
        tenant_code=tenant["tenant_code"],
        flag_key=flag_key,
        enabled=bool(row["enabled"]),
        updated_at=row["updated_at"],
    )


@router.get("/google-sheets/profiles", response_model=list[GoogleSheetProfileOut], dependencies=[Depends(apply_rate_limit)])
def list_google_sheet_profiles(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT gp.*, t.tenant_code
            FROM google_sheet_profiles gp
            JOIN tenants t ON t.id = gp.tenant_id
            WHERE gp.tenant_id = %s
            ORDER BY gp.is_active DESC, gp.updated_at DESC
            """,
            (tenant["id"],),
        )
        rows = cur.fetchall()
    return [_row_to_google_profile_out(row) for row in rows]


@router.post("/google-sheets/profiles", response_model=GoogleSheetProfileOut, dependencies=[Depends(apply_rate_limit)])
def create_google_sheet_profile(
    payload: GoogleSheetProfileCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, payload.tenant_code)

    if payload.is_active:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE google_sheet_profiles
                SET is_active = FALSE,
                    updated_by = %s,
                    updated_at = timezone('utc', now())
                WHERE tenant_id = %s
                """,
                (user["id"], tenant["id"]),
            )

    profile_id = uuid.uuid4()
    webhook_url = str(payload.webhook_url or "").strip() or settings.google_sheets_default_webhook or None
    options_payload = dict(payload.options_json or {})
    options_payload["profile_scope"] = _normalize_profile_scope(payload.profile_scope)
    options_payload["sync_mode"] = PROFILE_TYPE_TO_SYNC_MODE[_normalize_profile_type(payload.profile_type)]
    options_payload["site_codes"] = _normalize_site_codes(payload.site_codes)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO google_sheet_profiles (
                id, tenant_id, profile_name, is_active,
                spreadsheet_id, worksheet_schedule, worksheet_overtime, worksheet_overnight,
                webhook_url, auth_mode, credential_ref, mapping_json, options_json,
                created_by, updated_by, created_at, updated_at
            )
            VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s::jsonb, %s::jsonb,
                %s, %s, timezone('utc', now()), timezone('utc', now())
            )
            """,
            (
                profile_id,
                tenant["id"],
                payload.profile_name,
                payload.is_active,
                payload.spreadsheet_id or None,
                payload.worksheet_schedule or None,
                payload.worksheet_overtime or None,
                payload.worksheet_overnight or None,
                webhook_url,
                payload.auth_mode or "webhook",
                payload.credential_ref or None,
                _safe_json(payload.mapping_json or {}),
                _safe_json(options_payload),
                user["id"],
                user["id"],
            ),
        )

    _write_audit_log(
        conn,
        tenant_id=tenant["id"],
        action_type="google_sheet_profile_created",
        source="hr_ui",
        actor_user_id=user["id"],
        actor_role=normalize_role(user.get("role")),
        target_type="google_sheet_profile",
        target_id=str(profile_id),
        detail={
            "profile_name": payload.profile_name,
            "profile_scope": options_payload.get("profile_scope"),
            "profile_type": _normalize_profile_type(payload.profile_type),
            "site_codes": options_payload.get("site_codes") or [],
            "is_active": payload.is_active,
        },
    )

    row = _fetch_google_profile(conn, profile_id, tenant_id=tenant["id"])
    if not row:
        raise HTTPException(status_code=500, detail="profile create failed")
    return _row_to_google_profile_out(row)


@router.patch("/google-sheets/profiles/{profile_id}", response_model=GoogleSheetProfileOut, dependencies=[Depends(apply_rate_limit)])
def update_google_sheet_profile(
    profile_id: uuid.UUID,
    payload: GoogleSheetProfileUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    actor_role = normalize_role(user.get("role"))
    tenant_scope = None if actor_role == "dev" else user["tenant_id"]
    row = _fetch_google_profile(conn, profile_id, tenant_id=tenant_scope)
    if not row:
        raise HTTPException(status_code=404, detail="profile not found")

    values = payload.model_dump(exclude_unset=True)
    if not values:
        return _row_to_google_profile_out(row)

    existing_options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    options_payload = dict(existing_options)
    options_mutated = False

    incoming_options = values.pop("options_json", None)
    if isinstance(incoming_options, dict):
        options_payload.update(incoming_options)
        options_mutated = True

    if "profile_scope" in values:
        options_payload["profile_scope"] = _normalize_profile_scope(values.pop("profile_scope"))
        options_mutated = True
    if "profile_type" in values:
        normalized_type = _normalize_profile_type(values.pop("profile_type"))
        options_payload["sync_mode"] = PROFILE_TYPE_TO_SYNC_MODE[normalized_type]
        options_mutated = True
    if "site_codes" in values:
        options_payload["site_codes"] = _normalize_site_codes(values.pop("site_codes"))
        options_mutated = True
    if options_mutated:
        values["options_json"] = options_payload

    if values.get("is_active") is True:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE google_sheet_profiles
                SET is_active = FALSE,
                    updated_by = %s,
                    updated_at = timezone('utc', now())
                WHERE tenant_id = %s
                  AND id <> %s
                """,
                (user["id"], row["tenant_id"], profile_id),
            )

    assignments: list[str] = []
    params: list[Any] = []

    text_fields = {
        "profile_name",
        "spreadsheet_id",
        "worksheet_schedule",
        "worksheet_overtime",
        "worksheet_overnight",
        "webhook_url",
        "auth_mode",
        "credential_ref",
    }
    json_fields = {"mapping_json", "options_json"}

    for key, value in values.items():
        if key in text_fields:
            assignments.append(f"{key} = %s")
            text_value = str(value).strip() if value is not None else None
            params.append(text_value or None)
            continue
        if key in json_fields:
            assignments.append(f"{key} = %s::jsonb")
            params.append(_safe_json(value or {}))
            continue
        if key == "is_active":
            assignments.append("is_active = %s")
            params.append(bool(value))

    assignments.append("updated_by = %s")
    params.append(user["id"])
    assignments.append("updated_at = timezone('utc', now())")
    params.append(profile_id)

    if not assignments:
        return _row_to_google_profile_out(row)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE google_sheet_profiles
            SET {', '.join(assignments)}
            WHERE id = %s
            """,
            tuple(params),
        )

    _write_audit_log(
        conn,
        tenant_id=row["tenant_id"],
        action_type="google_sheet_profile_updated",
        source="hr_ui",
        actor_user_id=user["id"],
        actor_role=normalize_role(user.get("role")),
        target_type="google_sheet_profile",
        target_id=str(profile_id),
        detail={"fields": sorted(values.keys())},
    )

    updated = _fetch_google_profile(conn, profile_id, tenant_id=tenant_scope)
    if not updated:
        raise HTTPException(status_code=500, detail="profile update failed")
    return _row_to_google_profile_out(updated)


@router.post("/google-sheets/profiles/{profile_id}/sync", response_model=GoogleSheetSyncOut, dependencies=[Depends(apply_rate_limit)])
def sync_google_sheet_profile(
    profile_id: uuid.UUID,
    payload: GoogleSheetSyncRequest,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    actor_role = normalize_role(user.get("role"))
    tenant_scope = None if actor_role == "dev" else user["tenant_id"]
    profile = _fetch_google_profile(conn, profile_id, tenant_id=tenant_scope)
    if not profile:
        raise HTTPException(status_code=404, detail="profile not found")

    tenant_id = profile["tenant_id"]
    tenant_code = profile["tenant_code"]
    _process_sheets_retry_queue(conn, tenant_id=tenant_id)
    if payload.start_date and payload.end_date and payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

    today = datetime.now(KST).date()
    start_date = payload.start_date or today.replace(day=1)
    end_date = payload.end_date or today

    profile_scope = _resolve_profile_scope_from_row(profile)
    profile_options = profile.get("options_json") if isinstance(profile.get("options_json"), dict) else {}
    profile_site_codes = _resolve_profile_site_codes_from_row(profile)
    period = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    base_rows = _build_rows_by_scope(
        conn,
        tenant_id=tenant_id,
        scope=profile_scope,
        start_date=start_date,
        end_date=end_date,
        profile_options=profile_options,
    )
    rows_by_section = _filter_rows_by_site_codes(base_rows, profile_site_codes)

    intent = _scope_to_sync_intent(profile_scope)
    feature_enabled = _is_feature_enabled(conn, tenant_id, SHEETS_SYNC_ENABLED) and _is_sync_intent_enabled(conn, tenant_id, intent)

    if not feature_enabled:
        ok = False
        sent = False
        sync_message = "sheets sync is disabled by feature flag for selected profile scope"
        sync_payload = SheetsAdapter(profile).build_payload(
            tenant_code=tenant_code,
            period=period,
            generated_at=_utc_now().isoformat(),
            rows=rows_by_section,
        )
        row_counts = {
            "schedule": len(rows_by_section.get("schedule") or []),
            "overtime": len(rows_by_section.get("overtime") or []),
            "overnight": len(rows_by_section.get("overnight") or []),
        }
        _write_sheets_sync_log(
            conn,
            tenant_id=tenant_id,
            profile_id=profile_id,
            direction="DB_TO_SHEET",
            ok=ok,
            error_message=sync_message,
        )
        _write_audit_log(
            conn,
            tenant_id=tenant_id,
            action_type="google_sheet_sync",
            source="hr_ui",
            actor_user_id=user["id"],
            actor_role=normalize_role(user.get("role")),
            target_type="google_sheet_profile",
            target_id=str(profile_id),
            detail={
                "trigger": "manual_sync",
                "profile_scope": profile_scope,
                "site_codes": profile_site_codes,
                "ok": ok,
                "sent": sent,
                "message": sync_message,
                "row_counts": row_counts,
                "period": period,
            },
        )
    else:
        orchestrator = SheetsSyncOrchestrator(default_webhook_url=settings.google_sheets_default_webhook)
        dispatch = _dispatch_profile_sync(
            conn,
            orchestrator=orchestrator,
            tenant_id=tenant_id,
            tenant_code=tenant_code,
            profile=profile,
            profile_scope=profile_scope,
            trigger="manual_sync",
            trigger_event_type="manual_sync",
            period=period,
            rows_by_section=rows_by_section,
            enqueue_retry=True,
            actor_user_id=user["id"],
            actor_role=normalize_role(user.get("role")),
        )
        ok = bool(dispatch.get("ok"))
        sent = bool(dispatch.get("sent"))
        sync_message = str(dispatch.get("sync_message") or "")
        sync_payload = dispatch.get("payload") if isinstance(dispatch.get("payload"), dict) else {}
        row_counts = dispatch.get("row_counts") if isinstance(dispatch.get("row_counts"), dict) else {
            "schedule": len(rows_by_section.get("schedule") or []),
            "overtime": len(rows_by_section.get("overtime") or []),
            "overnight": len(rows_by_section.get("overnight") or []),
        }
    preview = {
        "tenant_code": tenant_code,
        "period": period,
        "profile_scope": profile_scope,
        "site_codes": profile_site_codes,
        "sync_mode": str(sync_payload.get("sync_mode") or "CUSTOM_JSON"),
        "sample": {
            "schedule": (rows_by_section.get("schedule") or [])[:20],
            "overtime": (rows_by_section.get("overtime") or [])[:20],
            "overnight": (rows_by_section.get("overnight") or [])[:20],
        },
    }

    return GoogleSheetSyncOut(
        ok=ok,
        sent=sent,
        tenant_code=tenant_code,
        profile_id=profile_id,
        row_counts=row_counts,
        payload_preview=preview,
        sync_message=sync_message,
    )


@router.get("/google-sheets/logs", response_model=list[GoogleSheetSyncLogOut], dependencies=[Depends(apply_rate_limit)])
def list_google_sheet_sync_logs(
    tenant_code: str | None = Query(default=None, max_length=64),
    profile_id: uuid.UUID | None = Query(default=None),
    status_filter: str | None = Query(default="FAIL", alias="status", max_length=16),
    limit: int = Query(default=30, ge=1, le=300),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_integration_manager(user)
    tenant = _resolve_target_tenant(conn, user, tenant_code)

    normalized_status = str(status_filter or "").strip().upper()
    if normalized_status and normalized_status not in {"SUCCESS", "FAIL"}:
        raise HTTPException(status_code=400, detail="status must be SUCCESS/FAIL")

    clauses = ["ssl.tenant_id = %s"]
    params: list[Any] = [tenant["id"]]
    if profile_id:
        clauses.append("ssl.profile_id = %s")
        params.append(profile_id)
    if normalized_status:
        clauses.append("ssl.status = %s")
        params.append(normalized_status)
    params.append(limit)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT ssl.id,
                   t.tenant_code,
                   ssl.profile_id,
                   gp.profile_name,
                   ssl.direction,
                   ssl.status,
                   ssl.error_message,
                   ssl.created_at
            FROM sheets_sync_log ssl
            JOIN tenants t ON t.id = ssl.tenant_id
            LEFT JOIN google_sheet_profiles gp ON gp.id = ssl.profile_id
            WHERE {' AND '.join(clauses)}
            ORDER BY ssl.created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()

    return [
        GoogleSheetSyncLogOut(
            id=row["id"],
            tenant_code=row["tenant_code"],
            profile_id=row.get("profile_id"),
            profile_name=row.get("profile_name"),
            direction=row["direction"],
            status=row["status"],
            error_message=row.get("error_message"),
            created_at=row["created_at"],
        )
        for row in rows
    ]
