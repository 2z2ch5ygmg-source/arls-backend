from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg.errors import ForeignKeyViolation

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import EmployeeCreate, EmployeeDutyRoleUpdate, EmployeeOut, EmployeeUpdate
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role

router = APIRouter(prefix="/employees", tags=["employees"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)


def _raise_api_error(status_code: int, code: str, message: str):
    raise HTTPException(status_code=status_code, detail={"error": code, "message": message})


def _normalize_tenant_code(value: str | None) -> str:
    return str(value or "").strip().lower()


def _validate_target_tenant_row(row: dict | None):
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "TENANT_NOT_FOUND", "tenant not found")
    if row.get("is_deleted") or row.get("is_active") is False:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "TENANT_DISABLED", "tenant disabled")


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


def _resolve_target_tenant(conn, user, tenant_code: str | None, tenant_id: str | None = None):
    own_tenant_id = str(user["tenant_id"])
    own_tenant_code = str(user.get("tenant_code") or "").strip()
    own_tenant_code_normalized = _normalize_tenant_code(own_tenant_code)
    requested_tenant_id = str(tenant_id or "").strip()
    requested_tenant_code_raw = str(tenant_code or "").strip()
    requested_tenant_code_normalized = _normalize_tenant_code(requested_tenant_code_raw)
    actor_role = normalize_role(user["role"])

    logger.info(
        "employees.resolve_tenant start role=%s tenant_id_raw=%s tenant_code_raw=%s tenant_code_normalized=%s",
        actor_role,
        requested_tenant_id,
        requested_tenant_code_raw,
        requested_tenant_code_normalized,
    )

    if actor_role != ROLE_DEV:
        if requested_tenant_id and requested_tenant_id != own_tenant_id:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
        if requested_tenant_code_normalized and requested_tenant_code_normalized != own_tenant_code_normalized:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    if requested_tenant_id:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tenant_code,
                       COALESCE(is_active, TRUE) AS is_active,
                       COALESCE(is_deleted, FALSE) AS is_deleted
                FROM tenants
                WHERE id = %s
                LIMIT 1
                """,
                (requested_tenant_id,),
            )
            row = cur.fetchone()
        _validate_target_tenant_row(row)
        logger.info(
            "employees.resolve_tenant resolved tenant_id=%s tenant_code=%s by=tenant_id",
            row["id"],
            row["tenant_code"],
        )
        return row

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
    _validate_target_tenant_row(row)
    logger.info(
        "employees.resolve_tenant resolved tenant_id=%s tenant_code=%s by=tenant_code(raw=%s normalized=%s)",
        row["id"],
        row["tenant_code"],
        requested_tenant_code_raw,
        requested_tenant_code_normalized,
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
                   s.site_code, c.company_code, UPPER(COALESCE(e.duty_role, 'GUARD')) AS duty_role,
                   u.id AS user_id
            FROM employees e
            JOIN sites s ON s.id = e.site_id
            JOIN companies c ON c.id = s.company_id
            LEFT JOIN LATERAL (
                SELECT au.id
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
        return [EmployeeOut(**r) for r in cur.fetchall()]


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

    tenant = _resolve_target_tenant(conn, user, tenant_code, str(payload.tenant_id or ""))
    tenant_id = tenant["id"]

    if actor_role == ROLE_BRANCH_MANAGER:
        scoped_site_id = _branch_manager_site_id(user)
        if payload.site_id and str(payload.site_id) != scoped_site_id:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
        company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
            conn,
            tenant_id,
            scoped_site_id,
        )
        requested_site_code = str(payload.site_code or "").strip().upper()
        if requested_site_code and requested_site_code != resolved_site_code:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
        requested_company_code = str(payload.company_code or "").strip().upper()
        if requested_company_code and requested_company_code != resolved_company_code:
            _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "forbidden")
    else:
        if payload.site_id:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids_by_site(
                conn, tenant_id, payload.site_id
            )
        else:
            company_id, site_id, resolved_company_code, resolved_site_code = _lookup_relation_ids(
                conn, tenant_id, payload.company_code, payload.site_code
            )

    employee_id = uuid.uuid4()
    created = None
    for _ in range(8):
        next_seq = _reserve_next_employee_sequence(conn, tenant_id, site_id)
        generated_employee_code = _format_employee_code(resolved_site_code, next_seq)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees
                    (id, tenant_id, company_id, site_id, sequence_no, employee_code, full_name, phone, duty_role)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id, employee_code, sequence_no, full_name, phone, %s AS site_code, %s AS company_code,
                          UPPER(COALESCE(duty_role, 'GUARD')) AS duty_role, NULL::uuid AS user_id
                """,
                (
                    employee_id,
                    tenant_id,
                    company_id,
                    site_id,
                    next_seq,
                    generated_employee_code,
                    payload.full_name,
                    payload.phone,
                    payload.duty_role or "GUARD",
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

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, employee_code, sequence_no, full_name, phone, duty_role, site_id
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
                phone = %s
            WHERE id = %s
              AND tenant_id = %s
            RETURNING id, employee_code, sequence_no, full_name, phone, duty_role, site_id
            """,
            (payload.full_name, payload.phone, str(employee_id), tenant_id),
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
            SELECT id
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
        duty_role=str(updated.get("duty_role") or "GUARD").upper(),
        user_id=user_row["id"] if user_row else None,
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


@router.patch("/{employee_id}/duty-role", response_model=EmployeeOut)
def update_employee_duty_role(
    employee_id: uuid.UUID,
    payload: EmployeeDutyRoleUpdate,
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
            SELECT id, employee_code, sequence_no, full_name, phone, duty_role, site_id
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
            SET duty_role = %s
            WHERE id = %s
              AND tenant_id = %s
            RETURNING id, employee_code, sequence_no, full_name, phone, duty_role, site_id
            """,
            (payload.duty_role, str(employee_id), tenant_id),
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
            raise HTTPException(status_code=500, detail="site/company not found")

        cur.execute(
            """
            SELECT id
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
        duty_role=str(updated.get("duty_role") or "GUARD").upper(),
        user_id=user_row["id"] if user_row else None,
    )
