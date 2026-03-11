from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import logging
from time import perf_counter
from typing import Any, Iterable

from ..config import settings

KST = timezone(timedelta(hours=9))
APPLE_TENANT_CODE = "APPLE"
CONTRACT_VERSION = "2026-03-07.phase4"
UNSUPPORTED_PHASE4 = "UNSUPPORTED_PHASE4"
SECTION_STATE_SUPPORTED_PRESENT = "supported_present"
SECTION_STATE_SUPPORTED_MISSING = "supported_missing"
SECTION_STATE_UNSUPPORTED = "unsupported"
SECTION_STATE_CONFLICTED = "conflicted"
CONFIDENCE_READY = "ready"
CONFIDENCE_WARNING = "warning"
CONFIDENCE_CONFLICT = "conflict"
CONFIDENCE_INCOMPLETE = "incomplete"
CONFIDENCE_UNSUPPORTED = "unsupported_section_present"
SERVICE_STATE_HEALTHY = "supported_and_healthy"
SERVICE_STATE_WARNING = "supported_with_warnings"
SERVICE_STATE_INCOMPLETE = "incomplete_source_data"
SERVICE_STATE_SITE_NOT_ONBOARDED = "site_not_onboarded"
SERVICE_STATE_IDENTITY_MISMATCH = "identity_mismatch_detected"
SERVICE_STATE_CONFLICT = "contract_conflict_detected"
SERVICE_STATE_FAILURE = "contract_failure"
SERVICE_SIGNAL_UNSUPPORTED = "unsupported_field_present"
SERVICE_SIGNAL_IDENTITY_MISMATCH = "identity_mismatch_detected"
SERVICE_SIGNAL_DATE_BOUNDARY = "date_boundary_anomaly_detected"
SERVICE_SIGNAL_SLOW = "slow_generation_detected"
ROLL_OUT_OPEN = "open"
ROLL_OUT_BLOCKED = "blocked"

logger = logging.getLogger(__name__)


def _to_text(value: Any) -> str:
    return str(value or "").strip()


def _to_upper(value: Any) -> str:
    return _to_text(value).upper()


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _ensure_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).astimezone(KST)
    return value.astimezone(KST)


def _to_iso_datetime(value: datetime | None) -> str | None:
    if not isinstance(value, datetime):
        return None
    return _ensure_kst(value).isoformat()


def _parse_iso_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    raw = _to_text(value)
    if not raw:
        raise ValueError("week_start is required")
    return date.fromisoformat(raw)


def normalize_week_start(value: str | date) -> date:
    parsed = _parse_iso_date(value)
    return parsed - timedelta(days=parsed.weekday())


def week_dates(week_start: date) -> list[date]:
    return [week_start + timedelta(days=offset) for offset in range(7)]


def week_bounds_utc(week_start: date) -> tuple[datetime, datetime]:
    start_kst = datetime.combine(week_start, time.min, tzinfo=KST)
    end_kst = start_kst + timedelta(days=8)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def build_site_identity_payload(tenant_code: str, row: dict[str, Any] | None) -> dict[str, Any]:
    row = row or {}
    site_code = _to_upper(row.get("site_code"))
    site_id = _to_text(row.get("site_id") or row.get("id"))
    canonical_site_key = f"{_to_upper(tenant_code)}:{site_code}" if site_code else f"{_to_upper(tenant_code)}:{site_id}"
    return {
        "canonical_site_key": canonical_site_key,
        "site_id": site_id or None,
        "site_code": site_code or None,
        "site_name": _to_text(row.get("site_name")) or None,
        "company_id": _to_text(row.get("company_id")) or None,
        "company_code": _to_upper(row.get("company_code")) or None,
        "company_name": _to_text(row.get("company_name")) or None,
        "display_keys": {
            "site_code": site_code or None,
            "site_name": _to_text(row.get("site_name")) or None,
            "company_code": _to_upper(row.get("company_code")) or None,
            "company_name": _to_text(row.get("company_name")) or None,
        },
    }


def build_employee_identity_payload(tenant_code: str, row: dict[str, Any] | None) -> tuple[dict[str, Any], list[str]]:
    row = row or {}
    employee_uuid = _to_text(row.get("employee_uuid")) or None
    employee_code = _to_upper(row.get("employee_code")) or None
    employee_id = _to_text(row.get("employee_id") or row.get("id")) or None
    canonical_employee_key = employee_uuid or (f"{_to_upper(tenant_code)}:{employee_code}" if employee_code else f"{_to_upper(tenant_code)}:{employee_id}")
    warnings: list[str] = []
    if not employee_code:
        warnings.append("employee_code_missing")
    payload = {
        "canonical_employee_key": canonical_employee_key,
        "employee_id": employee_id,
        "employee_uuid": employee_uuid,
        "employee_code": employee_code,
        "external_employee_key": _to_text(row.get("external_employee_key")) or None,
        "linked_employee_id": _to_text(row.get("linked_employee_id")) or None,
        "full_name": _to_text(row.get("full_name") or row.get("employee_name")) or None,
        "duty_role": _to_upper(row.get("duty_role")) or None,
        "identity_keys": {
            "employee_uuid": employee_uuid,
            "employee_code": employee_code,
            "external_employee_key": _to_text(row.get("external_employee_key")) or None,
            "linked_employee_id": _to_text(row.get("linked_employee_id")) or None,
        },
    }
    return payload, warnings


def build_unsupported_summary(field_name: str, reason: str = UNSUPPORTED_PHASE4) -> dict[str, Any]:
    payload = {
        "supported": False,
        "status": reason,
        "field": field_name,
        "entries": [],
        "count": 0,
        "missing_data_flags": [],
        "conflict_flags": [],
        "trace_refs": [],
    }
    return _finalize_truth_section(payload, has_data=False)


def _finalize_truth_section(payload: dict[str, Any], *, has_data: bool) -> dict[str, Any]:
    supported = bool(payload.get("supported", True))
    missing_data_flags = list(payload.get("missing_data_flags") or [])
    conflict_flags = list(payload.get("conflict_flags") or [])
    if not supported:
        section_state = SECTION_STATE_UNSUPPORTED
    elif conflict_flags:
        section_state = SECTION_STATE_CONFLICTED
    elif missing_data_flags:
        section_state = SECTION_STATE_SUPPORTED_MISSING
    else:
        section_state = SECTION_STATE_SUPPORTED_PRESENT
    payload["section_state"] = section_state
    payload["has_data"] = bool(has_data)
    payload["is_missing_for_scope"] = section_state == SECTION_STATE_SUPPORTED_MISSING
    payload["trace_refs"] = list(payload.get("trace_refs") or [])
    return payload


def _base_trace_ref(source_table: str, *, row_id: Any = None, **fields: Any) -> dict[str, Any]:
    payload = {"source_table": source_table}
    if row_id is not None and _to_text(row_id):
        payload["row_id"] = _to_text(row_id)
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, datetime):
            payload[key] = _to_iso_datetime(value)
        elif isinstance(value, date):
            payload[key] = value.isoformat()
        else:
            text = _to_text(value)
            payload[key] = text if text else value
    return payload


def _make_discrepancy(
    code: str,
    *,
    severity: str,
    scope: str,
    message: str,
    business_date: date | str | None = None,
    site: dict[str, Any] | None = None,
    employee: dict[str, Any] | None = None,
    trace_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "severity": severity,
        "scope": scope,
        "message": message,
        "trace_refs": list(trace_refs or []),
    }
    if isinstance(business_date, date):
        payload["business_date"] = business_date.isoformat()
    elif business_date:
        payload["business_date"] = _to_text(business_date)
    if site:
        payload["site"] = {
            "canonical_site_key": site.get("canonical_site_key"),
            "site_code": site.get("site_code"),
            "site_name": site.get("site_name"),
        }
    if employee:
        payload["employee"] = {
            "canonical_employee_key": employee.get("canonical_employee_key"),
            "employee_code": employee.get("employee_code"),
            "full_name": employee.get("full_name"),
        }
    return payload


def _compute_confidence_state(
    *,
    discrepancies: list[dict[str, Any]] | None = None,
    unsupported_section_present: bool = False,
) -> str:
    severities = {item.get("severity") for item in discrepancies or []}
    if "hard_error" in severities:
        return CONFIDENCE_CONFLICT
    if "warning" in severities:
        return CONFIDENCE_WARNING
    if unsupported_section_present:
        return CONFIDENCE_UNSUPPORTED
    if "informational_anomaly" in severities:
        return CONFIDENCE_INCOMPLETE
    return CONFIDENCE_READY


def _normalize_rollout_allowlist() -> set[str]:
    return {_to_upper(item) for item in (settings.apple_weekly_truth_site_allowlist or []) if _to_text(item)}


