from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...integration_center.feature_flags import (
    APPLE_REPORT_DAYTIME_ENABLED,
    APPLE_REPORT_OT_ENABLED,
    APPLE_REPORT_OVERNIGHT_ENABLED,
    APPLE_REPORT_TOTAL_LATE_ENABLED,
    SHEETS_SYNC_ENABLED,
    FeatureFlagService,
    build_feature_flag_defaults,
)
from ...utils.permissions import normalize_role
from . import integrations as integrations_router

router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(apply_rate_limit)])

APPLE_TENANT_CODE = "APPLE"
APPLE_PROFILE_SCOPES = {
    integrations_router.PROFILE_SCOPE_APPLE_OVERNIGHT,
    integrations_router.PROFILE_SCOPE_APPLE_DAYTIME,
    integrations_router.PROFILE_SCOPE_APPLE_OT,
    integrations_router.PROFILE_SCOPE_APPLE_TOTAL_LATE,
}
FEATURE_FLAG_DEFAULTS = build_feature_flag_defaults(settings)


def _resolve_target_tenant(conn, user: dict, tenant_code: str | None):
    actor_role = normalize_role(user.get("role"))
    own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    requested_tenant_code = str(tenant_code or "").strip().upper()

    if actor_role != "dev":
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "FORBIDDEN", "message": "다른 테넌트 조회 권한이 없습니다."},
            )
        requested_tenant_code = own_tenant_code
    elif not requested_tenant_code:
        requested_tenant_code = own_tenant_code

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code, tenant_name
            FROM tenants
            WHERE tenant_code = %s
              AND COALESCE(is_active, TRUE) = TRUE
            LIMIT 1
            """,
            (requested_tenant_code,),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )
    return row


def _is_apple_tenant(tenant_row: dict[str, Any]) -> bool:
    tenant_code = str(tenant_row.get("tenant_code") or "").strip().upper()
    return tenant_code == APPLE_TENANT_CODE


def _assert_apple_tenant(tenant_row: dict[str, Any]) -> None:
    if not _is_apple_tenant(tenant_row):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "FORBIDDEN",
                "message": "이 테넌트에 해당 보고서가 없습니다.",
            },
        )


def _normalize_month_key(month: str | None) -> str:
    value = str(month or "").strip()
    if not value:
        return datetime.now(timezone.utc).strftime("%Y-%m")
    try:
        parsed = date.fromisoformat(f"{value}-01")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "INVALID_MONTH", "message": "month 형식은 YYYY-MM 이어야 합니다."},
        ) from exc
    return parsed.strftime("%Y-%m")


def _month_bounds(month_key: str) -> tuple[date, date]:
    start_date = date.fromisoformat(f"{month_key}-01")
    next_month = (start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start_date, next_month


def _safe_fetchone(cur, query: str, params: tuple[Any, ...], default: dict[str, Any]) -> dict[str, Any]:
    savepoint = "sp_reports_safe_fetch"
    cur.execute(f"SAVEPOINT {savepoint}")
    try:
        cur.execute(query, params)
        row = cur.fetchone() or dict(default)
        cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        return row
    except pg_errors.UndefinedTable:
        cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        return dict(default)


def _scope_from_profile_row(row: dict[str, Any]) -> str:
    options = row.get("options_json") if isinstance(row.get("options_json"), dict) else {}
    raw = str(options.get("profile_scope") or "").strip()
    if not raw:
        return integrations_router.PROFILE_SCOPE_PAYROLL_LEAVE_OVERTIME
    return integrations_router._normalize_profile_scope(raw)


def _collect_apple_profiles(conn, tenant_id) -> list[dict[str, Any]]:
    profiles = integrations_router._fetch_active_google_profiles(conn, tenant_id)
    return [profile for profile in profiles if _scope_from_profile_row(profile) in APPLE_PROFILE_SCOPES]


def _build_default_pack() -> dict[str, Any]:
    return {
        "key": "DEFAULT_REPORT_PACK",
        "title": "기본 리포트",
        "description": "내부 월표/근태 기본 리포트",
        "route": "/reports?pack=default",
        "type": "default",
        "enabled": True,
        "reports": [
            {"code": "timesheet", "title": "내부 월표"},
            {"code": "duty_log", "title": "근무상황기록부"},
        ],
    }


def _build_apple_pack() -> dict[str, Any]:
    return {
        "key": "APPLE_REPORT_PACK",
        "title": "Apple 보고",
        "description": "월별 Apple 보고 자동화/동기화",
        "route": "/reports/apple",
        "type": "apple",
        "enabled": True,
        "reports": [
            {"code": "daytime", "title": "Daytime"},
            {"code": "overtime", "title": "Overtime"},
            {"code": "overnight", "title": "Overnight"},
            {"code": "late_event", "title": "Late/Event/Additional"},
        ],
    }


@router.get("/packs")
def list_report_packs(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)

    packs = [_build_default_pack()]
    if _is_apple_tenant(tenant):
        packs.insert(0, _build_apple_pack())

    return {
        "tenant_code": str(tenant.get("tenant_code") or "").strip().upper(),
        "packs": packs,
    }


@router.get("/apple")
def get_apple_report_status_default_month(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    return get_apple_report_status(month=month, tenant_code=tenant_code, conn=conn, user=user)


@router.get("/apple/status")
def get_apple_report_status(
    month: str | None = Query(default=None, max_length=7),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    _assert_apple_tenant(tenant)

    month_key = _normalize_month_key(month)
    start_date, next_month = _month_bounds(month_key)
    tenant_id = tenant["id"]
    tenant_code_text = str(tenant.get("tenant_code") or "").strip().upper()

    flag_service = FeatureFlagService(conn, FEATURE_FLAG_DEFAULTS)
    flag_overview = {
        "sheets_sync_enabled": flag_service.is_enabled(tenant_id, SHEETS_SYNC_ENABLED),
        "apple_report_daytime_enabled": flag_service.is_enabled(tenant_id, APPLE_REPORT_DAYTIME_ENABLED),
        "apple_report_ot_enabled": flag_service.is_enabled(tenant_id, APPLE_REPORT_OT_ENABLED),
        "apple_report_overnight_enabled": flag_service.is_enabled(tenant_id, APPLE_REPORT_OVERNIGHT_ENABLED),
        "apple_report_total_late_enabled": flag_service.is_enabled(tenant_id, APPLE_REPORT_TOTAL_LATE_ENABLED),
    }

    with conn.cursor() as cur:
        overnight_row = _safe_fetchone(
            cur,
            """
            SELECT COUNT(*) AS overnight_count,
                   COALESCE(MAX(updated_at), MAX(created_at)) AS overnight_last_at
            FROM apple_report_overnight_records
            WHERE tenant_id = %s
              AND work_date >= %s
              AND work_date < %s
            """,
            (tenant_id, start_date, next_month),
            {"overnight_count": 0, "overnight_last_at": None},
        )

        ot_row = _safe_fetchone(
            cur,
            """
            SELECT COUNT(*) FILTER (WHERE status = 'APPROVED') AS approved_count,
                   COUNT(*) FILTER (WHERE status = 'PENDING_REASON') AS pending_reason_count,
                   COALESCE(MAX(updated_at), MAX(created_at)) AS ot_last_at
            FROM apple_daytime_ot
            WHERE tenant_id = %s
              AND work_date >= %s
              AND work_date < %s
            """,
            (tenant_id, start_date, next_month),
            {"approved_count": 0, "pending_reason_count": 0, "ot_last_at": None},
        )

        late_row = _safe_fetchone(
            cur,
            """
            SELECT COUNT(*) AS late_count,
                   MAX(created_at) AS late_last_at
            FROM apple_late_shift
            WHERE tenant_id = %s
              AND work_date >= %s
              AND work_date < %s
            """,
            (tenant_id, start_date, next_month),
            {"late_count": 0, "late_last_at": None},
        )

        event_row = _safe_fetchone(
            cur,
            """
            SELECT COUNT(*) FILTER (WHERE type = 'EVENT') AS event_count,
                   COUNT(*) FILTER (WHERE type = 'ADDITIONAL') AS additional_count,
                   MAX(created_at) AS event_last_at
            FROM daily_event_log
            WHERE tenant_id = %s
              AND work_date >= %s
              AND work_date < %s
            """,
            (tenant_id, start_date, next_month),
            {"event_count": 0, "additional_count": 0, "event_last_at": None},
        )

        latest_soc = _safe_fetchone(
            cur,
            """
            SELECT se.status, se.event_type, se.received_at, se.error_text
            FROM soc_event_ingests se
            WHERE se.tenant_id = %s
            ORDER BY se.received_at DESC
            LIMIT 1
            """,
            (tenant_id,),
            {},
        )

    apple_profiles = _collect_apple_profiles(conn, tenant_id)
    apple_profile_ids = [str(row.get("id")) for row in apple_profiles if row.get("id")]
    scope_counter = {
        "APPLE_OVERNIGHT": 0,
        "APPLE_DAYTIME": 0,
        "APPLE_OT": 0,
        "APPLE_TOTAL_LATE": 0,
    }
    for profile in apple_profiles:
        scope = _scope_from_profile_row(profile)
        if scope in scope_counter:
            scope_counter[scope] += 1

    latest_sheet = None
    if apple_profile_ids:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ssl.status, ssl.created_at, ssl.error_message, gp.profile_name, gp.options_json
                FROM sheets_sync_log ssl
                LEFT JOIN google_sheet_profiles gp ON gp.id = ssl.profile_id
                WHERE ssl.tenant_id = %s
                  AND ssl.profile_id = ANY(%s::uuid[])
                ORDER BY ssl.created_at DESC
                LIMIT 1
                """,
                (tenant_id, apple_profile_ids),
            )
            latest_sheet = cur.fetchone()

    overnight_count = int(overnight_row.get("overnight_count") or 0)
    approved_ot_count = int(ot_row.get("approved_count") or 0)
    pending_reason_count = int(ot_row.get("pending_reason_count") or 0)
    late_count = int(late_row.get("late_count") or 0)
    event_count = int(event_row.get("event_count") or 0)
    additional_count = int(event_row.get("additional_count") or 0)

    sheets_status = "PENDING"
    sheets_last_at = latest_sheet.get("created_at") if latest_sheet else None
    sheets_error = str(latest_sheet.get("error_message") or "").strip() if latest_sheet else ""
    if not flag_overview["sheets_sync_enabled"]:
        sheets_status = "OFF"
    elif latest_sheet:
        sheets_status = str(latest_sheet.get("status") or "PENDING").strip().upper() or "PENDING"

    daytime_status = "OFF" if not flag_overview["apple_report_daytime_enabled"] else (
        "SUCCESS" if scope_counter["APPLE_DAYTIME"] > 0 and sheets_status == "SUCCESS" else "PENDING"
    )
    overtime_status = "OFF" if not flag_overview["apple_report_ot_enabled"] else (
        "SUCCESS" if approved_ot_count > 0 else ("PENDING" if pending_reason_count > 0 else "PENDING")
    )
    overnight_status = "OFF" if not flag_overview["apple_report_overnight_enabled"] else (
        "SUCCESS" if overnight_count > 0 else "PENDING"
    )
    late_event_status = "OFF" if not flag_overview["apple_report_total_late_enabled"] else (
        "SUCCESS" if (late_count + event_count + additional_count) > 0 else "PENDING"
    )

    latest_soc_status = str(latest_soc.get("status") or "PENDING").strip().upper() if latest_soc else "PENDING"
    latest_soc_at = latest_soc.get("received_at") if latest_soc else None
    latest_soc_error = str(latest_soc.get("error_text") or "").strip() if latest_soc else ""

    return {
        "tenant_code": tenant_code_text,
        "month": month_key,
        "flags": flag_overview,
        "profile_counts": scope_counter,
        "status": {
            "daytime": {"status": daytime_status, "last_at": sheets_last_at},
            "overtime": {"status": overtime_status, "last_at": ot_row.get("ot_last_at")},
            "overnight": {"status": overnight_status, "last_at": overnight_row.get("overnight_last_at")},
            "late_event_additional": {
                "status": late_event_status,
                "last_at": max(
                    [value for value in [late_row.get("late_last_at"), event_row.get("event_last_at")] if value is not None],
                    default=None,
                ),
            },
            "sheets": {
                "status": sheets_status,
                "last_at": sheets_last_at,
                "error": sheets_error,
            },
            "soc": {
                "status": latest_soc_status,
                "last_at": latest_soc_at,
                "error": latest_soc_error,
            },
        },
        "metrics": {
            "apple_profile_count": len(apple_profiles),
            "apple_profile_ids": apple_profile_ids,
            "overnight_rows": overnight_count,
            "approved_ot_rows": approved_ot_count,
            "pending_ot_reason_rows": pending_reason_count,
            "late_rows": late_count,
            "event_rows": event_count,
            "additional_rows": additional_count,
        },
    }


