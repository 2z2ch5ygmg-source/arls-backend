from __future__ import annotations

from collections import Counter
import csv
import io
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO, StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook

from ...deps import get_db_conn, get_current_user, apply_rate_limit
from ...schemas import (
    AppleDaytimeShiftOut,
    AppleOvertimeCreate,
    AppleOvertimeOut,
    DailyEventCreate,
    DailyEventOut,
    DutyLogOut,
    DutyLogRowOut,
    ImportApplyOut,
    ImportApplyRowOut,
    ImportPreviewOut,
    ImportPreviewRowOut,
    LateShiftCreate,
    LateShiftOut,
    ScheduleCloserUpdate,
    ScheduleLeaderCandidateOut,
    ScheduleLeaderCandidatesOut,
    ScheduleCreateRow,
    ScheduleUpdate,
    SiteShiftPolicyOut,
    SiteShiftPolicyUpdate,
    SupportAssignmentCreate,
    SupportAssignmentOut,
)
from ...services.p1_schedule import (
    build_duty_log,
    create_apple_overtime_log,
    create_daily_event_log,
    create_late_shift_log,
    delete_daily_event_log,
    delete_late_shift_log,
    delete_support_assignment,
    generate_apple_daytime_shift,
    get_or_create_site_shift_policy,
    list_apple_overtime_logs,
    list_daily_event_logs,
    list_late_shift_logs,
    list_support_assignments,
    resolve_employee,
    resolve_site,
    resolve_support_entries_to_assignments,
    resolve_tenant,
    upsert_site_shift_policy,
    upsert_support_assignment,
)
from ...utils.permissions import can_manage_schedule, is_super_admin, normalize_role

router = APIRouter(prefix="/schedules", tags=["schedules"], dependencies=[Depends(apply_rate_limit)])


SHIFT_TYPE_ALIASES = {
    "leave": "off",
}
ALLOWED_SHIFT_TYPES = {"day", "night", "off", "holiday"}
NON_WORKING_SHIFT_TYPES = {"off", "holiday"}
TEAM_MANAGER_DUTY_ROLE = "TEAM_MANAGER"
VICE_SUPERVISOR_DUTY_ROLE = "VICE_SUPERVISOR"
GUARD_DUTY_ROLE = "GUARD"
IMPORT_FORMATS = {"csv", "xlsx"}
IMPORT_PREVIEW_LIMIT = 300
IMPORT_REPORT_LIMIT = 300
VALIDATION_MESSAGES = {
    "tenant_code_mismatch": "요청 계정 테넌트와 일치하지 않습니다.",
    "tenant_match_failed": "테넌트 코드 매칭 실패",
    "company_match_failed": "조직(회사) 코드 매칭 실패",
    "site_match_failed": "사이트 코드 매칭 실패",
    "employee_match_failed": "직원 코드 매칭 실패",
    "required_column_missing": "필수 컬럼 누락",
    "invalid_shift_type": "shift_type 값이 유효하지 않습니다.",
    "invalid_schedule_date": "schedule_date 형식이 올바르지 않습니다. (YYYY-MM-DD)",
    "time_conflict": "같은 직원/날짜 스케줄과 충돌합니다.",
}


def _normalize_shift_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if not normalized:
        return ""
    return SHIFT_TYPE_ALIASES.get(normalized, normalized)


def _schedule_import_headers() -> list[str]:
    return [
        "tenant_code",
        "company_code",
        "site_code",
        "employee_code",
        "schedule_date",
        "shift_type",
    ]


def _month_bounds(value: str) -> tuple[date, date]:
    try:
        start = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"error": "INVALID_MONTH", "message": "month must be YYYY-MM"},
        ) from exc

    if start.month == 12:
        end = datetime(start.year + 1, 1, 1).date()
    else:
        end = datetime(start.year, start.month + 1, 1).date()
    return start, end


def _normalize_header(value: str | None) -> str:
    return (value or "").strip().strip("\ufeff").lower()


