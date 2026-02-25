from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg.errors import ForeignKeyViolation
import requests

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import EmployeeCreate, EmployeeOut, EmployeeUpdate
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, ROLE_EMPLOYEE, normalize_role, normalize_user_role
from ...utils.tenant_context import canonical_tenant_identifier, enforce_staff_site_scope, resolve_scoped_tenant

router = APIRouter(prefix="/employees", tags=["employees"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)

SOC_EMPLOYEE_ROLE_MAP: dict[str, str] = {
    "OFFICER": "Officer",
    "VICE_SUPERVISOR": "Vice_Supervisor",
    "SUPERVISOR": "Supervisor",
    "HQ_ADMIN": "HQ_Admin",
    "DEVELOPER": "Developer",
}


def _raise_api_error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "message": message})


def _normalize_tenant_code(value: str | None) -> str:
    return canonical_tenant_identifier(value)


def _lookup_relation_ids(conn, tenant_id, company_code, site_code):
    company_code_text = str(company_code or "").strip()
    site_code_text = str(site_code or "").strip()
    if not company_code_text:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_INPUT", "company_code is required")
    if not site_code_text:
        _raise_api_error(status.HTTP_400_BAD_REQUEST, "INVALID_INPUT", "site_code is required")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id AS company_id, c.company_code
            FROM companies c
            WHERE c.tenant_id = %s
              AND upper(c.company_code) = upper(%s)
            LIMIT 1
            """,
            (tenant_id, company_code_text),
        )
        company = cur.fetchone()
        if not company:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "COMPANY_NOT_FOUND", "company not found")

        cur.execute(
            """
            SELECT s.id AS site_id, s.site_code
            FROM sites s
            WHERE s.company_id = %s
              AND upper(s.site_code) = upper(%s)
            LIMIT 1
            """,
            (company["company_id"], site_code_text),
        )
        site = cur.fetchone()
    if not site:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return company["company_id"], site["site_id"], company["company_code"], site["site_code"]


def _lookup_relation_ids_by_site(conn, tenant_id, site_id):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.id AS site_id, s.site_code, c.id AS company_id, c.company_code
            FROM sites s
            JOIN companies c ON c.id = s.company_id
            WHERE s.id = %s
              AND c.tenant_id = %s
            LIMIT 1
            """,
            (site_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return row["company_id"], row["site_id"], row["company_code"], row["site_code"]


def _branch_manager_site_id(user: dict) -> str:
    site_id = str(user.get("site_id") or "").strip()
    if not site_id:
        _raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "SITE_SCOPE_REQUIRED",
            "branch manager site scope is required",
        )
    return site_id


def _assert_branch_manager_site_scope(user: dict, target_site_id: str | None):
    actor_role = normalize_role(user.get("role"))
    if actor_role != ROLE_BRANCH_MANAGER:
        return
    manager_site_id = _branch_manager_site_id(user)
    if str(target_site_id or "") != manager_site_id:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")