@router.post("/apple/run")
def run_apple_report_pack(
    month: str | None = Query(default=None, max_length=7),
    tenant_code: str | None = Query(default=None, max_length=64),
    site_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user.get("role"))
    if actor_role not in {"dev", "branch_manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "Apple 보고 실행 권한이 없습니다."},
        )

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    _assert_apple_tenant(tenant)

    month_key = _normalize_month_key(month)
    start_date, next_month = _month_bounds(month_key)
    tenant_id = tenant["id"]
    tenant_code_text = str(tenant.get("tenant_code") or "").strip().upper()
    requested_site_code = str(site_code or "").strip().upper()

    profiles = _collect_apple_profiles(conn, tenant_id)
    if not profiles:
        return {
            "ok": False,
            "tenant_code": tenant_code_text,
            "month": month_key,
            "message": "활성 Apple 보고 프로파일이 없습니다.",
            "results": [],
        }

    orchestrator = integrations_router.SheetsSyncOrchestrator(default_webhook_url=settings.google_sheets_default_webhook)
    period = {"start_date": start_date.isoformat(), "end_date": (next_month - timedelta(days=1)).isoformat()}
    results: list[dict[str, Any]] = []

    for profile in profiles:
        profile_id = profile.get("id")
        profile_name = str(profile.get("profile_name") or profile_id or "-").strip()
        profile_scope = _scope_from_profile_row(profile)
        intent = integrations_router._scope_to_sync_intent(profile_scope)
        is_enabled = integrations_router._is_sync_intent_enabled(conn, tenant_id, intent)

        if not is_enabled:
            results.append(
                {
                    "profile_id": str(profile_id),
                    "profile_name": profile_name,
                    "profile_scope": profile_scope,
                    "ok": False,
                    "sent": False,
                    "status": "SKIPPED_DISABLED",
                    "message": "해당 프로파일 기능 플래그가 비활성화되어 있습니다.",
                }
            )
            continue

        try:
            profile_options = profile.get("options_json") if isinstance(profile.get("options_json"), dict) else {}
            rows_by_section = integrations_router._build_rows_by_scope(
                conn,
                tenant_id=tenant_id,
                scope=profile_scope,
                start_date=start_date,
                end_date=next_month - timedelta(days=1),
                profile_options=profile_options,
            )

            profile_site_codes = integrations_router._resolve_profile_site_codes_from_row(profile)
            effective_site_codes = list(profile_site_codes)
            if requested_site_code:
                if effective_site_codes:
                    effective_site_codes = [code for code in effective_site_codes if code == requested_site_code]
                else:
                    effective_site_codes = [requested_site_code]
            if effective_site_codes:
                rows_by_section = integrations_router._filter_rows_by_site_codes(rows_by_section, effective_site_codes)

            dispatch = integrations_router._dispatch_profile_sync(
                conn,
                orchestrator=orchestrator,
                tenant_id=tenant_id,
                tenant_code=tenant_code_text,
                profile=profile,
                profile_scope=profile_scope,
                trigger="manual_apple_pack_run",
                trigger_event_type="manual_apple_pack_run",
                period=period,
                rows_by_section=rows_by_section,
                enqueue_retry=True,
                actor_user_id=user.get("id"),
                actor_role=actor_role,
            )
            results.append(
                {
                    "profile_id": str(profile_id),
                    "profile_name": profile_name,
                    "profile_scope": profile_scope,
                    "ok": bool(dispatch.get("ok")),
                    "sent": bool(dispatch.get("sent")),
                    "status": "SUCCESS" if bool(dispatch.get("ok")) else "FAIL",
                    "message": str(dispatch.get("sync_message") or ""),
                    "row_counts": dispatch.get("row_counts") if isinstance(dispatch.get("row_counts"), dict) else {},
                }
            )
        except Exception as exc:
            results.append(
                {
                    "profile_id": str(profile_id),
                    "profile_name": profile_name,
                    "profile_scope": profile_scope,
                    "ok": False,
                    "sent": False,
                    "status": "FAIL",
                    "message": str(exc),
                }
            )

    ok_count = sum(1 for row in results if row.get("status") == "SUCCESS")
    fail_count = sum(1 for row in results if row.get("status") == "FAIL")
    skipped_count = sum(1 for row in results if str(row.get("status") or "").startswith("SKIPPED"))

    return {
        "ok": fail_count == 0,
        "tenant_code": tenant_code_text,
        "month": month_key,
        "summary": {
            "total": len(results),
            "success": ok_count,
            "fail": fail_count,
            "skipped": skipped_count,
        },
        "results": results,
    }