def _normalize_import_row(row: dict[str, object]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, value in row.items():
        header = _normalize_header(str(key))
        if value is None:
            normalized[header] = ""
            continue
        if isinstance(value, datetime):
            normalized[header] = value.date().isoformat()
            continue
        if isinstance(value, date):
            normalized[header] = value.isoformat()
            continue
        if isinstance(value, float) and value.is_integer():
            normalized[header] = str(int(value))
            continue
        normalized[header] = str(value).strip()
    return normalized


def _parse_date_or_none(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _read_import_rows(file: UploadFile, raw_bytes: bytes) -> tuple[str, list[str], list[dict[str, str]]]:
    filename = (file.filename or "").lower()
    detected = "xlsx" if filename.endswith(".xlsx") else "csv"
    if detected not in IMPORT_FORMATS:
        detected = "csv"

    if detected == "xlsx":
        workbook = load_workbook(filename=BytesIO(raw_bytes), read_only=True, data_only=True)
        try:
            sheet = workbook.active
            rows_iter = sheet.iter_rows(values_only=True)
            header_cells = next(rows_iter, None)
            if not header_cells:
                return detected, [], []
            headers = [_normalize_header(str(cell) if cell is not None else "") for cell in header_cells]
            rows: list[dict[str, str]] = []
            for values in rows_iter:
                row_map: dict[str, str] = {}
                for idx, header in enumerate(headers):
                    cell_value = values[idx] if idx < len(values) else None
                    if cell_value is None:
                        row_map[header] = ""
                    elif isinstance(cell_value, datetime):
                        row_map[header] = cell_value.date().isoformat()
                    elif isinstance(cell_value, date):
                        row_map[header] = cell_value.isoformat()
                    elif isinstance(cell_value, float) and cell_value.is_integer():
                        row_map[header] = str(int(cell_value))
                    else:
                        row_map[header] = str(cell_value).strip()
                rows.append(row_map)
            return detected, headers, rows
        finally:
            workbook.close()

    try:
        raw = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        raw = raw_bytes.decode("cp949")
    reader = csv.DictReader(io.StringIO(raw))
    raw_headers = [_normalize_header(item) for item in (reader.fieldnames or [])]
    rows = [_normalize_import_row(row) for row in reader]
    return detected, raw_headers, rows


def _resolve_import_refs(
    cur,
    user,
    tenant_code: str,
    company_code: str,
    site_code: str,
    employee_code: str,
) -> tuple[dict | None, str | None, str | None]:
    cur.execute("SELECT id FROM tenants WHERE tenant_code = %s", (tenant_code,))
    tenant = cur.fetchone()
    if not tenant:
        return None, "tenant_match_failed", VALIDATION_MESSAGES["tenant_match_failed"]

    if not is_super_admin(user["role"]) and str(tenant["id"]) != str(user["tenant_id"]):
        return None, "tenant_code_mismatch", VALIDATION_MESSAGES["tenant_code_mismatch"]

    cur.execute(
        "SELECT id FROM companies WHERE tenant_id = %s AND company_code = %s",
        (tenant["id"], company_code),
    )
    company = cur.fetchone()
    if not company:
        return None, "company_match_failed", VALIDATION_MESSAGES["company_match_failed"]

    cur.execute(
        "SELECT id FROM sites WHERE tenant_id = %s AND company_id = %s AND site_code = %s",
        (tenant["id"], company["id"], site_code),
    )
    site = cur.fetchone()
    if not site:
        return None, "site_match_failed", VALIDATION_MESSAGES["site_match_failed"]

    cur.execute(
        "SELECT id, site_id FROM employees WHERE tenant_id = %s AND employee_code = %s",
        (tenant["id"], employee_code),
    )
    employee = cur.fetchone()
    if not employee:
        return None, "employee_match_failed", VALIDATION_MESSAGES["employee_match_failed"]

    if str(employee["site_id"]) != str(site["id"]):
        return None, "site_match_failed", "직원이 해당 사이트에 배정되어 있지 않습니다."

    refs = {
        "tenant_id": tenant["id"],
        "company_id": company["id"],
        "site_id": site["id"],
        "employee_id": employee["id"],
    }
    return refs, None, None


def _parse_export_period(
    month: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[date, date, str]:
    if start_date or end_date:
        if not start_date or not end_date:
            raise HTTPException(status_code=400, detail="start_date and end_date must be provided together")
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD") from exc
        if end < start:
            raise HTTPException(status_code=400, detail="end_date must be greater than or equal to start_date")
        return start, end + timedelta(days=1), f"{start.isoformat()}_{end.isoformat()}"

    if not month:
        raise HTTPException(status_code=400, detail="month or start_date/end_date is required")

    start, next_month_start = _month_bounds(month)
    return start, next_month_start, month


def _fetch_export_rows(
    conn,
    tenant_id: str,
    period_start: date,
    period_end_exclusive: date,
    company_code: str,
    site_code: str,
) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code,
                   c.company_code,
                   s.site_code,
                   e.employee_code,
                   ms.schedule_date,
                   ms.shift_type
            FROM monthly_schedules ms
            JOIN tenants t ON t.id = ms.tenant_id
            JOIN companies c ON c.id = ms.company_id
            JOIN sites s ON s.id = ms.site_id
            JOIN employees e ON e.id = ms.employee_id
            WHERE ms.tenant_id = %s
              AND ms.schedule_date >= %s
              AND ms.schedule_date < %s
              AND (%s = '' OR c.company_code = %s)
              AND (%s = '' OR s.site_code = %s)
            ORDER BY e.employee_code, ms.schedule_date
            """,
            (
                tenant_id,
                period_start,
                period_end_exclusive,
                company_code,
                company_code,
                site_code,
                site_code,
            ),
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/import/template")
def download_schedule_template(
    file_format: str = Query("csv", alias="format"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    normalized_format = (file_format or "csv").strip().lower()
    if normalized_format not in IMPORT_FORMATS:
        raise HTTPException(status_code=400, detail="format must be csv or xlsx")

    headers = _schedule_import_headers()
    if normalized_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "schedule_import_template"
        sheet.append(headers)
        out = BytesIO()
        workbook.save(out)
        out.seek(0)
        return StreamingResponse(
            out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=schedule_import_template.xlsx"},
        )

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    out.seek(0)

    return StreamingResponse(
        out,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=schedule_import_template.csv"},
    )


def _lookup_refs(conn, tenant_id: str, tenant_code: str, company_code: str, site_code: str, employee_code: str):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id AS tenant_id, c.id AS company_id, s.id AS site_id, e.id AS employee_id
            FROM tenants t
            JOIN companies c ON c.tenant_id = t.id
            JOIN sites s ON s.company_id = c.id
            JOIN employees e ON e.site_id = s.id
            WHERE t.id = %s
              AND t.tenant_code = %s
              AND c.company_code = %s
              AND s.site_code = %s
              AND e.employee_code = %s
            """,
            (tenant_id, tenant_code, company_code, site_code, employee_code),
        )
        return cur.fetchone()


def _resolve_target_tenant(conn, user, tenant_code: str | None):
    own_tenant_id = user["tenant_id"]
    own_tenant_code = str(user.get("tenant_code") or "").strip()
    own_tenant_code_normalized = own_tenant_code.lower()
    requested_tenant_code = str(tenant_code or "").strip()
    requested_tenant_code_normalized = requested_tenant_code.lower()

    if not is_super_admin(user["role"]):
        if requested_tenant_code_normalized and requested_tenant_code_normalized != own_tenant_code_normalized:
            raise HTTPException(
                status_code=403,
                detail={"error": "FORBIDDEN", "message": "tenant mismatch"},
            )
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    if not requested_tenant_code_normalized:
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            WHERE lower(trim(tenant_code)) = %s
            LIMIT 1
            """,
            (requested_tenant_code_normalized,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )
    if row.get("is_deleted") or row.get("is_active") is False:
        raise HTTPException(
            status_code=403,
            detail={"error": "TENANT_DISABLED", "message": "tenant disabled"},
        )
    return row


@router.get("")
def monthly_view_alias(
    month: str = Query(..., description="YYYY-MM"),
    tenant_code: str | None = None,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    # Legacy alias for older clients still calling /api/v1/schedules?month=YYYY-MM.
    return monthly_view(month=month, tenant_code=tenant_code, conn=conn, user=user)


def _normalize_duty_role(value: str | None, user_role: str | None = None) -> str:
    raw = str(value or "").strip().upper()
    if raw in {VICE_SUPERVISOR_DUTY_ROLE, GUARD_DUTY_ROLE, TEAM_MANAGER_DUTY_ROLE}:
        return raw
    if str(user_role or "").strip().lower() == "branch_manager":
        return VICE_SUPERVISOR_DUTY_ROLE
    return GUARD_DUTY_ROLE


def _fetch_schedule_context(conn, schedule_id: uuid.UUID | str, tenant_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.id, ms.tenant_id, ms.company_id, ms.site_id, ms.employee_id, ms.schedule_date, ms.shift_type,
                   ms.leader_user_id, s.site_code
            FROM monthly_schedules ms
            JOIN sites s ON s.id = ms.site_id
            WHERE ms.id = %s
              AND ms.tenant_id = %s
            LIMIT 1
            """,
            (str(schedule_id), tenant_id),
        )
        return cur.fetchone()


def _fetch_leader_candidates_for_site_day(conn, *, tenant_id, site_id, schedule_date: date) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id AS user_id,
                   au.username,
                   au.full_name,
                   e.employee_code,
                   COALESCE(e.duty_role, '') AS duty_role_raw,
                   COALESCE(au.role, '') AS user_role
            FROM monthly_schedules ms
            JOIN employees e ON e.id = ms.employee_id
            JOIN arls_users au ON au.tenant_id = ms.tenant_id
                              AND au.employee_id = ms.employee_id
                              AND au.is_active = TRUE
            WHERE ms.tenant_id = %s
              AND ms.site_id = %s
              AND ms.schedule_date = %s
              AND lower(ms.shift_type) NOT IN ('off', 'holiday')
            GROUP BY au.id, au.username, au.full_name, e.employee_code, e.duty_role, au.role
            ORDER BY e.employee_code, au.username
            """,
            (tenant_id, site_id, schedule_date),
        )
        rows = [dict(row) for row in cur.fetchall()]

    candidates: list[dict] = []
    for row in rows:
        duty_role = _normalize_duty_role(row.get("duty_role_raw"), row.get("user_role"))
        if duty_role == TEAM_MANAGER_DUTY_ROLE:
            continue
        candidates.append(
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "full_name": row["full_name"],
                "employee_code": row["employee_code"],
                "duty_role": duty_role,
            }
        )

    def _priority(item: dict) -> tuple[int, str]:
        duty_role = item.get("duty_role")
        if duty_role == VICE_SUPERVISOR_DUTY_ROLE:
            return (1, str(item.get("employee_code") or ""))
        if duty_role == GUARD_DUTY_ROLE:
            return (2, str(item.get("employee_code") or ""))
        return (9, str(item.get("employee_code") or ""))

    candidates.sort(key=_priority)
    return candidates


def _recommended_leader_user_id(candidates: list[dict]) -> str | None:
    if not candidates:
        return None
    for duty_role in (VICE_SUPERVISOR_DUTY_ROLE, GUARD_DUTY_ROLE):
        for candidate in candidates:
            if str(candidate.get("duty_role") or "") == duty_role:
                return str(candidate["user_id"])
    return str(candidates[0]["user_id"])


def _refresh_daily_leader_defaults(conn, *, tenant_id, site_id, schedule_date: date) -> str | None:
    candidates = _fetch_leader_candidates_for_site_day(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        schedule_date=schedule_date,
    )
    recommended_user_id = _recommended_leader_user_id(candidates)
    candidate_ids = [str(item["user_id"]) for item in candidates]

    with conn.cursor() as cur:
        if not recommended_user_id:
            # No eligible on-duty leader exists. Clear stale leader assignments for the day.
            cur.execute(
                """
                UPDATE monthly_schedules
                SET leader_user_id = NULL
                WHERE tenant_id = %s
                  AND site_id = %s
                  AND schedule_date = %s
                  AND lower(shift_type) NOT IN ('off', 'holiday')
                """,
                (tenant_id, site_id, schedule_date),
            )
            return None

        cur.execute(
            """
            UPDATE monthly_schedules
            SET leader_user_id = %s
            WHERE tenant_id = %s
              AND site_id = %s
              AND schedule_date = %s
              AND lower(shift_type) NOT IN ('off', 'holiday')
              AND (
                    leader_user_id IS NULL
                    OR NOT (leader_user_id = ANY(%s::uuid[]))
              )
            """,
            (recommended_user_id, tenant_id, site_id, schedule_date, candidate_ids),
        )
    return recommended_user_id


def _assert_valid_leader_for_site_day(
    conn,
    *,
    tenant_id,
    site_id,
    schedule_date: date,
    leader_user_id: str,
) -> None:
    candidates = _fetch_leader_candidates_for_site_day(
        conn,
        tenant_id=tenant_id,
        site_id=site_id,
        schedule_date=schedule_date,
    )
    candidate_ids = {str(item["user_id"]) for item in candidates}
    if str(leader_user_id) not in candidate_ids:
        raise HTTPException(
            status_code=400,
            detail="leader must be an on-duty VICE_SUPERVISOR/GUARD for this site/date",
        )


@router.get("/monthly")
def monthly_view(
    month: str = Query(..., description="YYYY-MM"),
    tenant_code: str | None = None,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    start, end = _month_bounds(month)
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.tenant_code,
                   ms.id,
                   c.company_code,
                   s.site_code,
                   e.employee_code,
                   e.full_name AS employee_name,
                   ms.schedule_date,
                   ms.shift_type,
                   ms.source,
                   ms.source_ticket_id,
                   ms.schedule_note,
                   ms.leader_user_id,
                   lu.username AS leader_username,
                   lu.full_name AS leader_full_name,
                   (lower(COALESCE(ms.schedule_note, '')) LIKE '%%closer%%') AS is_closer,
                   cu.id AS closer_user_id,
                   cu.username AS closer_username,
                   cu.full_name AS closer_full_name,
                   ce.employee_code AS closer_employee_code
            FROM monthly_schedules ms
            JOIN tenants t ON t.id = ms.tenant_id
            JOIN companies c ON c.id = ms.company_id
            JOIN sites s ON s.id = ms.site_id
            JOIN employees e ON e.id = ms.employee_id
            LEFT JOIN arls_users lu ON lu.id = ms.leader_user_id
            LEFT JOIN LATERAL (
                SELECT ms2.employee_id AS closer_employee_id
                FROM monthly_schedules ms2
                WHERE ms2.tenant_id = ms.tenant_id
                  AND ms2.site_id = ms.site_id
                  AND ms2.schedule_date = ms.schedule_date
                  AND lower(COALESCE(ms2.schedule_note, '')) LIKE '%%closer%%'
                ORDER BY ms2.employee_id
                LIMIT 1
            ) closer ON TRUE
            LEFT JOIN employees ce ON ce.id = closer.closer_employee_id
            LEFT JOIN arls_users cu
                   ON cu.tenant_id = ms.tenant_id
                  AND cu.employee_id = closer.closer_employee_id
                  AND cu.is_active = TRUE
            WHERE ms.tenant_id = %s
              AND ms.schedule_date >= %s
              AND ms.schedule_date < %s
            ORDER BY e.employee_code, ms.schedule_date
            """,
            (target_tenant["id"], start, end),
        )
        return [dict(r) for r in cur.fetchall()]