def _reserve_next_employee_sequence(conn, tenant_id, site_id) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sites
            SET employee_sequence_seed = COALESCE(employee_sequence_seed, 0) + 1
            WHERE id = %s
              AND tenant_id = %s
            RETURNING employee_sequence_seed
            """,
            (site_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "SITE_NOT_FOUND", "site not found")
    return max(1, int((row or {}).get("employee_sequence_seed") or 1))


def _reset_site_sequence_if_empty(conn, tenant_id, site_id):
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
        remaining = int((row or {}).get("cnt") or 0)
        if remaining == 0:
            cur.execute(
                """
                UPDATE sites
                SET employee_sequence_seed = 0
                WHERE id = %s
                  AND tenant_id = %s
                """,
                (site_id, tenant_id),
            )


def _format_employee_code(site_code: str, sequence_no: int) -> str:
    return f"{str(site_code or '').strip().upper()}-{int(sequence_no):03d}"


def _to_soc_employee_role(user_role: str | None) -> str:
    normalized = normalize_user_role(user_role)
    if normalized in {"vice_supervisor", "supervisor", "hq_admin", "developer"}:
        return "L2"
    return "L1"


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_soc_role(value: str | None, *, required: bool) -> str | None:
    normalized = _normalize_optional_text(value)
    if not normalized:
        if required:
            _raise_api_error(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", "soc_role is required")
        return None

    key = normalized.replace("-", "_").replace(" ", "_").upper()
    mapped = SOC_EMPLOYEE_ROLE_MAP.get(key)
    if not mapped:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "soc_role must be one of: Officer, Vice_Supervisor, Supervisor, HQ_Admin, Developer",
        )
    return mapped


def _to_iso_date(value) -> str | None:
    if value is None:
        return None
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    text = str(value).strip()
    return text or None


def _post_employee_sync_to_soc(
    *,
    tenant_code: str,
    site_code: str,
    employee_uuid: str,
    employee_code: str,
    full_name: str,
    phone: str | None,
    user_role: str | None,
    birth_date=None,
    hire_date=None,
    guard_training_cert_no: str | None = None,
    note: str | None = None,
    soc_login_id: str | None = None,
    soc_temp_password: str | None = None,
    soc_role: str | None = None,
):
    url = str(settings.soc_employee_sync_url or "").strip()
    if not url:
        logger.info("employees.soc_sync skipped: SOC_EMPLOYEE_SYNC_URL is empty")
        return

    payload = {
        "event_type": "EMPLOYEE_CREATED",
        "tenant_id": _normalize_tenant_code(tenant_code),
        "site_code": str(site_code or "").strip(),
        "employee": {
            "employee_uuid": str(employee_uuid or "").strip(),
            "employee_code": str(employee_code or "").strip(),
            "name": str(full_name or "").strip(),
            "phone": phone,
            "role": _to_soc_employee_role(user_role),
            "user_role": normalize_user_role(user_role) if user_role else None,
            "birth_date": _to_iso_date(birth_date),
            "hire_date": _to_iso_date(hire_date),
            "guard_training_cert_no": _normalize_optional_text(guard_training_cert_no),
            "note": _normalize_optional_text(note),
            "soc_login_id": _normalize_optional_text(soc_login_id),
            "soc_temp_password": _normalize_optional_text(soc_temp_password),
            "soc_role": _normalize_optional_text(soc_role),
        },
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code >= 400:
            logger.warning(
                "employees.soc_sync failed status=%s employee_uuid=%s employee_code=%s body=%s",
                response.status_code,
                payload["employee"]["employee_uuid"],
                payload["employee"]["employee_code"],
                (response.text or "")[:400],
            )
        else:
            logger.info(
                "employees.soc_sync success status=%s employee_uuid=%s employee_code=%s",
                response.status_code,
                payload["employee"]["employee_uuid"],
                payload["employee"]["employee_code"],
            )
    except Exception:
        logger.exception(
            "employees.soc_sync exception employee_uuid=%s employee_code=%s",
            payload["employee"]["employee_uuid"],
            payload["employee"]["employee_code"],
        )


def _resolve_target_tenant(conn, user, tenant_code: str | None, tenant_id: str | None = None):
    row = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        body_tenant_id=tenant_id,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    logger.info(
        "employees.resolve_tenant resolved role=%s tenant_id=%s tenant_code=%s",
        normalize_role(user["role"]),
        row.get("id"),
        row.get("tenant_code"),
    )
    return row


@router.get("", response_model=list[EmployeeOut])
def list_employees(
    site_id: str | None = None,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    scoped_site_id = None
    if actor_role == ROLE_BRANCH_MANAGER:
        scoped_site_id = _branch_manager_site_id(user)
        if site_id and str(site_id) != scoped_site_id:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
    elif actor_role == ROLE_EMPLOYEE:
        staff_scope = enforce_staff_site_scope(user, request_site_id=site_id)
        scoped_site_id = str((staff_scope or {}).get("site_id") or "").strip() or None
    effective_site_id = site_id or scoped_site_id

    params = [tenant["id"]]
    site_filter = ""
    if effective_site_id:
        site_filter = "AND s.id = %s"
        params.append(effective_site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id, e.employee_code, e.sequence_no, e.full_name, e.phone,
                   s.site_code, c.company_code,
                   e.birth_date, e.hire_date, e.guard_training_cert_no, e.note, e.soc_login_id, e.soc_role,
                   u.id AS user_id, u.role AS user_role
            FROM employees e
            JOIN sites s ON s.id = e.site_id
            JOIN companies c ON c.id = s.company_id
            LEFT JOIN LATERAL (
                SELECT au.id, au.role
                FROM arls_users au
                WHERE au.tenant_id = e.tenant_id
                  AND au.employee_id = e.id
                  AND au.is_active = TRUE
                ORDER BY au.updated_at DESC NULLS LAST, au.created_at DESC NULLS LAST
                LIMIT 1
            ) u ON TRUE
            WHERE e.tenant_id = %s
              {site_filter}
            ORDER BY e.employee_code
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    return [
        EmployeeOut(
            **{
                **row,
                "user_role": normalize_user_role(row.get("user_role")) if row.get("user_role") else None,
            }
        )
        for row in rows
    ]


@router.post("", response_model=EmployeeOut)
def create_employee(
    payload: EmployeeCreate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    requested_tenant_id = "" if actor_role == ROLE_BRANCH_MANAGER else str(payload.tenant_id or "")
    tenant = _resolve_target_tenant(conn, user, tenant_code, requested_tenant_id)
    tenant_id = tenant["id"]

    if actor_role == ROLE_BRANCH_MANAGER:
        scoped_site_id = _branch_manager_site_id(user)
        # 지점관리자는 tenant/site 스코프를 세션에서 강제 적용한다.
        # 요청 본문의 tenant/site/company 값은 신뢰하지 않는다.
        company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
            conn,
            tenant_id,
            scoped_site_id,
        )
    else:
        if payload.site_id:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
                conn, tenant_id, payload.site_id
            )
        else:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids(
                conn, tenant_id, payload.company_code, payload.site_code
            )

    normalized_soc_role = _normalize_soc_role(payload.soc_role, required=True)

    employee_id = uuid.uuid4()
    employee_uuid = str(uuid.uuid4())
    duty_role_value = "GUARD"
    created = None
    for _ in range(8):
        next_seq = _reserve_next_employee_sequence(conn, tenant_id, site_id)
        generated_employee_code = _format_employee_code(resolved_site_code, next_seq)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees
                    (
                      id, employee_uuid, tenant_id, company_id, site_id, sequence_no, employee_code, full_name, phone,
                      duty_role, birth_date, hire_date, guard_training_cert_no, note, soc_login_id, soc_role
                    )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id, employee_code, sequence_no, full_name, phone, %s AS site_code, %s AS company_code,
                          NULL::uuid AS user_id, NULL::text AS user_role,
                          birth_date, hire_date, guard_training_cert_no, note, soc_login_id, soc_role
                """,
                (
                    employee_id,
                    employee_uuid,
                    tenant_id,
                    company_id,
                    site_id,
                    next_seq,
                    generated_employee_code,
                    payload.full_name,
                    payload.phone,
                    duty_role_value,
                    payload.birth_date,
                    payload.hire_date,
                    _normalize_optional_text(payload.guard_training_cert_no),
                    _normalize_optional_text(payload.note),
                    _normalize_optional_text(payload.soc_login_id),
                    normalized_soc_role,
                    resolved_site_code,
                    resolved_company_code,
                ),
            )
            created = cur.fetchone()
        if created:
            break
        employee_id = uuid.uuid4()

    if not created:
        _raise_api_error(
            status.HTTP_409_CONFLICT,
            "EMPLOYEE_CODE_CONFLICT",
            "failed to allocate employee_code",
        )
    _post_employee_sync_to_soc(
        tenant_code=str(tenant.get("tenant_code") or ""),
        site_code=resolved_site_code,
        employee_uuid=employee_uuid,
        employee_code=str(created.get("employee_code") or ""),
        full_name=str(created.get("full_name") or payload.full_name or ""),
        phone=created.get("phone"),
        user_role=created.get("user_role"),
        birth_date=created.get("birth_date"),
        hire_date=created.get("hire_date"),
        guard_training_cert_no=created.get("guard_training_cert_no"),
        note=created.get("note"),
        soc_login_id=created.get("soc_login_id"),
        soc_temp_password=_normalize_optional_text(payload.soc_temp_password),
        soc_role=normalized_soc_role,
    )
    return EmployeeOut(**created)


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if normalize_role(user["role"]) not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = tenant["id"]

    normalized_soc_role = _normalize_soc_role(payload.soc_role, required=False)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, sequence_no, full_name, phone, site_id,
                   birth_date, hire_date, guard_training_cert_no, note, soc_login_id, soc_role
            FROM employees
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (str(employee_id), tenant_id),
        )
        current = cur.fetchone()
        if not current:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "EMPLOYEE_NOT_FOUND", "employee not found")

        _assert_branch_manager_site_scope(user, current["site_id"])

        cur.execute(
            """
            UPDATE employees
            SET full_name = %s,
                phone = %s,
                birth_date = %s,
                hire_date = %s,
                guard_training_cert_no = %s,
                note = %s,
                soc_login_id = %s,
                soc_role = %s
            WHERE id = %s
              AND tenant_id = %s
            RETURNING id, employee_code, sequence_no, full_name, phone, site_id,
                      birth_date, hire_date, guard_training_cert_no, note, soc_login_id, soc_role
            """,
            (
                payload.full_name,
                payload.phone,
                payload.birth_date,
                payload.hire_date,
                _normalize_optional_text(payload.guard_training_cert_no),
                _normalize_optional_text(payload.note),
                _normalize_optional_text(payload.soc_login_id),
                normalized_soc_role,
                str(employee_id),
                tenant_id,
            ),
        )
        updated = cur.fetchone()

        cur.execute(
            """
            SELECT s.site_code, c.company_code
            FROM sites s
            JOIN companies c ON c.id = s.company_id
            WHERE s.id = %s
            LIMIT 1
            """,
            (updated["site_id"],),
        )
        site_company = cur.fetchone()
        if not site_company:
            _raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL", "site/company not found")

        cur.execute(
            """
            SELECT id, role
            FROM arls_users
            WHERE tenant_id = %s
              AND employee_id = %s
              AND is_active = TRUE
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """,
            (tenant_id, employee_id),
        )
        user_row = cur.fetchone()

    return EmployeeOut(
        id=updated["id"],
        employee_code=updated["employee_code"],
        sequence_no=updated.get("sequence_no"),
        full_name=updated["full_name"],
        phone=updated["phone"],
        site_code=site_company["site_code"],
        company_code=site_company["company_code"],
        user_id=user_row["id"] if user_row else None,
        user_role=normalize_user_role(user_row["role"]) if user_row and user_row.get("role") else None,
        birth_date=updated.get("birth_date"),
        hire_date=updated.get("hire_date"),
        guard_training_cert_no=updated.get("guard_training_cert_no"),
        note=updated.get("note"),
        soc_login_id=updated.get("soc_login_id"),
        soc_role=updated.get("soc_role"),
    )


@router.delete("/{employee_id}")
def delete_employee(
    employee_id: uuid.UUID,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if normalize_role(user["role"]) not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")

    tenant = _resolve_target_tenant(conn, user, tenant_code)
    tenant_id = tenant["id"]

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, site_id
            FROM employees
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (str(employee_id), tenant_id),
        )
        target = cur.fetchone()
        if not target:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "EMPLOYEE_NOT_FOUND", "employee not found")
        _assert_branch_manager_site_scope(user, target["site_id"])

        cur.execute(
            """
            UPDATE arls_users
            SET employee_id = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND employee_id = %s
            """,
            (tenant_id, str(employee_id)),
        )
        try:
            cur.execute(
                """
                DELETE FROM employees
                WHERE id = %s
                  AND tenant_id = %s
                """,
                (str(employee_id), tenant_id),
            )
        except ForeignKeyViolation:
            _raise_api_error(
                status.HTTP_409_CONFLICT,
                "EMPLOYEE_HAS_REFERENCES",
                "employee has references",
            )
        _reset_site_sequence_if_empty(conn, tenant_id, target["site_id"])

    return {"success": True, "employee_code": target["employee_code"]}