@router.get("/apple/logs")
def list_apple_report_logs(
    month: str | None = Query(default=None, max_length=7),
    tenant_code: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=300),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    _assert_apple_tenant(tenant)

    month_key = _normalize_month_key(month)
    start_date, next_month = _month_bounds(month_key)
    tenant_id = tenant["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ssl.id,
                   ssl.status,
                   ssl.direction,
                   ssl.error_message,
                   ssl.created_at,
                   gp.id AS profile_id,
                   gp.profile_name,
                   gp.options_json
            FROM sheets_sync_log ssl
            LEFT JOIN google_sheet_profiles gp ON gp.id = ssl.profile_id
            WHERE ssl.tenant_id = %s
              AND ssl.created_at >= %s
              AND ssl.created_at < %s
            ORDER BY ssl.created_at DESC
            LIMIT %s
            """,
            (tenant_id, start_date, next_month, limit),
        )
        rows = cur.fetchall()

    logs: list[dict[str, Any]] = []
    for row in rows:
        scope = _scope_from_profile_row(row)
        if scope not in APPLE_PROFILE_SCOPES:
            continue
        logs.append(
            {
                "id": str(row.get("id")),
                "status": str(row.get("status") or "").strip().upper() or "FAIL",
                "direction": str(row.get("direction") or "DB_TO_SHEET").strip().upper(),
                "error_message": str(row.get("error_message") or "").strip(),
                "created_at": row.get("created_at"),
                "profile_id": str(row.get("profile_id")) if row.get("profile_id") else None,
                "profile_name": str(row.get("profile_name") or "").strip(),
                "profile_scope": scope,
            }
        )

    return {
        "tenant_code": str(tenant.get("tenant_code") or "").strip().upper(),
        "month": month_key,
        "logs": logs,
    }