@router.get("/soc-leave-logs")
def list_soc_leave_logs(
    tenant_code: str | None = Query(default=None, max_length=64),
    start_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    end_date: str | None = Query(default=None, description="YYYY-MM-DD"),
    limit: int = Query(default=50, ge=1, le=300),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)

    if start_date and end_date:
        try:
            period_start = datetime.strptime(start_date, "%Y-%m-%d").date()
            period_end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="start_date/end_date must be YYYY-MM-DD") from exc
        if period_end < period_start:
            raise HTTPException(status_code=400, detail="end_date must be greater than or equal to start_date")
    else:
        period_end = datetime.utcnow().date()
        period_start = period_end - timedelta(days=30)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.id AS schedule_id,
                   t.tenant_code,
                   e.employee_code,
                   e.full_name AS employee_name,
                   s.site_code,
                   s.site_name,
                   ms.schedule_date,
                   ms.shift_type,
                   ms.source,
                   ms.source_ticket_id,
                   ms.schedule_note,
                   COALESCE((to_jsonb(ms)->>'updated_at')::timestamptz, ms.created_at) AS updated_at
            FROM monthly_schedules ms
            JOIN tenants t ON t.id = ms.tenant_id
            JOIN employees e ON e.id = ms.employee_id
            JOIN sites s ON s.id = ms.site_id
            WHERE ms.tenant_id = %s
              AND ms.schedule_date BETWEEN %s AND %s
              AND lower(COALESCE(ms.source, '')) = 'soc'
              AND lower(ms.shift_type) IN ('off', 'holiday')
            ORDER BY ms.schedule_date DESC, e.employee_code ASC
            LIMIT %s
            """,
            (target_tenant["id"], period_start, period_end, limit),
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/overtime-daily")
def list_overtime_daily(
    date: str = Query(..., description="YYYY-MM-DD"),
    tenant_code: str | None = Query(default=None, max_length=64),
    employee_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    try:
        work_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD") from exc

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    employee_filter = str(employee_code or "").strip()
    if not can_manage_schedule(user["role"]):
        # Employee role can only read own overtime records.
        own_employee_id = user.get("employee_id")
        if not own_employee_id:
            return []
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_code
                FROM employees
                WHERE id = %s
                  AND tenant_id = %s
                LIMIT 1
                """,
                (own_employee_id, target_tenant["id"]),
            )
            own_row = cur.fetchone()
        own_employee_code = str(own_row["employee_code"] if own_row else "").strip()
        if employee_filter and employee_filter != own_employee_code:
            raise HTTPException(status_code=403, detail="employee mismatch")
        employee_filter = own_employee_code

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT so.id,
                   so.work_date,
                   so.employee_id,
                   e.employee_code,
                   e.full_name AS employee_name,
                   s.site_code,
                   s.site_name,
                   so.ticket_id,
                   so.reason,
                   so.source,
                   so.overtime_source,
                   so.overtime_policy,
                   so.approved_minutes,
                   so.raw_minutes_total,
                   so.overtime_hours_step,
                   so.closer_user_id,
                   cu.username AS closer_username,
                   cu.full_name AS closer_full_name,
                   so.updated_at
            FROM soc_overtime_approvals so
            JOIN employees e ON e.id = so.employee_id
            LEFT JOIN sites s ON s.id = so.site_id
            LEFT JOIN arls_users cu ON cu.id = so.closer_user_id
            WHERE so.tenant_id = %s
              AND so.work_date = %s
              AND (%s = '' OR e.employee_code = %s)
            ORDER BY
              e.employee_code ASC,
              CASE WHEN so.overtime_source = 'SOC_TICKET' THEN 0 ELSE 1 END,
              so.updated_at DESC
            """,
            (target_tenant["id"], work_date, employee_filter, employee_filter),
        )
        return [dict(row) for row in cur.fetchall()]


@router.get("/monthly/{schedule_id}/leader-candidates", response_model=ScheduleLeaderCandidatesOut)
def get_schedule_leader_candidates(
    schedule_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    context = _fetch_schedule_context(conn, schedule_id, target_tenant["id"])
    if not context:
        raise HTTPException(status_code=404, detail="schedule not found")

    candidates = _fetch_leader_candidates_for_site_day(
        conn,
        tenant_id=context["tenant_id"],
        site_id=context["site_id"],
        schedule_date=context["schedule_date"],
    )
    recommended = _recommended_leader_user_id(candidates)

    payload_candidates = [
        ScheduleLeaderCandidateOut(
            user_id=item["user_id"],
            username=item["username"],
            full_name=item["full_name"],
            employee_code=item["employee_code"],
            duty_role=item["duty_role"],
            is_recommended=(recommended is not None and str(item["user_id"]) == str(recommended)),
        )
        for item in candidates
    ]

    return ScheduleLeaderCandidatesOut(
        schedule_id=schedule_id,
        site_code=context["site_code"],
        schedule_date=context["schedule_date"],
        current_leader_user_id=context.get("leader_user_id"),
        recommended_leader_user_id=recommended,
        candidates=payload_candidates,
    )


@router.post("/monthly")
def upsert_monthly_rows(
    rows: list[ScheduleCreateRow],
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    created = 0
    skipped = 0
    affected_site_days: set[tuple[str, str, str]] = set()

    with conn.cursor() as cur:
        for row in rows:
            refs = _lookup_refs(
                conn,
                user["tenant_id"],
                user["tenant_code"],
                row.company_code,
                row.site_code,
                row.employee_code,
            )
            if not refs:
                skipped += 1
                continue

            cur.execute(
                """
                SELECT 1
                FROM monthly_schedules
                WHERE tenant_id = %s
                  AND employee_id = %s
                  AND schedule_date = %s
                """,
                (user["tenant_id"], refs["employee_id"], row.schedule_date),
            )
            if cur.fetchone():
                skipped += 1
                continue

            cur.execute(
                """
                INSERT INTO monthly_schedules (id, tenant_id, company_id, site_id, employee_id, schedule_date, shift_type, leader_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (
                    uuid.uuid4(),
                    user["tenant_id"],
                    refs["company_id"],
                    refs["site_id"],
                    refs["employee_id"],
                    row.schedule_date,
                    row.shift_type,
                ),
            )
            affected_site_days.add((str(user["tenant_id"]), str(refs["site_id"]), row.schedule_date.isoformat()))
            created += 1

    for tenant_id, site_id, schedule_date_raw in affected_site_days:
        _refresh_daily_leader_defaults(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            schedule_date=date.fromisoformat(schedule_date_raw),
        )

    return {"created": created, "skipped": skipped}