def _build_rollout_payload(
    *,
    fetched_sites: list[dict[str, Any]],
    requested_site_code: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    allowlist = _normalize_rollout_allowlist()
    requested_code = _to_upper(requested_site_code) or None
    mode = "allowlist" if allowlist else "all_sites"
    site_status_by_code: dict[str, str] = {}
    filtered_sites: list[dict[str, Any]] = []
    for row in fetched_sites:
        code = _to_upper(row.get("site_code"))
        if not code:
            continue
        enabled = not allowlist or code in allowlist
        site_status_by_code[code] = "enabled" if enabled else "not_onboarded"
        if enabled:
            filtered_sites.append(row)
    blocked_requested = bool(requested_code and allowlist and requested_code not in allowlist)
    if blocked_requested and requested_code not in site_status_by_code:
        site_status_by_code[requested_code] = "not_onboarded"
    rollout_payload = {
        "mode": mode,
        "gate_status": ROLL_OUT_BLOCKED if blocked_requested else ROLL_OUT_OPEN,
        "requested_site_code": requested_code,
        "requested_site_onboarded": not blocked_requested,
        "allowlisted_site_codes": sorted(allowlist),
        "enabled_site_codes": sorted([_to_upper(row.get("site_code")) for row in filtered_sites if _to_text(row.get("site_code"))]),
        "site_status_by_code": site_status_by_code,
        "fully_supported_site_codes": sorted([_to_upper(row.get("site_code")) for row in filtered_sites if _to_text(row.get("site_code"))]),
    }
    return rollout_payload, filtered_sites, blocked_requested


def _build_domain_capabilities() -> dict[str, Any]:
    return {
        "schedule": {"supported": True, "scope": "employee_day,site_day"},
        "attendance": {"supported": True, "scope": "employee_day,site_day"},
        "leave": {"supported": True, "scope": "employee_day,site_day"},
        "late_tardy": {"supported": True, "scope": "employee_day,site_day"},
        "overtime": {"supported": True, "scope": "employee_day,site_day"},
        "overnight": {"supported": True, "scope": "employee_day,site_day"},
        "support_assignment": {"supported": True, "scope": "employee_day,site_day"},
        "event_additional_site_day": {"supported": True, "scope": "site_day"},
        "event_additional_employee_day": {"supported": False, "scope": "employee_day", "status": "SITE_DAY_ONLY"},
    }


def _count_service_signal_matches(values: Iterable[str], *, prefixes: tuple[str, ...] = (), exact: set[str] | None = None) -> int:
    exact = exact or set()
    total = 0
    for value in values:
        text = _to_text(value)
        if not text:
            continue
        if text in exact or any(text.startswith(prefix) for prefix in prefixes):
            total += 1
    return total


def _derive_service_status(
    *,
    contract_state: str,
    rollout_payload: dict[str, Any],
    warnings: list[str],
    unsupported_fields: dict[str, Any],
    discrepancy_summary: dict[str, Any],
    discrepancies: list[dict[str, Any]],
    latency_ms: int,
) -> tuple[str, list[str], dict[str, int]]:
    discrepancy_codes = [_to_text(item.get("code")) for item in discrepancies]
    identity_mismatch_count = _count_service_signal_matches(
        warnings,
        prefixes=("site_mismatch:",),
        exact={"employee_code_missing"},
    ) + _count_service_signal_matches(
        discrepancy_codes,
        exact={"attendance_site_mismatch", "support_assignment_site_mismatch"},
    )
    date_boundary_anomaly_count = _count_service_signal_matches(
        warnings,
        prefixes=("attendance_orphan_checkout:", "attendance_missing_checkout:"),
    ) + _count_service_signal_matches(
        discrepancy_codes,
        exact={
            "overnight_headcount_mismatch",
            "overnight_record_without_attendance_cross_day",
            "attendance_cross_day_without_overnight_record",
            "duplicate_overnight_records",
        },
    )
    signals: list[str] = []
    if unsupported_fields:
        signals.append(SERVICE_SIGNAL_UNSUPPORTED)
    if identity_mismatch_count:
        signals.append(SERVICE_SIGNAL_IDENTITY_MISMATCH)
    if latency_ms >= settings.apple_weekly_truth_slow_ms:
        signals.append(SERVICE_SIGNAL_SLOW)
    metrics = {
        "identity_mismatch_count": identity_mismatch_count,
        "date_boundary_anomaly_count": date_boundary_anomaly_count,
    }
    if rollout_payload.get("gate_status") == ROLL_OUT_BLOCKED:
        return SERVICE_STATE_SITE_NOT_ONBOARDED, signals, metrics
    if contract_state == CONFIDENCE_CONFLICT:
        return SERVICE_STATE_CONFLICT, signals, metrics
    if identity_mismatch_count:
        return SERVICE_STATE_IDENTITY_MISMATCH, signals, metrics
    if contract_state == CONFIDENCE_INCOMPLETE:
        return SERVICE_STATE_INCOMPLETE, signals, metrics
    if contract_state == CONFIDENCE_WARNING:
        return SERVICE_STATE_WARNING, signals, metrics
    return SERVICE_STATE_HEALTHY, signals, metrics


def build_apple_weekly_truth_failure_contract(
    *,
    tenant_code: str,
    week_start: date,
    site_code: str | None,
    message: str,
    debug_enabled: bool = False,
) -> dict[str, Any]:
    week_start_value = normalize_week_start(week_start)
    week_end = week_start_value + timedelta(days=6)
    unsupported_fields = {
        "overtime_summary.normal_scheduled_minutes": {
            "supported": False,
            "status": UNSUPPORTED_PHASE4,
            "reason": "ARLS does not own Sentrix baseline scheduled-minute policy. The contract exposes operational overtime truth only.",
        },
        "overtime_summary.net_extension_minutes_vs_baseline": {
            "supported": False,
            "status": UNSUPPORTED_PHASE4,
            "reason": "Net overtime versus Sentrix baseline is intentionally left to Sentrix. ARLS exposes attendance, schedule presence, and approved overtime inputs separately.",
        },
        "employee_day_rows.event_additional_note_summary": {
            "supported": False,
            "status": "SITE_DAY_ONLY",
            "reason": "Event and additional note truth is normalized at site/day scope, not employee/day scope.",
        },
    }
    contract = {
        "contract_version": CONTRACT_VERSION,
        "tenant": {
            "tenant_id": None,
            "tenant_code": _to_upper(tenant_code) or APPLE_TENANT_CODE,
            "tenant_name": None,
        },
        "scope": {
            "week_start": _iso_date_key(week_start_value),
            "week_end": _iso_date_key(week_end),
            "site_code": _to_upper(site_code) or None,
            "site_count": 0,
        },
        "identity_rules": {
            "canonical_site_key": "tenant_code:site_code (fallback tenant_code:site_id)",
            "canonical_employee_key": "employee_uuid (fallback tenant_code:employee_code, then tenant_code:employee_id)",
            "site_display_keys": ["site_code", "site_name", "company_code", "company_name"],
            "employee_identity_keys": ["employee_uuid", "employee_code", "external_employee_key", "linked_employee_id"],
        },
        "business_date_rules": {
            "week_scope": "week_start is normalized to Monday in KST; week_end is week_start + 6 days.",
            "schedule": "monthly_schedules.schedule_date is the business date.",
            "attendance": "business date is the KST date of check_in.",
            "leave": "approved leave_requests are expanded date-by-date from start_at to end_at inclusive.",
            "late_tardy": "late_shift_log.work_date is the business date.",
            "overtime": "ARLS exposes operational overtime truth only; Sentrix baseline math remains external.",
            "overnight": "overnight truth is attributed to the originating attendance business date and reconciled at site/day scope.",
            "support_assignment": "support_assignment.work_date is the business date.",
            "event_additional": "daily_event_log.work_date is the business date.",
        },
        "unsupported_fields": unsupported_fields,
        "domain_capabilities": _build_domain_capabilities(),
        "contract_state": CONFIDENCE_CONFLICT,
        "service_state": SERVICE_STATE_FAILURE,
        "service_signals": [SERVICE_SIGNAL_UNSUPPORTED],
        "discrepancy_summary": {
            "employee_day": {"hard_error": 1, "warning": 0, "informational_anomaly": 0},
            "site_day": {"hard_error": 0, "warning": 0, "informational_anomaly": 0},
        },
        "employee_day_rows": [],
        "site_day_summaries": [],
        "warnings": [],
        "rollout": {
            "mode": "unknown",
            "gate_status": ROLL_OUT_OPEN,
            "requested_site_code": _to_upper(site_code) or None,
            "requested_site_onboarded": True,
            "allowlisted_site_codes": sorted(_normalize_rollout_allowlist()),
            "enabled_site_codes": [],
            "site_status_by_code": {},
            "fully_supported_site_codes": [],
        },
        "failure_mode": {
            "state": SERVICE_STATE_FAILURE,
            "retryable": True,
            "message": message,
        },
        "observability": {
            "contract_version": CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": None,
            "request_scope": {
                "tenant_code": _to_upper(tenant_code) or APPLE_TENANT_CODE,
                "week_start": _iso_date_key(week_start_value),
                "site_code": _to_upper(site_code) or None,
            },
            "source_coverage": {},
            "discrepancy_counts": {
                "employee_day": {"hard_error": 1, "warning": 0, "informational_anomaly": 0},
                "site_day": {"hard_error": 0, "warning": 0, "informational_anomaly": 0},
            },
            "unsupported_fields": sorted(unsupported_fields.keys()),
            "identity_mismatch_count": 0,
            "date_boundary_anomaly_count": 0,
        },
        "legacy_sheet_paths": {
            "isolated": True,
            "paths": [
                "/api/v1/integrations/google-sheets/profiles",
                "/api/v1/integrations/google-sheets/profiles/{profile_id}/sync",
                "/api/v1/integrations/google-sheets/support-assignments/webhook",
            ],
            "note": "These legacy ARLS Google Sheets paths remain separate from the Apple Weekly truth contract and are not called by this endpoint.",
        },
    }
    if debug_enabled:
        contract["debug"] = {
            "source_counts": {},
            "site_codes": [],
            "discrepancy_summary": contract["discrepancy_summary"],
            "failure_mode": contract["failure_mode"],
        }
    return contract


def _date_range_inclusive(start_date: date, end_date: date) -> Iterable[date]:
    cursor = start_date
    while cursor <= end_date:
        yield cursor
        cursor = cursor + timedelta(days=1)


def expand_leave_records_by_business_date(rows: list[dict[str, Any]], week_start: date, week_end: date) -> dict[tuple[str, date], list[dict[str, Any]]]:
    expanded: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        employee_id = _to_text(row.get("employee_id"))
        if not employee_id:
            continue
        start_value = row.get("start_at")
        end_value = row.get("end_at")
        if isinstance(start_value, datetime):
            start_date = start_value.date()
        else:
            start_date = start_value
        if isinstance(end_value, datetime):
            end_date = end_value.date()
        else:
            end_date = end_value
        if not isinstance(start_date, date) or not isinstance(end_date, date):
            continue
        for business_date in _date_range_inclusive(start_date, end_date):
            if business_date < week_start or business_date > week_end:
                continue
            expanded[(employee_id, business_date)].append(
                {
                    "leave_request_id": _to_text(row.get("id")) or None,
                    "supported": True,
                    "has_leave": True,
                    "leave_type": _to_text(row.get("leave_type")).lower() or None,
                    "half_day_slot": _to_text(row.get("half_day_slot")).lower() or None,
                    "status": _to_text(row.get("status")).lower() or "approved",
                    "reason": _to_text(row.get("reason")) or None,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                }
            )
    return dict(expanded)


def build_attendance_sessions_from_rows(rows: list[dict[str, Any]], week_start: date, week_end: date) -> tuple[dict[tuple[str, date], dict[str, Any]], list[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        employee_id = _to_text(row.get("employee_id"))
        if not employee_id:
            continue
        grouped[employee_id].append(dict(row))

    sessions: dict[tuple[str, date], dict[str, Any]] = {}
    warnings: list[str] = []
    for employee_id, employee_rows in grouped.items():
        employee_rows.sort(key=lambda item: item.get("event_at") or datetime.min.replace(tzinfo=timezone.utc))
        open_session: dict[str, Any] | None = None
        for row in employee_rows:
            event_type = _to_text(row.get("event_type")).lower()
            event_at = row.get("event_at")
            if not isinstance(event_at, datetime):
                continue
            local_event_at = _ensure_kst(event_at)
            if event_type == "check_in":
                if open_session and not open_session.get("check_out_at"):
                    business_date = open_session["business_date"]
                    if week_start <= business_date <= week_end:
                        sessions[(employee_id, business_date)] = open_session
                    warnings.append(f"attendance_missing_checkout:{employee_id}:{business_date.isoformat()}")
                open_session = {
                    "employee_id": employee_id,
                    "business_date": local_event_at.date(),
                    "site_id": _to_text(row.get("site_id")) or None,
                    "site_code": _to_upper(row.get("site_code")) or None,
                    "check_in_at": event_at,
                    "check_out_at": None,
                    "worked_minutes": None,
                    "auto_checkout": False,
                    "status": "present",
                }
                continue
            if event_type != "check_out":
                continue
            if open_session and not open_session.get("check_out_at"):
                open_session["check_out_at"] = event_at
                delta = int(max(0, (_ensure_kst(event_at) - _ensure_kst(open_session["check_in_at"])).total_seconds() // 60))
                open_session["worked_minutes"] = delta
                open_session["auto_checkout"] = bool(row.get("auto_checkout"))
                business_date = open_session["business_date"]
                if week_start <= business_date <= week_end:
                    sessions[(employee_id, business_date)] = open_session
                open_session = None
            else:
                business_date = local_event_at.date()
                orphan = {
                    "employee_id": employee_id,
                    "business_date": business_date,
                    "site_id": _to_text(row.get("site_id")) or None,
                    "site_code": _to_upper(row.get("site_code")) or None,
                    "check_in_at": None,
                    "check_out_at": event_at,
                    "worked_minutes": None,
                    "auto_checkout": bool(row.get("auto_checkout")),
                    "status": "orphan_check_out",
                }
                if week_start <= business_date <= week_end:
                    sessions[(employee_id, business_date)] = orphan
                warnings.append(f"attendance_orphan_checkout:{employee_id}:{business_date.isoformat()}")
        if open_session and not open_session.get("check_out_at"):
            business_date = open_session["business_date"]
            if week_start <= business_date <= week_end:
                sessions[(employee_id, business_date)] = open_session
            warnings.append(f"attendance_missing_checkout:{employee_id}:{business_date.isoformat()}")
    return sessions, warnings


def build_overtime_summary(
    soc_row: dict[str, Any] | None,
    apple_daytime_row: dict[str, Any] | None,
    *,
    attendance_row: dict[str, Any] | None = None,
    schedule_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    soc_minutes = _safe_int((soc_row or {}).get("approved_minutes"))
    soc_units = _safe_float((soc_row or {}).get("overtime_units"))
    soc_hours_step = _safe_float((soc_row or {}).get("overtime_hours_step"))
    apple_hours = _safe_float((apple_daytime_row or {}).get("hours"))
    apple_status = _to_text((apple_daytime_row or {}).get("status")) or None
    sources: list[str] = []
    if soc_row:
        sources.append("soc_overtime_approvals")
    if apple_daytime_row:
        sources.append("apple_daytime_ot")
    derived_from_attendance = bool(
        attendance_row
        and (
            _to_upper((soc_row or {}).get("source")) == "ATTENDANCE_CLOSE"
            or _to_upper((soc_row or {}).get("overtime_source")) == "ATTENDANCE_CLOSE"
            or apple_daytime_row
        )
    )
    attendance_extension_minutes = soc_minutes or int(round(apple_hours * 60))
    precision = None
    if soc_row and (soc_row or {}).get("approved_minutes") is not None:
        precision = "approved_minutes"
    elif apple_daytime_row and (apple_daytime_row or {}).get("hours") is not None:
        precision = "hours"
    missing_data_flags: list[str] = []
    conflict_flags: list[str] = []
    has_overtime = bool(soc_minutes or apple_hours)
    if has_overtime and not attendance_row:
        missing_data_flags.append("attendance_missing_for_overtime")
    if has_overtime and not schedule_row:
        missing_data_flags.append("schedule_missing_for_overtime")
    if soc_row and apple_daytime_row and soc_minutes and apple_hours and soc_minutes != int(round(apple_hours * 60)):
        conflict_flags.append("overtime_source_mismatch")
    payload = {
        "supported": True,
        "has_overtime": has_overtime,
        "derived_from_attendance": derived_from_attendance,
        "attendance_extension_minutes": attendance_extension_minutes or 0,
        "attendance_extension_precision": precision,
        "worked_minutes": (attendance_row or {}).get("worked_minutes"),
        "scheduled_shift_present": schedule_row is not None,
        "scheduled_shift_type": _to_text((schedule_row or {}).get("shift_type")) or None,
        "normal_scheduled_minutes_supported": False,
        "net_extension_minutes_supported": False,
        "soc_approved_minutes": soc_minutes,
        "soc_overtime_units": soc_units,
        "soc_overtime_hours_step": soc_hours_step,
        "apple_daytime_ot_hours": apple_hours,
        "apple_daytime_ot_status": apple_status,
        "apple_daytime_ot_reason": _to_text((apple_daytime_row or {}).get("reason")) or None,
        "apple_daytime_ot_source_event_uid": _to_text((apple_daytime_row or {}).get("source_event_uid")) or None,
        "sources": sources,
        "missing_data_flags": missing_data_flags,
        "conflict_flags": conflict_flags,
        "trace_refs": [
            _base_trace_ref(
                "soc_overtime_approvals",
                row_id=(soc_row or {}).get("overtime_approval_id"),
                employee_id=(soc_row or {}).get("employee_id"),
                site_id=(soc_row or {}).get("site_id"),
                work_date=(soc_row or {}).get("work_date"),
            )
            for source, row in (("soc", soc_row),)
            if row
        ]
        + [
            _base_trace_ref(
                "apple_daytime_ot",
                row_id=(apple_daytime_row or {}).get("apple_daytime_ot_id"),
                employee_id=(apple_daytime_row or {}).get("employee_id"),
                site_id=(apple_daytime_row or {}).get("site_id"),
                work_date=(apple_daytime_row or {}).get("work_date"),
                source_event_uid=(apple_daytime_row or {}).get("source_event_uid"),
            )
            for row in [apple_daytime_row]
            if row
        ]
        + [
            _base_trace_ref(
                "attendance_records",
                employee_id=(attendance_row or {}).get("employee_id"),
                site_id=(attendance_row or {}).get("site_id"),
                business_date=(attendance_row or {}).get("business_date"),
                check_in_at=(attendance_row or {}).get("check_in_at"),
                check_out_at=(attendance_row or {}).get("check_out_at"),
            )
            for row in [attendance_row]
            if row
        ],
    }
    return _finalize_truth_section(payload, has_data=has_overtime)


def build_late_summary(late_row: dict[str, Any] | None) -> dict[str, Any]:
    if not late_row:
        payload = {
            "supported": True,
            "is_late": False,
            "status": "on_time",
            "minutes_late": 0,
            "exact_minutes_available": False,
            "precision": None,
            "note": None,
            "source": None,
            "missing_data_flags": [],
            "conflict_flags": [],
            "trace_refs": [],
        }
        return _finalize_truth_section(payload, has_data=False)
    has_minutes = late_row.get("minutes_late") is not None
    payload = {
        "supported": True,
        "is_late": True,
        "status": "late",
        "minutes_late": _safe_int(late_row.get("minutes_late")) if has_minutes else None,
        "exact_minutes_available": has_minutes,
        "precision": "exact_minutes" if has_minutes else "missing",
        "note": _to_text(late_row.get("note")) or None,
        "source": "late_shift_log",
        "missing_data_flags": [] if has_minutes else ["minutes_late_missing"],
        "conflict_flags": [],
        "trace_refs": [
            _base_trace_ref(
                "late_shift_log",
                row_id=late_row.get("late_log_id"),
                employee_id=late_row.get("employee_id"),
                site_id=late_row.get("site_id"),
                work_date=late_row.get("work_date"),
            )
        ],
    }
    return _finalize_truth_section(payload, has_data=True)


def build_leave_summary(
    leave_rows: list[dict[str, Any]] | dict[str, Any] | None,
    *,
    schedule_row: dict[str, Any] | None = None,
    attendance_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(leave_rows, list):
        rows = [row for row in leave_rows if row]
    elif leave_rows:
        rows = [leave_rows]
    else:
        rows = []
    if not rows:
        payload = {
            "supported": True,
            "source": "leave_requests",
            "has_leave": False,
            "leave_type": None,
            "leave_types": [],
            "half_day_slot": None,
            "half_day_slots": [],
            "status": None,
            "reason": None,
            "reasons": [],
            "entry_count": 0,
            "is_partial_leave": False,
            "staffing_impact": None,
            "scheduled_overlap": False,
            "attendance_overlap": False,
            "entries": [],
            "missing_data_flags": [],
            "conflict_flags": [],
            "trace_refs": [],
        }
        return _finalize_truth_section(payload, has_data=False)
    leave_types = sorted({_to_text(row.get("leave_type")).lower() for row in rows if _to_text(row.get("leave_type"))})
    half_day_slots = sorted({_to_text(row.get("half_day_slot")).lower() for row in rows if _to_text(row.get("half_day_slot"))})
    reasons = sorted({_to_text(row.get("reason")) for row in rows if _to_text(row.get("reason"))})
    primary = rows[0]
    is_partial_leave = bool(half_day_slots)
    attendance_overlap = bool((attendance_row or {}).get("check_in_at") or (attendance_row or {}).get("check_out_at"))
    scheduled_overlap = schedule_row is not None and _to_text((schedule_row or {}).get("shift_type")).lower() not in {"", "off", "holiday"}
    conflict_flags: list[str] = []
    if len(leave_types) > 1:
        conflict_flags.append("multiple_leave_types_same_day")
    if attendance_overlap:
        conflict_flags.append("leave_attendance_overlap")
    payload = {
        "supported": True,
        "source": "leave_requests",
        "has_leave": True,
        "leave_type": _to_text(primary.get("leave_type")).lower() or None,
        "leave_types": leave_types,
        "half_day_slot": _to_text(primary.get("half_day_slot")).lower() or None,
        "half_day_slots": half_day_slots,
        "status": _to_text(primary.get("status")).lower() or "approved",
        "reason": _to_text(primary.get("reason")) or None,
        "reasons": reasons,
        "entry_count": len(rows),
        "is_partial_leave": is_partial_leave,
        "staffing_impact": "partial_leave" if is_partial_leave else "full_day_leave",
        "scheduled_overlap": scheduled_overlap,
        "attendance_overlap": attendance_overlap,
        "entries": [
            {
                "leave_request_id": _to_text(row.get("leave_request_id") or row.get("id")) or None,
                "leave_type": _to_text(row.get("leave_type")).lower() or None,
                "half_day_slot": _to_text(row.get("half_day_slot")).lower() or None,
                "status": _to_text(row.get("status")).lower() or "approved",
                "reason": _to_text(row.get("reason")) or None,
                "start_date": _to_text(row.get("start_date")) or None,
                "end_date": _to_text(row.get("end_date")) or None,
            }
            for row in rows
        ],
        "missing_data_flags": [],
        "conflict_flags": conflict_flags,
        "trace_refs": [
            _base_trace_ref(
                "leave_requests",
                row_id=row.get("leave_request_id") or row.get("id"),
                employee_id=row.get("employee_id"),
                start_date=row.get("start_date"),
                end_date=row.get("end_date"),
            )
            for row in rows
        ],
    }
    return _finalize_truth_section(payload, has_data=True)


def _parse_time_range(value: Any) -> tuple[str | None, str | None, bool]:
    raw = _to_text(value)
    if "-" not in raw:
        return None, None, False
    start_raw, end_raw = [part.strip() for part in raw.split("-", 1)]
    if not start_raw or not end_raw:
        return None, None, False
    try:
        start_time = datetime.strptime(start_raw, "%H:%M").time()
        end_time = datetime.strptime(end_raw, "%H:%M").time()
    except ValueError:
        return start_raw, end_raw, False
    crosses_midnight = (end_time.hour, end_time.minute) <= (start_time.hour, start_time.minute)
    return start_time.strftime("%H:%M"), end_time.strftime("%H:%M"), crosses_midnight


def build_employee_overnight_summary(attendance_row: dict[str, Any] | None, site_overnight_row: dict[str, Any] | None) -> dict[str, Any]:
    if not attendance_row or not attendance_row.get("check_in_at") or not attendance_row.get("check_out_at"):
        payload = {
            "supported": True,
            "scope": "employee_day",
            "has_overnight": False,
            "crosses_midnight": False,
            "origin_business_date": None,
            "target_calendar_date": None,
            "start_at": None,
            "end_at": None,
            "worked_minutes": None,
            "site_day_recorded": bool(site_overnight_row),
            "missing_data_flags": [],
            "conflict_flags": [],
            "trace_refs": [],
        }
        return _finalize_truth_section(payload, has_data=False)
    check_in_local = _ensure_kst(attendance_row["check_in_at"])
    check_out_local = _ensure_kst(attendance_row["check_out_at"])
    crosses_midnight = check_out_local.date() > check_in_local.date()
    payload = {
        "supported": True,
        "scope": "employee_day",
        "has_overnight": crosses_midnight,
        "crosses_midnight": crosses_midnight,
        "origin_business_date": check_in_local.date().isoformat(),
        "target_calendar_date": check_out_local.date().isoformat() if crosses_midnight else None,
        "start_at": check_in_local.isoformat(),
        "end_at": check_out_local.isoformat(),
        "worked_minutes": attendance_row.get("worked_minutes"),
        "site_day_recorded": bool(site_overnight_row),
        "missing_data_flags": [],
        "conflict_flags": [],
        "trace_refs": [
            _base_trace_ref(
                "attendance_records",
                employee_id=attendance_row.get("employee_id"),
                site_id=attendance_row.get("site_id"),
                business_date=attendance_row.get("business_date"),
                check_in_at=attendance_row.get("check_in_at"),
                check_out_at=attendance_row.get("check_out_at"),
            )
        ] + (
            [
                _base_trace_ref(
                    "apple_report_overnight_records",
                    row_id=site_overnight_row.get("overnight_record_id"),
                    site_id=site_overnight_row.get("site_id"),
                    work_date=site_overnight_row.get("work_date"),
                    source_ticket_id=site_overnight_row.get("source_ticket_id"),
                )
            ]
            if site_overnight_row
            else []
        ),
    }
    return _finalize_truth_section(payload, has_data=crosses_midnight)


def build_site_overnight_summary(overnight_row: dict[str, Any] | None, *, business_date: date, attendance_cross_day_count: int) -> dict[str, Any]:
    start_local_time, end_local_time, crosses_midnight = _parse_time_range((overnight_row or {}).get("time_range"))
    recorded_headcount = _safe_int((overnight_row or {}).get("headcount"))
    if not overnight_row:
        crosses_midnight = attendance_cross_day_count > 0
    conflict_flags: list[str] = []
    reconciliation_status = "none"
    has_overnight = bool(overnight_row or attendance_cross_day_count)
    if overnight_row and attendance_cross_day_count:
        reconciliation_status = "matched" if recorded_headcount == attendance_cross_day_count else "mismatch"
        if recorded_headcount != attendance_cross_day_count:
            conflict_flags.append("overnight_headcount_mismatch")
    elif overnight_row:
        reconciliation_status = "record_only"
        conflict_flags.append("overnight_record_without_attendance_cross_day")
    elif attendance_cross_day_count:
        reconciliation_status = "attendance_only"
        conflict_flags.append("attendance_cross_day_without_overnight_record")
    payload = {
        "supported": True,
        "scope": "site_day",
        "has_overnight": has_overnight,
        "origin_business_date": business_date.isoformat(),
        "report_business_date": business_date.isoformat(),
        "target_calendar_date": (business_date + timedelta(days=1)).isoformat() if crosses_midnight else None,
        "crosses_midnight": crosses_midnight,
        "headcount": recorded_headcount,
        "attendance_cross_day_headcount": attendance_cross_day_count,
        "time_range": _to_text((overnight_row or {}).get("time_range")) or None,
        "start_local_time": start_local_time,
        "end_local_time": end_local_time,
        "hours": _safe_float((overnight_row or {}).get("hours")),
        "source_ticket_id": (overnight_row or {}).get("source_ticket_id"),
        "source_event_uid": _to_text((overnight_row or {}).get("source_event_uid")) or None,
        "reconciliation_status": reconciliation_status,
        "missing_data_flags": [],
        "conflict_flags": conflict_flags,
        "trace_refs": (
            [
                _base_trace_ref(
                    "apple_report_overnight_records",
                    row_id=(overnight_row or {}).get("overnight_record_id"),
                    site_id=(overnight_row or {}).get("site_id"),
                    work_date=(overnight_row or {}).get("work_date"),
                    source_ticket_id=(overnight_row or {}).get("source_ticket_id"),
                    source_event_uid=(overnight_row or {}).get("source_event_uid"),
                )
            ]
            if overnight_row
            else []
        ),
    }
    return _finalize_truth_section(payload, has_data=has_overnight)


def build_support_assignment_summary(rows: list[dict[str, Any]] | None, *, employee_id: str | None = None) -> dict[str, Any]:
    scoped_rows = list(rows or [])
    if employee_id is not None:
        employee_key = _to_text(employee_id)
        scoped_rows = [row for row in scoped_rows if _to_text(row.get("employee_id")) == employee_key]
    counts: dict[str, int] = defaultdict(int)
    entries: list[dict[str, Any]] = []
    linked_employee_count = 0
    for row in scoped_rows:
        worker_type = _to_upper(row.get("worker_type")) or "UNKNOWN"
        counts[worker_type] += 1
        linked_employee = bool(_to_text(row.get("employee_id")))
        if linked_employee:
            linked_employee_count += 1
        entries.append(
            {
                "worker_type": worker_type,
                "employee_id": _to_text(row.get("employee_id")) or None,
                "employee_code": _to_upper(row.get("employee_code")) or None,
                "employee_name": _to_text(row.get("employee_name") or row.get("full_name") or row.get("name")) or None,
                "name": _to_text(row.get("name")) or None,
                "source": _to_text(row.get("source")) or None,
                "assignment_kind": "support_assignment",
                "linked_employee": linked_employee,
            }
        )
    payload = {
        "supported": True,
        "scope": "employee_day" if employee_id is not None else "site_day",
        "has_support_assignment": bool(entries),
        "count": len(entries),
        "linked_employee_count": linked_employee_count,
        "unlinked_assignment_count": len(entries) - linked_employee_count,
        "by_worker_type": dict(sorted(counts.items())),
        "entries": entries,
        "missing_data_flags": [],
        "conflict_flags": [],
        "trace_refs": [
            _base_trace_ref(
                "support_assignment",
                row_id=row.get("support_assignment_id"),
                employee_id=row.get("employee_id"),
                site_id=row.get("site_id"),
                work_date=row.get("work_date"),
                worker_type=row.get("worker_type"),
            )
            for row in scoped_rows
        ],
    }
    return _finalize_truth_section(payload, has_data=bool(entries))


def build_event_additional_note_summary(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    scoped_rows = list(rows or [])
    event_entries: list[dict[str, Any]] = []
    additional_entries: list[dict[str, Any]] = []
    for row in scoped_rows:
        entry = {
            "type": _to_upper(row.get("type")) or None,
            "description": _to_text(row.get("description")) or None,
            "source": "daily_event_log",
        }
        if entry["type"] == "EVENT":
            event_entries.append(entry)
        else:
            additional_entries.append(entry)
    payload = {
        "supported": True,
        "count": len(scoped_rows),
        "event_count": len(event_entries),
        "additional_count": len(additional_entries),
        "event_entries": event_entries,
        "additional_entries": additional_entries,
        "missing_data_flags": [],
        "conflict_flags": [],
        "trace_refs": [
            _base_trace_ref(
                "daily_event_log",
                row_id=row.get("daily_event_id"),
                site_id=row.get("site_id"),
                work_date=row.get("work_date"),
                type=row.get("type"),
            )
            for row in scoped_rows
        ],
    }
    return _finalize_truth_section(payload, has_data=bool(scoped_rows))


def _iso_date_key(work_date: date) -> str:
    return work_date.isoformat()


def _fetch_sites(conn, tenant_id: str, site_code: str | None) -> list[dict[str, Any]]:
    clauses = ["s.tenant_id = %s", "COALESCE(s.is_active, TRUE) = TRUE"]
    params: list[Any] = [tenant_id]
    if _to_text(site_code):
        clauses.append("upper(s.site_code) = upper(%s)")
        params.append(_to_text(site_code))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id AS site_id, s.company_id, s.site_code, s.site_name,
                   COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM sites s
            LEFT JOIN companies c ON c.id = s.company_id
            WHERE {' AND '.join(clauses)}
            ORDER BY s.site_code
            """,
            tuple(params),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_schedule_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.id AS schedule_id, ms.employee_id, ms.site_id, ms.company_id, ms.schedule_date, ms.shift_type, ms.source,
                   ms.source_ticket_id, ms.schedule_note, ms.leader_user_id,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM monthly_schedules ms
            JOIN employees e ON e.id = ms.employee_id
            LEFT JOIN sites s ON s.id = ms.site_id
            LEFT JOIN companies c ON c.id = COALESCE(ms.company_id, s.company_id, e.company_id)
            WHERE ms.tenant_id = %s
              AND ms.schedule_date >= %s
              AND ms.schedule_date <= %s
              AND ms.site_id = ANY(%s::uuid[])
            ORDER BY ms.schedule_date, s.site_code, e.employee_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_attendance_rows(conn, tenant_id: str, range_start_utc: datetime, range_end_utc: datetime, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ar.id AS attendance_record_id, ar.employee_id, ar.site_id, ar.event_type, ar.event_at, COALESCE(ar.auto_checkout, FALSE) AS auto_checkout,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM attendance_records ar
            JOIN employees e ON e.id = ar.employee_id
            LEFT JOIN sites s ON s.id = COALESCE(ar.site_id, e.site_id)
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE ar.tenant_id = %s
              AND ar.event_type IN ('check_in', 'check_out')
              AND ar.event_at >= %s
              AND ar.event_at < %s
              AND COALESCE(ar.site_id, e.site_id) = ANY(%s::uuid[])
            ORDER BY ar.employee_id, ar.event_at ASC
            """,
            (tenant_id, range_start_utc, range_end_utc, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_leave_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lr.id, lr.employee_id, lr.leave_type, lr.half_day_slot, lr.start_at, lr.end_at, lr.reason, lr.status,
                   e.site_id, e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM leave_requests lr
            JOIN employees e ON e.id = lr.employee_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE lr.tenant_id = %s
              AND lr.status = 'approved'
              AND lr.end_at >= %s
              AND lr.start_at <= %s
              AND e.site_id = ANY(%s::uuid[])
            ORDER BY lr.start_at, e.employee_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_late_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ls.id AS late_log_id, ls.employee_id, ls.site_id, ls.work_date, ls.minutes_late, ls.note,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM late_shift_log ls
            JOIN employees e ON e.id = ls.employee_id
            LEFT JOIN sites s ON s.id = ls.site_id
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE ls.tenant_id = %s
              AND ls.work_date >= %s
              AND ls.work_date <= %s
              AND ls.site_id = ANY(%s::uuid[])
            ORDER BY ls.work_date, s.site_code, e.employee_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_soc_overtime_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT so.id AS overtime_approval_id, so.employee_id, so.site_id, so.work_date, so.approved_minutes, so.overtime_units,
                   so.overtime_hours_step, so.overtime_source, so.source, so.reason,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM soc_overtime_approvals so
            JOIN employees e ON e.id = so.employee_id
            LEFT JOIN sites s ON s.id = so.site_id
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE so.tenant_id = %s
              AND so.work_date >= %s
              AND so.work_date <= %s
              AND so.site_id = ANY(%s::uuid[])
            ORDER BY so.work_date, s.site_code, e.employee_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_apple_daytime_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ao.id AS apple_daytime_ot_id, ao.leader_user_id, ao.site_id, ao.work_date, ao.reason, ao.status, ao.hours,
                   ao.source, ao.source_event_uid, ao.closer_user_id,
                   u.employee_id,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM apple_daytime_ot ao
            LEFT JOIN arls_users u ON u.id = ao.leader_user_id
            LEFT JOIN employees e ON e.id = u.employee_id
            LEFT JOIN sites s ON s.id = ao.site_id
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE ao.tenant_id = %s
              AND ao.work_date >= %s
              AND ao.work_date <= %s
              AND ao.site_id = ANY(%s::uuid[])
            ORDER BY ao.work_date, s.site_code, e.employee_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_overnight_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ao.id AS overnight_record_id, ao.site_id, ao.work_date, ao.headcount, ao.time_range, ao.hours,
                   ao.source_ticket_id, ao.source_event_uid,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM apple_report_overnight_records ao
            LEFT JOIN sites s ON s.id = ao.site_id
            LEFT JOIN companies c ON c.id = s.company_id
            WHERE ao.tenant_id = %s
              AND ao.work_date >= %s
              AND ao.work_date <= %s
              AND ao.site_id = ANY(%s::uuid[])
            ORDER BY ao.work_date, s.site_code
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_support_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT sa.id AS support_assignment_id, sa.site_id, sa.work_date, sa.worker_type, sa.employee_id, sa.name, sa.source,
                   e.employee_uuid, e.employee_code, e.external_employee_key, e.linked_employee_id,
                   e.full_name AS employee_name, e.duty_role,
                   s.site_code, s.site_name, COALESCE(c.company_code, '') AS company_code,
                   COALESCE(c.company_name, '') AS company_name
            FROM support_assignment sa
            LEFT JOIN employees e ON e.id = sa.employee_id
            LEFT JOIN sites s ON s.id = sa.site_id
            LEFT JOIN companies c ON c.id = COALESCE(s.company_id, e.company_id)
            WHERE sa.tenant_id = %s
              AND sa.work_date >= %s
              AND sa.work_date <= %s
              AND sa.site_id = ANY(%s::uuid[])
            ORDER BY sa.work_date, s.site_code, sa.worker_type, sa.name
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _fetch_event_rows(conn, tenant_id: str, week_start: date, week_end: date, site_ids: list[str]) -> list[dict[str, Any]]:
    if not site_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT de.id AS daily_event_id, de.site_id, de.work_date, de.type, de.description,
                   s.site_code, s.site_name
            FROM daily_event_log de
            LEFT JOIN sites s ON s.id = de.site_id
            WHERE de.tenant_id = %s
              AND de.work_date >= %s
              AND de.work_date <= %s
              AND de.site_id = ANY(%s::uuid[])
            ORDER BY de.work_date, s.site_code, de.created_at
            """,
            (tenant_id, week_start, week_end, site_ids),
        )
        return [dict(row) for row in cur.fetchall()]


def _merge_employee_site_payload(base: dict[str, Any], site_payload: dict[str, Any], warnings: list[str], *, source_label: str) -> None:
    if not base.get("site_code"):
        base["site_code"] = site_payload.get("site_code")
        base["site_name"] = site_payload.get("site_name")
        base["company_code"] = site_payload.get("company_code")
        base["company_name"] = site_payload.get("company_name")
        base["site_id"] = site_payload.get("site_id")
        return
    existing_code = _to_upper(base.get("site_code"))
    incoming_code = _to_upper(site_payload.get("site_code"))
    if existing_code and incoming_code and existing_code != incoming_code:
        warnings.append(f"site_mismatch:{source_label}:{existing_code}:{incoming_code}")


def _build_row_discrepancies(
    *,
    business_date: date,
    site_payload: dict[str, Any],
    employee_payload: dict[str, Any],
    row_missing_data_flags: list[str],
    row_conflict_flags: list[str],
    row_warnings: list[str],
    attendance_row: dict[str, Any] | None,
    schedule_row: dict[str, Any] | None,
    leave_summary: dict[str, Any],
    late_summary: dict[str, Any],
    overtime_summary: dict[str, Any],
    overnight_summary: dict[str, Any],
    support_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    trace_refs = []
    for section in (leave_summary, late_summary, overtime_summary, overnight_summary, support_summary):
        trace_refs.extend(section.get("trace_refs") or [])

    discrepancies: list[dict[str, Any]] = []
    severity_map = {
        "attendance_site_mismatch": "hard_error",
        "attendance_missing_for_scheduled_shift": "warning",
        "schedule_missing_for_attendance": "warning",
        "leave_attendance_overlap": "warning",
        "late_leave_overlap": "warning",
        "support_assignment_site_mismatch": "warning",
        "minutes_late_missing": "warning",
        "attendance_missing_for_overtime": "hard_error",
        "schedule_missing_for_overtime": "warning",
        "overtime_source_mismatch": "warning",
        "multiple_leave_types_same_day": "informational_anomaly",
    }
    message_map = {
        "attendance_site_mismatch": "출퇴근 기록의 현장 식별자가 스케줄/직원 기준 현장과 다릅니다.",
        "attendance_missing_for_scheduled_shift": "스케줄은 있으나 출퇴근 기록이 없습니다.",
        "schedule_missing_for_attendance": "출퇴근 기록은 있으나 스케줄이 없습니다.",
        "leave_attendance_overlap": "휴가와 출퇴근 기록이 같은 업무일에 겹칩니다.",
        "late_leave_overlap": "휴가와 지각 기록이 같은 업무일에 겹칩니다.",
        "support_assignment_site_mismatch": "지원 배치 현장과 직원의 기준 현장이 다릅니다.",
        "minutes_late_missing": "지각 상태는 있으나 정확한 지각 분(minutes_late)이 없습니다.",
        "attendance_missing_for_overtime": "초과근무 근거는 있으나 출퇴근 실적이 없습니다.",
        "schedule_missing_for_overtime": "초과근무 근거는 있으나 해당일 스케줄이 없습니다.",
        "overtime_source_mismatch": "SOC 승인 초과근무와 Apple daytime OT 값이 일치하지 않습니다.",
        "multiple_leave_types_same_day": "같은 업무일에 복수 휴가 유형이 중복 기록되었습니다.",
    }
    seen: set[str] = set()
    for code in row_missing_data_flags + row_conflict_flags + row_warnings:
        if code in seen:
            continue
        seen.add(code)
        discrepancies.append(
            _make_discrepancy(
                code,
                severity=severity_map.get(code, "informational_anomaly"),
                scope="employee_day",
                message=message_map.get(code, code),
                business_date=business_date,
                site=site_payload,
                employee=employee_payload,
                trace_refs=trace_refs,
            )
        )
    return discrepancies


def _build_site_day_discrepancies(
    *,
    business_date: date,
    site_payload: dict[str, Any],
    conflict_flags: list[str],
    missing_data_flags: list[str],
    overnight_summary: dict[str, Any],
    support_summary: dict[str, Any],
    event_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    discrepancies: list[dict[str, Any]] = []
    severity_map = {
        "overnight_headcount_mismatch": "hard_error",
        "overnight_record_without_attendance_cross_day": "warning",
        "attendance_cross_day_without_overnight_record": "warning",
        "overnight_support_overlap_ambiguity": "warning",
        "duplicate_overnight_records": "warning",
    }
    message_map = {
        "overnight_headcount_mismatch": "야간 기록 headcount와 출퇴근 cross-day headcount가 다릅니다.",
        "overnight_record_without_attendance_cross_day": "야간 기록은 있으나 cross-day 출퇴근 실적이 없습니다.",
        "attendance_cross_day_without_overnight_record": "cross-day 출퇴근은 있으나 야간 기록이 없습니다.",
        "overnight_support_overlap_ambiguity": "같은 날짜에 야간 기록과 지원 배치가 겹쳐 인력 해석이 모호합니다.",
        "duplicate_overnight_records": "같은 현장/업무일에 복수 야간 기록이 존재합니다.",
    }
    trace_refs = []
    for section in (overnight_summary, support_summary, event_summary):
        trace_refs.extend(section.get("trace_refs") or [])
    seen: set[str] = set()
    for code in missing_data_flags + conflict_flags:
        if code in seen:
            continue
        seen.add(code)
        discrepancies.append(
            _make_discrepancy(
                code,
                severity=severity_map.get(code, "informational_anomaly"),
                scope="site_day",
                message=message_map.get(code, code),
                business_date=business_date,
                site=site_payload,
                trace_refs=trace_refs,
            )
        )
    return discrepancies


def _summarize_discrepancies(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"hard_error": 0, "warning": 0, "informational_anomaly": 0}
    for row in rows:
        for item in row.get("discrepancies", []):
            severity = item.get("severity")
            if severity in counts:
                counts[severity] += 1
    return counts


def build_apple_weekly_truth_contract(
    conn,
    *,
    tenant_row: dict[str, Any],
    week_start: date,
    site_code: str | None = None,
    include_debug: bool = False,
) -> dict[str, Any]:
    started_at = perf_counter()
    tenant_id = _to_text(tenant_row.get("id"))
    tenant_code = _to_upper(tenant_row.get("tenant_code"))
    week_start = normalize_week_start(week_start)
    week_end = week_start + timedelta(days=6)
    range_start_utc, range_end_utc = week_bounds_utc(week_start)
    warnings: list[str] = []

    sites = _fetch_sites(conn, tenant_id, site_code)
    if _to_text(site_code) and not sites:
        raise LookupError("site_not_found")
    rollout_payload, sites, blocked_requested = _build_rollout_payload(
        fetched_sites=sites,
        requested_site_code=site_code,
    )
    if blocked_requested or (rollout_payload["mode"] == "allowlist" and not sites):
        contract = build_apple_weekly_truth_failure_contract(
            tenant_code=tenant_code,
            week_start=week_start,
            site_code=site_code,
            message="Requested site is not onboarded for ARLS Apple Weekly truth rollout.",
            debug_enabled=include_debug,
        )
        contract["contract_state"] = CONFIDENCE_INCOMPLETE
        contract["service_state"] = SERVICE_STATE_SITE_NOT_ONBOARDED
        contract["service_signals"] = [SERVICE_SIGNAL_UNSUPPORTED]
        contract["rollout"] = rollout_payload
        contract["failure_mode"] = {
            "state": SERVICE_STATE_SITE_NOT_ONBOARDED,
            "retryable": False,
            "message": "Requested site is not onboarded for ARLS Apple Weekly truth rollout.",
        }
        contract["observability"]["latency_ms"] = int((perf_counter() - started_at) * 1000)
        contract["observability"]["request_scope"]["tenant_code"] = tenant_code
        logger.warning(
            "apple_weekly_truth_rollout_blocked",
            extra={
                "contract_version": CONTRACT_VERSION,
                "tenant_code": tenant_code,
                "week_start": week_start.isoformat(),
                "site_code": _to_upper(site_code) or None,
                "rollout": rollout_payload,
            },
        )
        return contract
    site_ids = [row["site_id"] for row in sites if row.get("site_id")]

    schedule_rows = _fetch_schedule_rows(conn, tenant_id, week_start, week_end, site_ids)
    attendance_rows = _fetch_attendance_rows(conn, tenant_id, range_start_utc, range_end_utc, site_ids)
    leave_rows = _fetch_leave_rows(conn, tenant_id, week_start, week_end, site_ids)
    late_rows = _fetch_late_rows(conn, tenant_id, week_start, week_end, site_ids)
    soc_overtime_rows = _fetch_soc_overtime_rows(conn, tenant_id, week_start, week_end, site_ids)
    apple_daytime_rows = _fetch_apple_daytime_rows(conn, tenant_id, week_start, week_end, site_ids)
    overnight_rows = _fetch_overnight_rows(conn, tenant_id, week_start, week_end, site_ids)
    support_rows = _fetch_support_rows(conn, tenant_id, week_start, week_end, site_ids)
    event_rows = _fetch_event_rows(conn, tenant_id, week_start, week_end, site_ids)
    source_counts = {
        "sites": len(sites),
        "schedule_rows": len(schedule_rows),
        "attendance_rows": len(attendance_rows),
        "leave_rows": len(leave_rows),
        "late_rows": len(late_rows),
        "soc_overtime_rows": len(soc_overtime_rows),
        "apple_daytime_rows": len(apple_daytime_rows),
        "overnight_rows": len(overnight_rows),
        "support_rows": len(support_rows),
        "event_rows": len(event_rows),
    }

    schedule_index: dict[tuple[str, date], dict[str, Any]] = {}
    employee_payloads: dict[str, dict[str, Any]] = {}
    employee_site_refs: dict[str, dict[str, Any]] = {}
    for row in schedule_rows:
        employee_id = _to_text(row.get("employee_id"))
        business_date = row.get("schedule_date")
        if not employee_id or not isinstance(business_date, date):
            continue
        key = (employee_id, business_date)
        if key not in schedule_index:
            schedule_index[key] = row
        else:
            warnings.append(f"duplicate_schedule:{employee_id}:{business_date.isoformat()}")
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="schedule")

    attendance_index, attendance_warnings = build_attendance_sessions_from_rows(attendance_rows, week_start, week_end)
    warnings.extend(attendance_warnings)
    for row in attendance_rows:
        employee_id = _to_text(row.get("employee_id"))
        if not employee_id:
            continue
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="attendance")

    leave_index = expand_leave_records_by_business_date(leave_rows, week_start, week_end)
    for row in leave_rows:
        employee_id = _to_text(row.get("employee_id"))
        if not employee_id:
            continue
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="leave")

    late_index: dict[tuple[str, date], dict[str, Any]] = {}
    for row in late_rows:
        employee_id = _to_text(row.get("employee_id"))
        business_date = row.get("work_date")
        if not employee_id or not isinstance(business_date, date):
            continue
        if (employee_id, business_date) in late_index:
            warnings.append(f"duplicate_late:{employee_id}:{business_date.isoformat()}")
        late_index[(employee_id, business_date)] = row
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="late")

    soc_overtime_index: dict[tuple[str, date], dict[str, Any]] = {}
    for row in soc_overtime_rows:
        employee_id = _to_text(row.get("employee_id"))
        business_date = row.get("work_date")
        if not employee_id or not isinstance(business_date, date):
            continue
        if (employee_id, business_date) in soc_overtime_index:
            warnings.append(f"duplicate_soc_overtime:{employee_id}:{business_date.isoformat()}")
        soc_overtime_index[(employee_id, business_date)] = row
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="soc_overtime")

    apple_daytime_index: dict[tuple[str, date], dict[str, Any]] = {}
    for row in apple_daytime_rows:
        employee_id = _to_text(row.get("employee_id"))
        business_date = row.get("work_date")
        if not employee_id or not isinstance(business_date, date):
            continue
        if (employee_id, business_date) in apple_daytime_index:
            warnings.append(f"duplicate_apple_daytime_ot:{employee_id}:{business_date.isoformat()}")
        apple_daytime_index[(employee_id, business_date)] = row
        identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
        employee_payloads.setdefault(employee_id, identity)
        warnings.extend(identity_warnings)
        site_payload = build_site_identity_payload(tenant_code, row)
        employee_site_refs.setdefault(employee_id, dict(site_payload))
        _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="apple_daytime_ot")

    overnight_index: dict[tuple[str, date], dict[str, Any]] = {}
    overnight_duplicate_flags: set[tuple[str, date]] = set()
    for row in overnight_rows:
        business_date = row.get("work_date")
        site_id_key = _to_text(row.get("site_id"))
        if not site_id_key or not isinstance(business_date, date):
            continue
        if (site_id_key, business_date) in overnight_index:
            warnings.append(f"duplicate_overnight_records:{site_id_key}:{business_date.isoformat()}")
            overnight_duplicate_flags.add((site_id_key, business_date))
        overnight_index[(site_id_key, business_date)] = row

    support_index: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    support_employee_index: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for row in support_rows:
        business_date = row.get("work_date")
        site_id_key = _to_text(row.get("site_id"))
        if not site_id_key or not isinstance(business_date, date):
            continue
        support_index[(site_id_key, business_date)].append(row)
        employee_id = _to_text(row.get("employee_id"))
        if employee_id:
            support_employee_index[(employee_id, business_date)].append(row)
            identity, identity_warnings = build_employee_identity_payload(tenant_code, row)
            employee_payloads.setdefault(employee_id, identity)
            warnings.extend(identity_warnings)
            site_payload = build_site_identity_payload(tenant_code, row)
            employee_site_refs.setdefault(employee_id, dict(site_payload))
            _merge_employee_site_payload(employee_site_refs[employee_id], site_payload, warnings, source_label="support_assignment")

    event_index: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for row in event_rows:
        business_date = row.get("work_date")
        site_id_key = _to_text(row.get("site_id"))
        if not site_id_key or not isinstance(business_date, date):
            continue
        event_index[(site_id_key, business_date)].append(row)

    relevant_employee_day_keys: set[tuple[str, date]] = set(schedule_index)
    relevant_employee_day_keys.update(attendance_index)
    relevant_employee_day_keys.update(leave_index)
    relevant_employee_day_keys.update(late_index)
    relevant_employee_day_keys.update(soc_overtime_index)
    relevant_employee_day_keys.update(apple_daytime_index)
    relevant_employee_day_keys.update(support_employee_index)

    employee_day_rows: list[dict[str, Any]] = []
    site_day_buckets: dict[tuple[str, date], dict[str, Any]] = {}
    for site in sites:
        site_payload = build_site_identity_payload(tenant_code, site)
        for business_date in week_dates(week_start):
            site_day_buckets[(site_payload["site_id"], business_date)] = {
                "site": site_payload,
                "business_date": _iso_date_key(business_date),
                "scheduled_shift_summary": {
                    "scheduled_employee_count": 0,
                    "scheduled_shift_type_counts": defaultdict(int),
                },
                "attendance_summary": {
                    "present_count": 0,
                    "missing_check_out_count": 0,
                    "orphan_check_out_count": 0,
                    "absent_count": 0,
                    "leave_count": 0,
                    "attendance_without_schedule_count": 0,
                    "scheduled_without_attendance_count": 0,
                },
                "late_tardy_summary": {"late_count": 0, "late_minutes_total": 0, "late_without_minutes_count": 0},
                "overtime_summary": {
                    "entry_count": 0,
                    "soc_approved_minutes_total": 0,
                    "soc_overtime_units_total": 0.0,
                    "apple_daytime_ot_hours_total": 0.0,
                    "attendance_extension_minutes_total": 0,
                },
                "overnight_summary": build_site_overnight_summary(None, business_date=business_date, attendance_cross_day_count=0),
                "support_assignment_summary": build_support_assignment_summary([]),
                "event_additional_note_summary": build_event_additional_note_summary([]),
                "missing_data_flags": [],
                "conflict_flags": [],
                "warnings": [],
                "discrepancies": [],
            }

    site_day_attendance_overnight_counts: dict[tuple[str, date], int] = defaultdict(int)
    sorted_keys = sorted(relevant_employee_day_keys, key=lambda item: (_to_upper(employee_payloads.get(item[0], {}).get("employee_code") or item[0]), item[1]))
    for employee_id, business_date in sorted_keys:
        schedule_row = schedule_index.get((employee_id, business_date))
        attendance_row = attendance_index.get((employee_id, business_date))
        leave_rows_for_day = leave_index.get((employee_id, business_date), [])
        late_row = late_index.get((employee_id, business_date))
        soc_ot_row = soc_overtime_index.get((employee_id, business_date))
        apple_ot_row = apple_daytime_index.get((employee_id, business_date))
        support_rows_for_employee = support_employee_index.get((employee_id, business_date), [])
        identity_source_row = (
            employee_payloads.get(employee_id)
            or schedule_row
            or attendance_row
            or (leave_rows_for_day[0] if leave_rows_for_day else None)
            or late_row
            or soc_ot_row
            or apple_ot_row
            or (support_rows_for_employee[0] if support_rows_for_employee else None)
        )
        site_payload = employee_site_refs.get(employee_id) or build_site_identity_payload(tenant_code, identity_source_row)
        employee_payload, identity_warnings = build_employee_identity_payload(tenant_code, identity_source_row)
        warnings.extend(identity_warnings)
        shift_type = _to_text((schedule_row or {}).get("shift_type"))
        shift_type_lower = shift_type.lower()
        schedule_status = "unscheduled"
        if schedule_row:
            if shift_type_lower in {"off", "holiday"}:
                schedule_status = shift_type_lower
            else:
                schedule_status = "scheduled"
        attendance_status = "none"
        if attendance_row:
            attendance_status = _to_text(attendance_row.get("status")).lower() or "present"
        elif leave_rows_for_day:
            attendance_status = "leave"
        elif schedule_status == "scheduled":
            attendance_status = "absent"

        row_warnings: list[str] = []
        row_missing_data_flags: list[str] = []
        row_conflict_flags: list[str] = []
        if attendance_row and site_payload.get("site_code") and attendance_row.get("site_code") and _to_upper(attendance_row.get("site_code")) != _to_upper(site_payload.get("site_code")):
            row_warnings.append("attendance_site_mismatch")
            row_conflict_flags.append("attendance_site_mismatch")
        if schedule_status == "scheduled" and not attendance_row and not leave_rows_for_day:
            row_missing_data_flags.append("attendance_missing_for_scheduled_shift")
        if attendance_row and not schedule_row:
            row_missing_data_flags.append("schedule_missing_for_attendance")
        if leave_rows_for_day and attendance_row:
            row_conflict_flags.append("leave_attendance_overlap")
        if leave_rows_for_day and late_row:
            row_conflict_flags.append("late_leave_overlap")
        if support_rows_for_employee and any(_to_text(row.get("site_id")) and _to_text(row.get("site_id")) != _to_text(site_payload.get("site_id")) for row in support_rows_for_employee):
            row_conflict_flags.append("support_assignment_site_mismatch")
        overnight_row = overnight_index.get((_to_text(site_payload.get("site_id")), business_date))
        leave_summary = build_leave_summary(leave_rows_for_day, schedule_row=schedule_row, attendance_row=attendance_row)
        late_summary = build_late_summary(late_row)
        overtime_summary = build_overtime_summary(
            soc_ot_row,
            apple_ot_row,
            attendance_row=attendance_row,
            schedule_row=schedule_row,
        )
        overnight_summary = build_employee_overnight_summary(attendance_row, overnight_row)
        if overnight_summary.get("has_overnight"):
            site_day_attendance_overnight_counts[(_to_text(site_payload.get("site_id")), business_date)] += 1
        support_summary = build_support_assignment_summary(support_rows_for_employee, employee_id=employee_id)
        row_missing_data_flags.extend(leave_summary.get("missing_data_flags", []))
        row_missing_data_flags.extend(late_summary.get("missing_data_flags", []))
        row_missing_data_flags.extend(overtime_summary.get("missing_data_flags", []))
        row_conflict_flags.extend(leave_summary.get("conflict_flags", []))
        row_conflict_flags.extend(late_summary.get("conflict_flags", []))
        row_conflict_flags.extend(overtime_summary.get("conflict_flags", []))
        row_conflict_flags.extend(support_summary.get("conflict_flags", []))
        row_discrepancies = _build_row_discrepancies(
            business_date=business_date,
            site_payload=site_payload,
            employee_payload=employee_payload,
            row_missing_data_flags=row_missing_data_flags,
            row_conflict_flags=row_conflict_flags,
            row_warnings=row_warnings,
            attendance_row=attendance_row,
            schedule_row=schedule_row,
            leave_summary=leave_summary,
            late_summary=late_summary,
            overtime_summary=overtime_summary,
            overnight_summary=overnight_summary,
            support_summary=support_summary,
        )
        scheduled_shift_summary = _finalize_truth_section(
            {
                "supported": True,
                "status": schedule_status,
                "shift_type": shift_type or None,
                "source": _to_text((schedule_row or {}).get("source")) or None,
                "source_ticket_id": (schedule_row or {}).get("source_ticket_id"),
                "schedule_note": _to_text((schedule_row or {}).get("schedule_note")) or None,
                "leader_user_id": _to_text((schedule_row or {}).get("leader_user_id")) or None,
                "trace_refs": (
                    [
                        _base_trace_ref(
                            "monthly_schedules",
                            row_id=(schedule_row or {}).get("schedule_id"),
                            employee_id=(schedule_row or {}).get("employee_id"),
                            site_id=(schedule_row or {}).get("site_id"),
                            schedule_date=(schedule_row or {}).get("schedule_date"),
                            source_ticket_id=(schedule_row or {}).get("source_ticket_id"),
                        )
                    ]
                    if schedule_row
                    else []
                ),
                "missing_data_flags": [],
                "conflict_flags": [],
            },
            has_data=schedule_row is not None,
        )
        attendance_summary = _finalize_truth_section(
            {
                "supported": True,
                "status": attendance_status,
                "check_in_at": _to_iso_datetime((attendance_row or {}).get("check_in_at")),
                "check_out_at": _to_iso_datetime((attendance_row or {}).get("check_out_at")),
                "worked_minutes": (attendance_row or {}).get("worked_minutes"),
                "auto_checkout": bool((attendance_row or {}).get("auto_checkout")),
                "trace_refs": (
                    [
                        _base_trace_ref(
                            "attendance_records",
                            employee_id=(attendance_row or {}).get("employee_id"),
                            site_id=(attendance_row or {}).get("site_id"),
                            business_date=(attendance_row or {}).get("business_date"),
                            check_in_at=(attendance_row or {}).get("check_in_at"),
                            check_out_at=(attendance_row or {}).get("check_out_at"),
                        )
                    ]
                    if attendance_row
                    else []
                ),
                "missing_data_flags": ["attendance_missing_for_scheduled_shift"] if schedule_status == "scheduled" and not attendance_row and not leave_rows_for_day else [],
                "conflict_flags": ["attendance_site_mismatch"] if "attendance_site_mismatch" in row_conflict_flags else [],
            },
            has_data=attendance_row is not None or attendance_status in {"absent", "leave"},
        )
        row_payload = {
            "site": site_payload,
            "employee": employee_payload,
            "business_date": _iso_date_key(business_date),
            "scheduled_shift_summary": scheduled_shift_summary,
            "attendance_summary": attendance_summary,
            "leave_summary": leave_summary,
            "late_tardy_summary": late_summary,
            "overtime_summary": overtime_summary,
            "overnight_summary": overnight_summary,
            "support_assignment_summary": support_summary,
            "event_additional_note_summary": build_unsupported_summary("event_additional_note_summary", reason="SITE_DAY_ONLY"),
            "missing_data_flags": sorted(set(row_missing_data_flags)),
            "conflict_flags": sorted(set(row_conflict_flags)),
            "warnings": row_warnings,
            "discrepancies": row_discrepancies,
            "confidence_state": _compute_confidence_state(discrepancies=row_discrepancies),
            "traceability": {
                "site_key": site_payload.get("canonical_site_key"),
                "employee_key": employee_payload.get("canonical_employee_key"),
                "source_refs": {
                    "schedule": scheduled_shift_summary.get("trace_refs", []),
                    "attendance": attendance_summary.get("trace_refs", []),
                    "leave": leave_summary.get("trace_refs", []),
                    "late": late_summary.get("trace_refs", []),
                    "overtime": overtime_summary.get("trace_refs", []),
                    "overnight": overnight_summary.get("trace_refs", []),
                    "support_assignment": support_summary.get("trace_refs", []),
                },
            },
        }
        employee_day_rows.append(row_payload)

        bucket = site_day_buckets.get((site_payload.get("site_id"), business_date))
        if not bucket:
            continue
        if schedule_row:
            if schedule_status == "scheduled":
                bucket["scheduled_shift_summary"]["scheduled_employee_count"] += 1
            bucket["scheduled_shift_summary"]["scheduled_shift_type_counts"][shift_type_lower or "unscheduled"] += 1
        if attendance_status == "present":
            bucket["attendance_summary"]["present_count"] += 1
        elif attendance_status == "absent":
            bucket["attendance_summary"]["absent_count"] += 1
        elif attendance_status == "leave":
            bucket["attendance_summary"]["leave_count"] += 1
        elif attendance_status == "orphan_check_out":
            bucket["attendance_summary"]["orphan_check_out_count"] += 1
        if attendance_row and not schedule_row:
            bucket["attendance_summary"]["attendance_without_schedule_count"] += 1
        if schedule_status == "scheduled" and not attendance_row and not leave_rows_for_day:
            bucket["attendance_summary"]["scheduled_without_attendance_count"] += 1
        if attendance_status in {"present", "missing_check_out"} and not (attendance_row or {}).get("check_out_at"):
            bucket["attendance_summary"]["missing_check_out_count"] += 1
        if late_row:
            bucket["late_tardy_summary"]["late_count"] += 1
            if late_row.get("minutes_late") is None:
                bucket["late_tardy_summary"]["late_without_minutes_count"] += 1
            else:
                bucket["late_tardy_summary"]["late_minutes_total"] += _safe_int(late_row.get("minutes_late"))
        if soc_ot_row:
            bucket["overtime_summary"]["entry_count"] += 1
            bucket["overtime_summary"]["soc_approved_minutes_total"] += int(soc_ot_row.get("approved_minutes") or 0)
            bucket["overtime_summary"]["soc_overtime_units_total"] += float(soc_ot_row.get("overtime_units") or 0)
        if apple_ot_row:
            if not soc_ot_row:
                bucket["overtime_summary"]["entry_count"] += 1
            bucket["overtime_summary"]["apple_daytime_ot_hours_total"] += float(apple_ot_row.get("hours") or 0)
        bucket["overtime_summary"]["attendance_extension_minutes_total"] += _safe_int(overtime_summary.get("attendance_extension_minutes"))
        bucket["warnings"].extend(row_warnings)
        bucket["missing_data_flags"].extend(row_payload["missing_data_flags"])
        bucket["conflict_flags"].extend(row_payload["conflict_flags"])
        bucket["discrepancies"].extend(row_discrepancies)

    for (site_id_key, business_date), rows in support_index.items():
        bucket = site_day_buckets.get((site_id_key, business_date))
        if not bucket:
            continue
        bucket["support_assignment_summary"] = build_support_assignment_summary(rows)
    for (site_id_key, business_date), rows in event_index.items():
        bucket = site_day_buckets.get((site_id_key, business_date))
        if not bucket:
            continue
        bucket["event_additional_note_summary"] = build_event_additional_note_summary(rows)

    for (site_id_key, business_date), bucket in site_day_buckets.items():
        overnight_row = overnight_index.get((site_id_key, business_date))
        bucket["overnight_summary"] = build_site_overnight_summary(
            overnight_row,
            business_date=business_date,
            attendance_cross_day_count=site_day_attendance_overnight_counts.get((site_id_key, business_date), 0),
        )
        bucket["conflict_flags"].extend(bucket["overnight_summary"].get("conflict_flags", []))
        if (site_id_key, business_date) in overnight_duplicate_flags:
            bucket["conflict_flags"].append("duplicate_overnight_records")
        if bucket["overnight_summary"].get("has_overnight") and bucket["support_assignment_summary"].get("count"):
            bucket["conflict_flags"].append("overnight_support_overlap_ambiguity")
        bucket["discrepancies"] = _build_site_day_discrepancies(
            business_date=business_date,
            site_payload=bucket["site"],
            conflict_flags=bucket["conflict_flags"],
            missing_data_flags=bucket["missing_data_flags"],
            overnight_summary=bucket["overnight_summary"],
            support_summary=bucket["support_assignment_summary"],
            event_summary=bucket["event_additional_note_summary"],
        )

    site_day_summaries: list[dict[str, Any]] = []
    for site in sites:
        site_payload = build_site_identity_payload(tenant_code, site)
        for business_date in week_dates(week_start):
            bucket = site_day_buckets[(site_payload["site_id"], business_date)]
            bucket["scheduled_shift_summary"]["scheduled_shift_type_counts"] = dict(sorted(bucket["scheduled_shift_summary"]["scheduled_shift_type_counts"].items()))
            bucket["missing_data_flags"] = sorted(set(bucket["missing_data_flags"]))
            bucket["conflict_flags"] = sorted(set(bucket["conflict_flags"]))
            bucket["warnings"] = sorted(set(bucket["warnings"]))
            bucket["scheduled_shift_summary"] = _finalize_truth_section(
                {
                    **bucket["scheduled_shift_summary"],
                    "supported": True,
                    "missing_data_flags": [],
                    "conflict_flags": [],
                    "trace_refs": [],
                },
                has_data=bool(bucket["scheduled_shift_summary"]["scheduled_employee_count"]),
            )
            bucket["attendance_summary"] = _finalize_truth_section(
                {
                    **bucket["attendance_summary"],
                    "supported": True,
                    "missing_data_flags": [
                        "scheduled_without_attendance_present"
                    ]
                    if bucket["attendance_summary"]["scheduled_without_attendance_count"]
                    else [],
                    "conflict_flags": [],
                    "trace_refs": [],
                },
                has_data=bool(
                    bucket["attendance_summary"]["present_count"]
                    or bucket["attendance_summary"]["absent_count"]
                    or bucket["attendance_summary"]["leave_count"]
                    or bucket["attendance_summary"]["attendance_without_schedule_count"]
                ),
            )
            bucket["late_tardy_summary"] = _finalize_truth_section(
                {
                    **bucket["late_tardy_summary"],
                    "supported": True,
                    "missing_data_flags": ["late_minutes_missing"] if bucket["late_tardy_summary"]["late_without_minutes_count"] else [],
                    "conflict_flags": [],
                    "trace_refs": [],
                },
                has_data=bool(bucket["late_tardy_summary"]["late_count"]),
            )
            bucket["overtime_summary"] = _finalize_truth_section(
                {
                    **bucket["overtime_summary"],
                    "supported": True,
                    "missing_data_flags": [],
                    "conflict_flags": [],
                    "trace_refs": [],
                },
                has_data=bool(bucket["overtime_summary"]["entry_count"]),
            )
            bucket["confidence_state"] = _compute_confidence_state(discrepancies=bucket["discrepancies"])
            bucket["traceability"] = {
                "site_key": bucket["site"].get("canonical_site_key"),
                "source_refs": {
                    "overnight": bucket["overnight_summary"].get("trace_refs", []),
                    "support_assignment": bucket["support_assignment_summary"].get("trace_refs", []),
                    "event_additional": bucket["event_additional_note_summary"].get("trace_refs", []),
                },
            }
            site_day_summaries.append(bucket)

    unsupported_fields = {
        "overtime_summary.normal_scheduled_minutes": {
            "supported": False,
            "status": UNSUPPORTED_PHASE4,
            "reason": "ARLS does not own Sentrix baseline scheduled-minute policy. The contract exposes operational overtime truth only.",
        },
        "overtime_summary.net_extension_minutes_vs_baseline": {
            "supported": False,
            "status": UNSUPPORTED_PHASE4,
            "reason": "Net overtime versus Sentrix baseline is intentionally left to Sentrix. ARLS exposes attendance, schedule presence, and approved overtime inputs separately.",
        },
        "employee_day_rows.event_additional_note_summary": {
            "supported": False,
            "status": "SITE_DAY_ONLY",
            "reason": "Event and additional note truth is normalized at site/day scope, not employee/day scope.",
        },
    }

    top_level_discrepancy_summary = {
        "employee_day": _summarize_discrepancies(employee_day_rows),
        "site_day": _summarize_discrepancies(site_day_summaries),
    }
    all_discrepancies = [
        *[item for row in employee_day_rows for item in row.get("discrepancies", [])],
        *[item for row in site_day_summaries for item in row.get("discrepancies", [])],
    ]
    has_supported_missing = any(
        section.get("section_state") == SECTION_STATE_SUPPORTED_MISSING
        for row in employee_day_rows + site_day_summaries
        for section in (
            row.get("scheduled_shift_summary"),
            row.get("attendance_summary"),
            row.get("leave_summary"),
            row.get("late_tardy_summary"),
            row.get("overtime_summary"),
            row.get("overnight_summary"),
            row.get("support_assignment_summary"),
            row.get("event_additional_note_summary"),
        )
        if isinstance(section, dict)
    )
    contract_state = _compute_confidence_state(
        discrepancies=all_discrepancies,
        unsupported_section_present=False,
    )
    if contract_state == CONFIDENCE_READY and has_supported_missing:
        contract_state = CONFIDENCE_INCOMPLETE
    latency_ms = int((perf_counter() - started_at) * 1000)
    service_state, service_signals, service_metrics = _derive_service_status(
        contract_state=contract_state,
        rollout_payload=rollout_payload,
        warnings=sorted(set(warnings)),
        unsupported_fields=unsupported_fields,
        discrepancy_summary=top_level_discrepancy_summary,
        discrepancies=all_discrepancies,
        latency_ms=latency_ms,
    )
    contract = {
        "contract_version": CONTRACT_VERSION,
        "tenant": {
            "tenant_id": tenant_id,
            "tenant_code": tenant_code,
            "tenant_name": _to_text(tenant_row.get("tenant_name")) or None,
        },
        "scope": {
            "week_start": _iso_date_key(week_start),
            "week_end": _iso_date_key(week_end),
            "site_code": _to_upper(site_code) or None,
            "site_count": len(sites),
        },
        "identity_rules": {
            "canonical_site_key": "tenant_code:site_code (fallback tenant_code:site_id)",
            "canonical_employee_key": "employee_uuid (fallback tenant_code:employee_code, then tenant_code:employee_id)",
            "site_display_keys": ["site_code", "site_name", "company_code", "company_name"],
            "employee_identity_keys": ["employee_uuid", "employee_code", "external_employee_key", "linked_employee_id"],
        },
        "business_date_rules": {
            "week_scope": "week_start is normalized to Monday in KST; week_end is week_start + 6 days.",
            "schedule": "monthly_schedules.schedule_date is the business date.",
            "attendance": "business date is the KST date of check_in. Overnight check_out remains attached to the originating check_in date. A checkout without a prior open check_in is attributed to its own KST date as orphan_check_out.",
            "leave": "approved leave_requests are expanded date-by-date from start_at to end_at inclusive. Half-day slot is preserved and reported as partial leave on that business date.",
            "late_tardy": "late_shift_log.work_date is the business date. Exact minutes_late are preserved whenever present.",
            "overtime": "soc_overtime_approvals.work_date and apple_daytime_ot.work_date are exposed under one overtime summary with attendance-derived extension minutes. Sentrix baseline policy minutes are not computed inside ARLS.",
            "overnight": "employee overnight attendance is attributed to the originating check_in business date. site-level overnight truth uses apple_report_overnight_records.work_date and is reconciled against cross-day attendance counts.",
            "support_assignment": "support_assignment.work_date is the business date for site/day staffing support rows.",
            "event_additional": "daily_event_log.work_date is the business date for EVENT and ADDITIONAL notes.",
        },
        "unsupported_fields": unsupported_fields,
        "domain_capabilities": _build_domain_capabilities(),
        "contract_state": contract_state,
        "service_state": service_state,
        "service_signals": service_signals,
        "discrepancy_summary": top_level_discrepancy_summary,
        "employee_day_rows": employee_day_rows,
        "site_day_summaries": site_day_summaries,
        "warnings": sorted(set(warnings)),
        "rollout": rollout_payload,
        "failure_mode": {
            "state": None,
            "retryable": False,
            "message": None,
        },
        "observability": {
            "contract_version": CONTRACT_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "request_scope": {
                "tenant_code": tenant_code,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "site_code": _to_upper(site_code) or None,
                "site_count": len(sites),
            },
            "source_coverage": source_counts,
            "discrepancy_counts": top_level_discrepancy_summary,
            "unsupported_fields": sorted(unsupported_fields.keys()),
            **service_metrics,
        },
        "legacy_sheet_paths": {
            "isolated": True,
            "paths": [
                "/api/v1/integrations/google-sheets/profiles",
                "/api/v1/integrations/google-sheets/profiles/{profile_id}/sync",
                "/api/v1/integrations/google-sheets/support-assignments/webhook",
            ],
            "note": "These legacy ARLS Google Sheets paths remain separate from the Apple Weekly truth contract and are not called by this endpoint.",
        },
    }
    if include_debug:
        contract["debug"] = {
            "source_counts": source_counts,
            "site_codes": [_to_upper(row.get("site_code")) for row in sites],
            "discrepancy_summary": top_level_discrepancy_summary,
            "rollout": rollout_payload,
        }
    logger.info(
        "apple_weekly_truth_built",
        extra={
            "contract_version": CONTRACT_VERSION,
            "tenant_code": tenant_code,
            "week_start": week_start.isoformat(),
            "site_code": _to_upper(site_code) or None,
            "source_counts": source_counts,
            "employee_day_rows": len(employee_day_rows),
            "site_day_summaries": len(site_day_summaries),
            "discrepancy_summary": top_level_discrepancy_summary,
            "unsupported_fields": sorted(unsupported_fields.keys()),
            "warnings_count": len(contract["warnings"]),
            "service_state": service_state,
            "service_signals": service_signals,
            "rollout": rollout_payload,
            "latency_ms": latency_ms,
        },
    )
    if service_state in {SERVICE_STATE_WARNING, SERVICE_STATE_INCOMPLETE, SERVICE_STATE_CONFLICT}:
        logger.warning(
            "apple_weekly_truth_attention",
            extra={
                "contract_version": CONTRACT_VERSION,
                "tenant_code": tenant_code,
                "week_start": week_start.isoformat(),
                "site_code": _to_upper(site_code) or None,
                "service_state": service_state,
                "discrepancy_summary": top_level_discrepancy_summary,
                "observability": contract["observability"],
            },
        )
    if latency_ms >= settings.apple_weekly_truth_slow_ms:
        logger.warning(
            "apple_weekly_truth_slow",
            extra={
                "contract_version": CONTRACT_VERSION,
                "tenant_code": tenant_code,
                "week_start": week_start.isoformat(),
                "site_code": _to_upper(site_code) or None,
                "latency_ms": latency_ms,
            },
        )
    return contract