@router.get("/export")
def export_monthly_csv(
    month: str | None = Query(None, description="YYYY-MM"),
    start_date: str | None = Query(None, description="YYYY-MM-DD"),
    end_date: str | None = Query(None, description="YYYY-MM-DD"),
    tenant_code: str | None = None,
    company_code: str | None = None,
    site_code: str | None = None,
    file_format: str = Query("xlsx", alias="format"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = (tenant_code or user["tenant_code"]).strip()
    company_filter = (company_code or "").strip()
    site_filter = (site_code or "").strip()
    normalized_format = (file_format or "xlsx").strip().lower()
    if normalized_format not in IMPORT_FORMATS:
        raise HTTPException(status_code=400, detail="format must be csv or xlsx")

    period_start, period_end_exclusive, period_label = _parse_export_period(month, start_date, end_date)

    with conn.cursor() as cur:
        cur.execute("SELECT id, tenant_code FROM tenants WHERE tenant_code = %s", (target_tenant,))
        tenant = cur.fetchone()
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant not found")
    if tenant["tenant_code"] != user["tenant_code"] and not is_super_admin(user["role"]):
        raise HTTPException(status_code=403, detail="tenant mismatch")

    payload = _fetch_export_rows(
        conn=conn,
        tenant_id=tenant["id"],
        period_start=period_start,
        period_end_exclusive=period_end_exclusive,
        company_code=company_filter,
        site_code=site_filter,
    )

    headers = _schedule_import_headers()
    if normalized_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "schedule_export"
        sheet.append(headers)
        for row in payload:
            sheet.append(
                [
                    row["tenant_code"],
                    row["company_code"],
                    row["site_code"],
                    row["employee_code"],
                    str(row["schedule_date"]),
                    row["shift_type"],
                ]
            )
        out = BytesIO()
        workbook.save(out)
        out.seek(0)
        return StreamingResponse(
            out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=schedule_export_{period_label}.xlsx"},
        )

    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in payload:
        writer.writerow(
            [
                row["tenant_code"],
                row["company_code"],
                row["site_code"],
                row["employee_code"],
                str(row["schedule_date"]),
                row["shift_type"],
            ]
        )

    out.seek(0)
    return StreamingResponse(
        out,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=schedule_export_{period_label}.csv"},
    )


@router.post("/import/preview", response_model=ImportPreviewOut)
def preview_import(
    file: UploadFile,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    raw_bytes = file.file.read()
    try:
        detected_format, raw_headers, rows = _read_import_rows(file, raw_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="invalid import file") from exc
    batch_id = uuid.uuid4()
    total = 0
    valid = 0
    invalid = 0
    errors: list[str] = []
    preview_rows: list[ImportPreviewRowOut] = []
    error_counts: Counter[str] = Counter()
    seen_employee_date: set[tuple[str, str, str]] = set()

    required_headers = set(_schedule_import_headers())
    if (
        not raw_headers
        or len(raw_headers) != len(set(raw_headers))
        or set(raw_headers) != required_headers
    ):
        raise HTTPException(status_code=400, detail="invalid import header")

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO schedule_import_batches (id, tenant_id, created_by, filename) VALUES (%s, %s, %s, %s)",
            (batch_id, user["tenant_id"], user["id"], file.filename or f"schedule_import.{detected_format}"),
        )

        for row_no, row in enumerate(rows, start=1):
            total += 1

            normalized_row = _normalize_import_row(row)
            tenant_code = normalized_row.get("tenant_code", "")
            company_code = normalized_row.get("company_code", "")
            site_code = normalized_row.get("site_code", "")
            employee_code = normalized_row.get("employee_code", "")
            shift_type_raw = normalized_row.get("shift_type", "")
            shift_type = _normalize_shift_type(shift_type_raw)
            schedule_date_raw = normalized_row.get("schedule_date", "")

            validation_code = None
            validation_error = None
            schedule_date = None
            if tenant_code != user["tenant_code"] and not is_super_admin(user["role"]):
                validation_code = "tenant_code_mismatch"
                validation_error = VALIDATION_MESSAGES["tenant_code_mismatch"]
            if not (tenant_code and company_code and site_code and employee_code and schedule_date_raw and shift_type_raw):
                validation_code = "required_column_missing"
                validation_error = VALIDATION_MESSAGES["required_column_missing"]
            elif shift_type not in ALLOWED_SHIFT_TYPES:
                validation_code = "invalid_shift_type"
                validation_error = VALIDATION_MESSAGES["invalid_shift_type"]
            else:
                schedule_date = _parse_date_or_none(schedule_date_raw)
                if not schedule_date:
                    validation_code = "invalid_schedule_date"
                    validation_error = VALIDATION_MESSAGES["invalid_schedule_date"]

            refs = None
            if not validation_code:
                refs, validation_code, validation_error = _resolve_import_refs(
                    cur,
                    user,
                    tenant_code=tenant_code,
                    company_code=company_code,
                    site_code=site_code,
                    employee_code=employee_code,
                )

            if not validation_code and refs and schedule_date:
                dedup_key = (str(refs["tenant_id"]), str(refs["employee_id"]), schedule_date.isoformat())
                if dedup_key in seen_employee_date:
                    validation_code = "time_conflict"
                    validation_error = "파일 내 중복 스케줄입니다."
                else:
                    cur.execute(
                        """
                        SELECT 1
                        FROM monthly_schedules
                        WHERE tenant_id = %s
                          AND employee_id = %s
                          AND schedule_date = %s
                        """,
                        (refs["tenant_id"], refs["employee_id"], schedule_date),
                    )
                    if cur.fetchone():
                        validation_code = "time_conflict"
                        validation_error = "이미 등록된 스케줄과 충돌합니다."
                    else:
                        seen_employee_date.add(dedup_key)

            cur.execute(
                """
                INSERT INTO schedule_import_rows
                (id, batch_id, row_no, tenant_code, company_code, site_code, employee_code,
                 schedule_date, shift_type, validation_error, employee_id, company_id, site_id,
                 tenant_id, is_valid)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    uuid.uuid4(),
                    batch_id,
                    row_no,
                    tenant_code,
                    company_code,
                    site_code,
                    employee_code,
                    schedule_date,
                    shift_type or shift_type_raw,
                    validation_error,
                    refs["employee_id"] if refs else None,
                    refs["company_id"] if refs else None,
                    refs["site_id"] if refs else None,
                    refs["tenant_id"] if refs else user["tenant_id"],
                    validation_code is None,
                ),
            )

            preview_rows.append(
                ImportPreviewRowOut(
                    row_no=row_no,
                    tenant_code=tenant_code,
                    company_code=company_code,
                    site_code=site_code,
                    employee_code=employee_code,
                    schedule_date=schedule_date_raw or (schedule_date.isoformat() if schedule_date else None),
                    shift_type=shift_type or shift_type_raw,
                    is_valid=validation_code is None,
                    validation_code=validation_code,
                    validation_error=validation_error,
                )
            )

            if validation_code:
                invalid += 1
                error_counts[validation_code] += 1
                if len(errors) < 20:
                    errors.append(f"row {row_no}: {validation_error}")
            else:
                valid += 1

        cur.execute(
            "UPDATE schedule_import_batches SET total_rows = %s, valid_rows = %s, invalid_rows = %s WHERE id = %s",
            (total, valid, invalid, batch_id),
        )

    return ImportPreviewOut(
        batch_id=batch_id,
        total_rows=total,
        valid_rows=valid,
        invalid_rows=invalid,
        invalid_samples=errors,
        preview_rows=preview_rows[:IMPORT_PREVIEW_LIMIT],
        error_counts=dict(error_counts),
    )


@router.post("/import/{batch_id}/apply", response_model=ImportApplyOut)
def apply_import(
    batch_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    with conn.cursor() as cur:
        cur.execute(
            "SELECT status FROM schedule_import_batches WHERE id = %s AND tenant_id = %s",
            (batch_id, user["tenant_id"]),
        )
        batch = cur.fetchone()
        if not batch:
            raise HTTPException(status_code=404, detail="batch not found")
        if str(batch["status"]).lower() == "applied":
            raise HTTPException(status_code=409, detail="batch already applied")

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM schedule_import_rows
            WHERE batch_id = %s AND is_valid = FALSE
            """,
            (batch_id,),
        )
        invalid_count_row = cur.fetchone()
        invalid_count = int(invalid_count_row["cnt"]) if invalid_count_row else 0

        cur.execute(
            """
            SELECT row_no, employee_code, site_code, schedule_date, shift_type, validation_error
            FROM schedule_import_rows
            WHERE batch_id = %s AND is_valid = FALSE
            ORDER BY row_no
            LIMIT %s
            """,
            (batch_id, IMPORT_REPORT_LIMIT),
        )
        invalid_rows = cur.fetchall()

        cur.execute(
            """
            SELECT row_no, tenant_id, company_id, site_id, employee_id, employee_code, site_code, schedule_date, shift_type
            FROM schedule_import_rows
            WHERE batch_id = %s AND is_valid = TRUE
            ORDER BY row_no
            """,
            (batch_id,),
        )
        rows = cur.fetchall()

        applied = 0
        skipped = invalid_count
        applied_rows: list[ImportApplyRowOut] = []
        skipped_rows: list[ImportApplyRowOut] = []
        dedup_applied: set[tuple[str, str, str]] = set()
        affected_site_days: set[tuple[str, str, str]] = set()

        for row in invalid_rows:
            if len(skipped_rows) >= IMPORT_REPORT_LIMIT:
                break
            skipped_rows.append(
                ImportApplyRowOut(
                    row_no=row["row_no"],
                    employee_code=row["employee_code"],
                    site_code=row["site_code"],
                    schedule_date=str(row["schedule_date"]) if row["schedule_date"] else None,
                    shift_type=row["shift_type"],
                    status="invalid",
                    reason=row["validation_error"] or "미리보기 검증 실패",
                )
            )

        for row in rows:
            shift_type = _normalize_shift_type(row["shift_type"])
            if shift_type not in ALLOWED_SHIFT_TYPES:
                skipped += 1
                if len(skipped_rows) < IMPORT_REPORT_LIMIT:
                    skipped_rows.append(
                        ImportApplyRowOut(
                            row_no=row["row_no"],
                            employee_code=row["employee_code"],
                            site_code=row["site_code"],
                            schedule_date=str(row["schedule_date"]) if row["schedule_date"] else None,
                            shift_type=row["shift_type"],
                            status="skipped",
                            reason="invalid shift_type",
                        )
                    )
                continue

            if not (row["tenant_id"] and row["company_id"] and row["site_id"] and row["employee_id"] and row["schedule_date"]):
                skipped += 1
                if len(skipped_rows) < IMPORT_REPORT_LIMIT:
                    skipped_rows.append(
                        ImportApplyRowOut(
                            row_no=row["row_no"],
                            employee_code=row["employee_code"],
                            site_code=row["site_code"],
                            schedule_date=str(row["schedule_date"]) if row["schedule_date"] else None,
                            shift_type=shift_type,
                            status="skipped",
                            reason="lookup metadata missing",
                        )
                    )
                continue

            dedup_key = (
                str(row["tenant_id"]),
                str(row["employee_id"]),
                str(row["schedule_date"]),
            )
            if dedup_key in dedup_applied:
                skipped += 1
                if len(skipped_rows) < IMPORT_REPORT_LIMIT:
                    skipped_rows.append(
                        ImportApplyRowOut(
                            row_no=row["row_no"],
                            employee_code=row["employee_code"],
                            site_code=row["site_code"],
                            schedule_date=str(row["schedule_date"]),
                            shift_type=shift_type,
                            status="skipped",
                            reason="time_conflict (duplicate in batch)",
                        )
                    )
                continue
            dedup_applied.add(dedup_key)

            cur.execute(
                """
                SELECT 1 FROM monthly_schedules
                WHERE tenant_id = %s AND employee_id = %s AND schedule_date = %s
                """,
                (row["tenant_id"], row["employee_id"], row["schedule_date"]),
            )
            if cur.fetchone():
                skipped += 1
                if len(skipped_rows) < IMPORT_REPORT_LIMIT:
                    skipped_rows.append(
                        ImportApplyRowOut(
                            row_no=row["row_no"],
                            employee_code=row["employee_code"],
                            site_code=row["site_code"],
                            schedule_date=str(row["schedule_date"]),
                            shift_type=shift_type,
                            status="skipped",
                            reason="time_conflict (already exists)",
                        )
                    )
                continue

            cur.execute(
                """
                INSERT INTO monthly_schedules (id, tenant_id, company_id, site_id, employee_id, schedule_date, shift_type, leader_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL)
                """,
                (
                    uuid.uuid4(),
                    row["tenant_id"],
                    row["company_id"],
                    row["site_id"],
                    row["employee_id"],
                    row["schedule_date"],
                    shift_type,
                )
            )
            affected_site_days.add((str(row["tenant_id"]), str(row["site_id"]), str(row["schedule_date"])))
            applied += 1
            if len(applied_rows) < IMPORT_REPORT_LIMIT:
                applied_rows.append(
                    ImportApplyRowOut(
                        row_no=row["row_no"],
                        employee_code=row["employee_code"],
                        site_code=row["site_code"],
                        schedule_date=str(row["schedule_date"]),
                        shift_type=shift_type,
                        status="applied",
                        reason="applied",
                    )
                )

        cur.execute(
            "UPDATE schedule_import_batches SET status = 'applied', completed_at = timezone('utc', now()) WHERE id = %s",
            (batch_id,),
        )

    for tenant_id, site_id, schedule_date_raw in affected_site_days:
        _refresh_daily_leader_defaults(
            conn,
            tenant_id=tenant_id,
            site_id=site_id,
            schedule_date=date.fromisoformat(schedule_date_raw),
        )

    return ImportApplyOut(
        batch_id=batch_id,
        applied=applied,
        skipped=skipped,
        applied_rows=applied_rows,
        skipped_rows=skipped_rows,
    )


@router.put("/monthly/{schedule_id}")
def update_monthly_schedule(
    schedule_id: uuid.UUID,
    payload: ScheduleUpdate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    context = _fetch_schedule_context(conn, schedule_id, target_tenant["id"])
    if not context:
        raise HTTPException(status_code=404, detail="schedule not found")

    leader_field_provided = "leader_user_id" in payload.model_fields_set
    next_shift_type = _normalize_shift_type(payload.shift_type)
    if next_shift_type not in ALLOWED_SHIFT_TYPES:
        raise HTTPException(status_code=400, detail="shift_type invalid")

    next_leader_user_id = context.get("leader_user_id")
    if leader_field_provided:
        next_leader_user_id = payload.leader_user_id

    if next_shift_type in NON_WORKING_SHIFT_TYPES:
        next_leader_user_id = None
    elif next_leader_user_id:
        _assert_valid_leader_for_site_day(
            conn,
            tenant_id=context["tenant_id"],
            site_id=context["site_id"],
            schedule_date=context["schedule_date"],
            leader_user_id=str(next_leader_user_id),
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE monthly_schedules
            SET shift_type = %s,
                leader_user_id = %s
            WHERE id = %s AND tenant_id = %s
            """,
            (next_shift_type, next_leader_user_id, str(schedule_id), target_tenant["id"]),
        )

    recommended_user_id = _refresh_daily_leader_defaults(
        conn,
        tenant_id=context["tenant_id"],
        site_id=context["site_id"],
        schedule_date=context["schedule_date"],
    )

    return {
        "id": str(schedule_id),
        "shift_type": next_shift_type,
        "leader_user_id": str(next_leader_user_id) if next_leader_user_id else None,
        "recommended_leader_user_id": recommended_user_id,
    }


@router.post("/monthly/{schedule_id}/closer")
def set_monthly_schedule_closer(
    schedule_id: uuid.UUID,
    payload: ScheduleCloserUpdate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    context = _fetch_schedule_context(conn, schedule_id, target_tenant["id"])
    if not context:
        raise HTTPException(status_code=404, detail="schedule not found")

    if payload.enabled and str(context.get("shift_type") or "").strip().lower() in NON_WORKING_SHIFT_TYPES:
        raise HTTPException(status_code=400, detail="closer must be an on-duty schedule row")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE monthly_schedules
            SET schedule_note = NULLIF(
                btrim(
                    regexp_replace(
                        regexp_replace(COALESCE(schedule_note, ''), '(\\[closer\\]|\\bcloser\\b)', '', 'gi'),
                        '\\s{2,}',
                        ' ',
                        'g'
                    )
                ),
                ''
            )
            WHERE tenant_id = %s
              AND site_id = %s
              AND schedule_date = %s
            """,
            (context["tenant_id"], context["site_id"], context["schedule_date"]),
        )

        if payload.enabled:
            cur.execute(
                """
                UPDATE monthly_schedules
                SET schedule_note = CASE
                    WHEN lower(COALESCE(schedule_note, '')) LIKE '%%closer%%' THEN schedule_note
                    WHEN COALESCE(schedule_note, '') = '' THEN '[closer]'
                    ELSE btrim(schedule_note || ' [closer]')
                END
                WHERE id = %s
                  AND tenant_id = %s
                  AND lower(shift_type) NOT IN ('off', 'holiday')
                RETURNING employee_id
                """,
                (str(schedule_id), target_tenant["id"]),
            )
            marked = cur.fetchone()
            if not marked:
                raise HTTPException(status_code=400, detail="failed to assign closer to schedule row")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.employee_code,
                   e.full_name AS employee_name,
                   au.id AS closer_user_id,
                   au.username AS closer_username,
                   au.full_name AS closer_full_name
            FROM monthly_schedules ms
            JOIN employees e ON e.id = ms.employee_id
            LEFT JOIN arls_users au
                   ON au.tenant_id = ms.tenant_id
                  AND au.employee_id = ms.employee_id
                  AND au.is_active = TRUE
            WHERE ms.tenant_id = %s
              AND ms.site_id = %s
              AND ms.schedule_date = %s
              AND lower(COALESCE(ms.schedule_note, '')) LIKE '%%closer%%'
            ORDER BY e.employee_code
            LIMIT 1
            """,
            (context["tenant_id"], context["site_id"], context["schedule_date"]),
        )
        closer = cur.fetchone()

    return {
        "schedule_id": str(schedule_id),
        "enabled": bool(payload.enabled),
        "site_code": context["site_code"],
        "schedule_date": context["schedule_date"].isoformat(),
        "closer_employee_code": str(closer["employee_code"]) if closer else None,
        "closer_employee_name": str(closer["employee_name"]) if closer else None,
        "closer_user_id": str(closer["closer_user_id"]) if closer and closer.get("closer_user_id") else None,
        "closer_username": str(closer["closer_username"]) if closer and closer.get("closer_username") else None,
        "closer_full_name": str(closer["closer_full_name"]) if closer and closer.get("closer_full_name") else None,
    }


@router.delete("/monthly/{schedule_id}")
def delete_monthly_schedule(
    schedule_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    context = _fetch_schedule_context(conn, schedule_id, target_tenant["id"])
    if not context:
        raise HTTPException(status_code=404, detail="schedule not found")

    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM monthly_schedules WHERE id = %s AND tenant_id = %s",
            (str(schedule_id), target_tenant["id"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="schedule not found")

    _refresh_daily_leader_defaults(
        conn,
        tenant_id=context["tenant_id"],
        site_id=context["site_id"],
        schedule_date=context["schedule_date"],
    )

    return {"deleted": True, "id": str(schedule_id)}


def _parse_ymd_or_400(value: str, *, field_name: str = "date") -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} must be YYYY-MM-DD") from exc


def _resolve_site_or_404(conn, *, tenant_id, site_code: str):
    site = resolve_site(conn, tenant_id=tenant_id, site_code=site_code)
    if not site:
        raise HTTPException(status_code=404, detail="site not found")
    return site


@router.get("/site-shift-policy", response_model=SiteShiftPolicyOut)
def get_site_shift_policy(
    site_code: str = Query(..., min_length=1, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code)
    policy = get_or_create_site_shift_policy(conn, tenant_id=target_tenant["id"], site_id=site["id"])
    return SiteShiftPolicyOut(
        tenant_code=target_tenant["tenant_code"],
        site_code=site["site_code"],
        weekday_headcount=int(policy["weekday_headcount"]),
        weekend_headcount=int(policy["weekend_headcount"]),
        updated_at=policy["updated_at"],
    )


@router.put("/site-shift-policy", response_model=SiteShiftPolicyOut)
def put_site_shift_policy(
    payload: SiteShiftPolicyUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")

    target_tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=payload.site_code)
    policy = upsert_site_shift_policy(
        conn,
        tenant_id=target_tenant["id"],
        site_id=site["id"],
        weekday_headcount=payload.weekday_headcount,
        weekend_headcount=payload.weekend_headcount,
    )
    return SiteShiftPolicyOut(
        tenant_code=target_tenant["tenant_code"],
        site_code=site["site_code"],
        weekday_headcount=int(policy["weekday_headcount"]),
        weekend_headcount=int(policy["weekend_headcount"]),
        updated_at=policy["updated_at"],
    )


@router.get("/apple-daytime-shift", response_model=AppleDaytimeShiftOut)
def get_apple_daytime_shift(
    date: str = Query(..., description="YYYY-MM-DD"),
    site_code: str = Query(..., min_length=1, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if normalize_role(user.get("role")) not in {"dev", "branch_manager", "employee"}:
        raise HTTPException(status_code=403, detail="forbidden")

    work_date = _parse_ymd_or_400(date)
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code)
    policy = get_or_create_site_shift_policy(conn, tenant_id=target_tenant["id"], site_id=site["id"])
    generated = generate_apple_daytime_shift(
        work_date=work_date,
        weekday_headcount=int(policy["weekday_headcount"]),
        weekend_headcount=int(policy["weekend_headcount"]),
    )
    return AppleDaytimeShiftOut(
        tenant_code=target_tenant["tenant_code"],
        site_code=site["site_code"],
        work_date=generated["work_date"],
        is_weekend=bool(generated["is_weekend"]),
        total_headcount=int(generated["total_headcount"]),
        supervisor_count=int(generated["supervisor_count"]),
        guard_count=int(generated["guard_count"]),
        supervisor_time=generated["supervisor_time"],
        guard_time=generated["guard_time"],
        supervisor_hours=float(generated["supervisor_hours"]),
        guard_hours=float(generated["guard_hours"]),
    )


@router.post("/apple-overtime", response_model=AppleOvertimeOut)
def create_apple_daytime_overtime(
    payload: AppleOvertimeCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=payload.site_code)

    actor_role = normalize_role(user.get("role"))
    if actor_role not in {"dev", "branch_manager", "employee"}:
        raise HTTPException(status_code=403, detail="forbidden")

    leader_user_id = payload.leader_user_id or user["id"]
    if actor_role == "employee" and str(leader_user_id) != str(user["id"]):
        raise HTTPException(status_code=403, detail="employee can only submit own leader record")

    row = create_apple_overtime_log(
        conn,
        tenant_id=target_tenant["id"],
        site_id=site["id"],
        work_date=payload.work_date,
        leader_user_id=leader_user_id,
        reason=payload.reason,
    )

    rows = list_apple_overtime_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=payload.work_date,
        site_id=site["id"],
    )
    hydrated = next((item for item in rows if str(item["id"]) == str(row["id"])), None) or row
    return AppleOvertimeOut(
        id=hydrated["id"],
        tenant_code=target_tenant["tenant_code"],
        site_code=hydrated.get("site_code") or site["site_code"],
        work_date=hydrated["work_date"],
        leader_user_id=hydrated["leader_user_id"],
        leader_username=hydrated.get("leader_username"),
        leader_full_name=hydrated.get("leader_full_name"),
        reason=hydrated["reason"],
        hours=float(hydrated["hours"]),
        source=hydrated.get("source") or "APPLE_DAYTIME_OT",
        created_at=hydrated["created_at"],
    )


@router.get("/apple-overtime", response_model=list[AppleOvertimeOut])
def get_apple_daytime_overtime(
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    work_date = _parse_ymd_or_400(date) if date else None
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code) if site_code else None
    rows = list_apple_overtime_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site["id"] if site else None,
    )
    return [
        AppleOvertimeOut(
            id=row["id"],
            tenant_code=row["tenant_code"],
            site_code=row["site_code"],
            work_date=row["work_date"],
            leader_user_id=row["leader_user_id"],
            leader_username=row.get("leader_username"),
            leader_full_name=row.get("leader_full_name"),
            reason=row["reason"],
            hours=float(row["hours"]),
            source=row.get("source") or "APPLE_DAYTIME_OT",
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.post("/late-shifts", response_model=LateShiftOut)
def post_late_shift(
    payload: LateShiftCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=payload.site_code)
    employee = resolve_employee(
        conn,
        tenant_id=target_tenant["id"],
        employee_code=payload.employee_code,
        site_id=site["id"],
    )
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")

    row = create_late_shift_log(
        conn,
        tenant_id=target_tenant["id"],
        site_id=site["id"],
        work_date=payload.work_date,
        employee_id=employee["id"],
        minutes_late=payload.minutes_late,
        note=payload.note,
    )
    return LateShiftOut(
        id=row["id"],
        tenant_code=target_tenant["tenant_code"],
        site_code=site["site_code"],
        work_date=row["work_date"],
        employee_id=employee["id"],
        employee_code=employee["employee_code"],
        employee_name=employee.get("full_name"),
        minutes_late=int(row["minutes_late"]),
        note=row.get("note"),
        created_at=row["created_at"],
    )


@router.get("/late-shifts", response_model=list[LateShiftOut])
def get_late_shifts(
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    work_date = _parse_ymd_or_400(date) if date else None
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code) if site_code else None
    rows = list_late_shift_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site["id"] if site else None,
    )
    if not can_manage_schedule(user["role"]) and user.get("employee_id"):
        own_id = str(user.get("employee_id"))
        rows = [row for row in rows if str(row.get("employee_id")) == own_id]
    return [
        LateShiftOut(
            id=row["id"],
            tenant_code=row["tenant_code"],
            site_code=row["site_code"],
            work_date=row["work_date"],
            employee_id=row["employee_id"],
            employee_code=row["employee_code"],
            employee_name=row.get("employee_name"),
            minutes_late=int(row["minutes_late"]),
            note=row.get("note"),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.delete("/late-shifts/{late_shift_id}")
def remove_late_shift(
    late_shift_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    deleted = delete_late_shift_log(conn, tenant_id=target_tenant["id"], row_id=late_shift_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="late shift log not found")
    return {"deleted": True, "id": str(late_shift_id)}


@router.post("/daily-events", response_model=DailyEventOut)
def post_daily_event(
    payload: DailyEventCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=payload.site_code)
    row = create_daily_event_log(
        conn,
        tenant_id=target_tenant["id"],
        site_id=site["id"],
        work_date=payload.work_date,
        event_type=payload.type,
        description=payload.description,
    )
    return DailyEventOut(
        id=row["id"],
        tenant_code=target_tenant["tenant_code"],
        site_code=site["site_code"],
        work_date=row["work_date"],
        type=row["type"],
        description=row["description"],
        created_at=row["created_at"],
    )


@router.get("/daily-events", response_model=list[DailyEventOut])
def get_daily_events(
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    work_date = _parse_ymd_or_400(date) if date else None
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code) if site_code else None
    rows = list_daily_event_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site["id"] if site else None,
    )
    return [
        DailyEventOut(
            id=row["id"],
            tenant_code=row["tenant_code"],
            site_code=row["site_code"],
            work_date=row["work_date"],
            type=row["type"],
            description=row["description"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.delete("/daily-events/{event_id}")
def remove_daily_event(
    event_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    deleted = delete_daily_event_log(conn, tenant_id=target_tenant["id"], row_id=event_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="daily event not found")
    return {"deleted": True, "id": str(event_id)}


@router.post("/support-assignments", response_model=SupportAssignmentOut)
def post_support_assignment(
    payload: SupportAssignmentCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, payload.tenant_code)
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=payload.site_code)
    employee_id = None
    if payload.employee_code:
        employee = resolve_employee(
            conn,
            tenant_id=target_tenant["id"],
            employee_code=payload.employee_code,
            site_id=site["id"],
        )
        if not employee:
            raise HTTPException(status_code=404, detail="employee not found")
        employee_id = employee["id"]

    row, _created = upsert_support_assignment(
        conn,
        tenant_id=target_tenant["id"],
        site_id=site["id"],
        work_date=payload.work_date,
        worker_type=payload.worker_type,
        name=payload.name,
        source=payload.source,
        employee_id=employee_id,
    )
    if not row:
        raise HTTPException(status_code=500, detail="failed to save support assignment")
    return SupportAssignmentOut(
        id=row["id"],
        tenant_code=row["tenant_code"],
        site_code=row["site_code"],
        work_date=row["work_date"],
        worker_type=row["worker_type"],
        employee_id=row.get("employee_id"),
        employee_code=row.get("employee_code"),
        employee_name=row.get("employee_name"),
        name=row["name"],
        source=row["source"],
        created_at=row["created_at"],
    )


@router.get("/support-assignments", response_model=list[SupportAssignmentOut])
def get_support_assignments(
    date: str | None = Query(default=None, description="YYYY-MM-DD"),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    work_date = _parse_ymd_or_400(date) if date else None
    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code) if site_code else None
    rows = list_support_assignments(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site["id"] if site else None,
    )
    return [
        SupportAssignmentOut(
            id=row["id"],
            tenant_code=row["tenant_code"],
            site_code=row["site_code"],
            work_date=row["work_date"],
            worker_type=row["worker_type"],
            employee_id=row.get("employee_id"),
            employee_code=row.get("employee_code"),
            employee_name=row.get("employee_name"),
            name=row["name"],
            source=row["source"],
            created_at=row["created_at"],
        )
        for row in rows
    ]


@router.delete("/support-assignments/{assignment_id}")
def remove_support_assignment(
    assignment_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_schedule(user["role"]):
        raise HTTPException(status_code=403, detail="forbidden")
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    deleted = delete_support_assignment(conn, tenant_id=target_tenant["id"], row_id=assignment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="support assignment not found")
    return {"deleted": True, "id": str(assignment_id)}


@router.get("/duty-log", response_model=DutyLogOut)
def get_duty_log(
    month: str = Query(..., description="YYYY-MM"),
    employee_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)
    actor_role = normalize_role(user.get("role"))
    if actor_role == "employee":
        if not user.get("employee_id"):
            raise HTTPException(status_code=400, detail="employee account is not linked")
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_code
                FROM employees
                WHERE id = %s
                  AND tenant_id = %s
                LIMIT 1
                """,
                (user["employee_id"], target_tenant["id"]),
            )
            own = cur.fetchone()
        if not own:
            raise HTTPException(status_code=404, detail="employee not found")
        target_employee_code = own["employee_code"]
    else:
        target_employee_code = (employee_code or "").strip()
        if not target_employee_code:
            raise HTTPException(status_code=400, detail="employee_code is required")

    employee = resolve_employee(
        conn,
        tenant_id=target_tenant["id"],
        employee_code=target_employee_code,
    )
    if not employee:
        raise HTTPException(status_code=404, detail="employee not found")

    rows = build_duty_log(
        conn,
        tenant_id=target_tenant["id"],
        employee_id=employee["id"],
        month=month,
    )
    return DutyLogOut(
        tenant_code=target_tenant["tenant_code"],
        employee_code=employee["employee_code"],
        month=month,
        rows=[
            DutyLogRowOut(
                work_date=row["work_date"],
                mark=row["mark"],
                shift_type=row.get("shift_type"),
                leave_type=row.get("leave_type"),
                source=row.get("source"),
            )
            for row in rows
        ],
    )


@router.get("/date-details")
def get_schedule_date_details(
    date: str = Query(..., description="YYYY-MM-DD"),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    work_date = _parse_ymd_or_400(date)
    target_tenant = _resolve_target_tenant(conn, user, tenant_code)

    site = _resolve_site_or_404(conn, tenant_id=target_tenant["id"], site_code=site_code) if site_code else None
    site_id = site["id"] if site else None

    apple_ot_rows = list_apple_overtime_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site_id,
    )
    late_rows = list_late_shift_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site_id,
    )
    support_rows = list_support_assignments(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site_id,
    )
    event_rows = list_daily_event_logs(
        conn,
        tenant_id=target_tenant["id"],
        work_date=work_date,
        site_id=site_id,
    )

    daytime_payload: dict[str, Any] | None = None
    policy_payload: dict[str, Any] | None = None
    if site:
        policy = get_or_create_site_shift_policy(conn, tenant_id=target_tenant["id"], site_id=site["id"])
        generated = generate_apple_daytime_shift(
            work_date=work_date,
            weekday_headcount=int(policy["weekday_headcount"]),
            weekend_headcount=int(policy["weekend_headcount"]),
        )
        policy_payload = {
            "tenant_code": target_tenant["tenant_code"],
            "site_code": site["site_code"],
            "weekday_headcount": int(policy["weekday_headcount"]),
            "weekend_headcount": int(policy["weekend_headcount"]),
            "updated_at": policy["updated_at"],
        }
        daytime_payload = {
            "tenant_code": target_tenant["tenant_code"],
            "site_code": site["site_code"],
            **generated,
        }

    return {
        "tenant_code": target_tenant["tenant_code"],
        "work_date": work_date.isoformat(),
        "site_code": site["site_code"] if site else None,
        "site_policy": policy_payload,
        "daytime_shift": daytime_payload,
        "apple_overtime": [dict(row) for row in apple_ot_rows],
        "late_shift": [dict(row) for row in late_rows],
        "support_assignment": [dict(row) for row in support_rows],
        "daily_events": [dict(row) for row in event_rows],
    }
