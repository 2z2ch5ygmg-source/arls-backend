from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_DEV, normalize_user_role
from ...utils.schema_introspection import table_column_exists

router = APIRouter(prefix="/dev", tags=["dev-scope"], dependencies=[Depends(apply_rate_limit)])


def _table_column_exists(conn, table_name: str, column_name: str) -> bool:
    return table_column_exists(conn, table_name, column_name)


def _build_exact_match_clause(column_sql: str, value: str, params: list) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    variants = [normalized]
    upper_variant = normalized.upper()
    if upper_variant not in variants:
        variants.append(upper_variant)
    lower_variant = normalized.lower()
    if lower_variant not in variants:
        variants.append(lower_variant)
    if len(variants) == 1:
        params.append(variants[0])
        return f"{column_sql} = %s"
    params.extend(variants)
    return f"{column_sql} IN ({', '.join(['%s'] * len(variants))})"


@router.get("/sites")
def list_dev_sites(
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    tenant_code: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=1000, ge=1, le=10000),
    conn=Depends(get_db_conn),
    _user=Depends(require_roles(ROLE_DEV)),
):
    has_site_active = _table_column_exists(conn, "sites", "is_active")
    has_site_deleted = _table_column_exists(conn, "sites", "is_deleted")
    has_site_place_id = _table_column_exists(conn, "sites", "place_id")
    has_tenant_active = _table_column_exists(conn, "tenants", "is_active")
    has_tenant_deleted = _table_column_exists(conn, "tenants", "is_deleted")

    clauses: list[str] = []
    params: list = []

    normalized_tenant_code = str(tenant_code or "").strip()
    tenant_clause = _build_exact_match_clause("t.tenant_code", normalized_tenant_code, params)
    if tenant_clause:
        clauses.append(tenant_clause)

    if has_site_deleted and not include_deleted:
        clauses.append("COALESCE(s.is_deleted, FALSE) = FALSE")
    if has_tenant_deleted and not include_deleted:
        clauses.append("COALESCE(t.is_deleted, FALSE) = FALSE")

    if has_site_active and not include_inactive:
        clauses.append("COALESCE(s.is_active, TRUE) = TRUE")
    if has_tenant_active and not include_inactive:
        clauses.append("COALESCE(t.is_active, TRUE) = TRUE")

    keyword = str(q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            """
            (
                t.tenant_code ILIKE %s
                OR COALESCE(t.tenant_name, '') ILIKE %s
                OR s.site_code ILIKE %s
                OR s.site_name ILIKE %s
                OR COALESCE(s.address, '') ILIKE %s
                OR COALESCE(c.company_code, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like, like])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    place_id_sql = "COALESCE(s.place_id, '') AS place_id" if has_site_place_id else "''::text AS place_id"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT s.id, s.tenant_id, t.tenant_code, t.tenant_name,
                   s.site_code, s.site_name,
                   COALESCE(s.address, '') AS address,
                   {place_id_sql},
                   s.latitude, s.longitude, s.radius_meters,
                   COALESCE(s.is_active, TRUE) AS is_active,
                   COALESCE(c.company_code, '') AS company_code
            FROM sites s
            JOIN tenants t ON t.id = s.tenant_id
            LEFT JOIN companies c ON c.id = s.company_id
            {where_sql}
            ORDER BY t.tenant_code, s.site_code
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []
    return rows


@router.get("/employees")
def list_dev_employees(
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    tenant_code: str | None = Query(default=None, max_length=64),
    site_code: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, min_length=1, max_length=120),
    limit: int = Query(default=1000, ge=1, le=10000),
    include_account: bool = Query(default=False),
    conn=Depends(get_db_conn),
    _user=Depends(require_roles(ROLE_DEV)),
):
    has_employee_active = _table_column_exists(conn, "employees", "is_active")
    has_employee_deleted = _table_column_exists(conn, "employees", "is_deleted")
    has_site_active = _table_column_exists(conn, "sites", "is_active")
    has_site_deleted = _table_column_exists(conn, "sites", "is_deleted")
    has_tenant_active = _table_column_exists(conn, "tenants", "is_active")
    has_tenant_deleted = _table_column_exists(conn, "tenants", "is_deleted")

    clauses: list[str] = []
    params: list = []

    normalized_tenant_code = str(tenant_code or "").strip()
    tenant_clause = _build_exact_match_clause("t.tenant_code", normalized_tenant_code, params)
    if tenant_clause:
        clauses.append(tenant_clause)

    normalized_site_code = str(site_code or "").strip()
    if normalized_site_code and normalized_site_code.lower() != "all":
        site_clause = _build_exact_match_clause("s.site_code", normalized_site_code, params)
        if site_clause:
            clauses.append(site_clause)

    if has_employee_deleted and not include_deleted:
        clauses.append("COALESCE(e.is_deleted, FALSE) = FALSE")
    if has_site_deleted and not include_deleted:
        clauses.append("COALESCE(s.is_deleted, FALSE) = FALSE")
    if has_tenant_deleted and not include_deleted:
        clauses.append("COALESCE(t.is_deleted, FALSE) = FALSE")

    if has_employee_active and not include_inactive:
        clauses.append("COALESCE(e.is_active, TRUE) = TRUE")
    if has_site_active and not include_inactive:
        clauses.append("COALESCE(s.is_active, TRUE) = TRUE")
    if has_tenant_active and not include_inactive:
        clauses.append("COALESCE(t.is_active, TRUE) = TRUE")

    keyword = str(q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append(
            """
            (
                t.tenant_code ILIKE %s
                OR COALESCE(t.tenant_name, '') ILIKE %s
                OR e.employee_code ILIKE %s
                OR COALESCE(e.full_name, '') ILIKE %s
                OR COALESCE(e.phone, '') ILIKE %s
                OR COALESCE(s.site_code, '') ILIKE %s
                OR COALESCE(s.site_name, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like, like, like, like])

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    account_join_sql = ""
    account_select_sql = "NULL::uuid AS user_id, NULL::text AS user_role"
    if include_account:
        account_select_sql = "u.id AS user_id, u.role AS user_role"
        account_join_sql = """
            LEFT JOIN (
                SELECT DISTINCT ON (au.tenant_id, au.employee_id)
                       au.tenant_id, au.employee_id, au.id, au.role
                FROM arls_users au
                WHERE COALESCE(au.is_active, TRUE) = TRUE
                  AND COALESCE(au.is_deleted, FALSE) = FALSE
                ORDER BY au.tenant_id, au.employee_id, au.updated_at DESC NULLS LAST, au.created_at DESC NULLS LAST
            ) u
              ON u.tenant_id = e.tenant_id
             AND u.employee_id = e.id
        """

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id, e.tenant_id, t.tenant_code, t.tenant_name,
                   e.employee_code, e.management_no_str, e.sequence_no,
                   e.full_name, e.phone,
                   s.site_code, s.site_name,
                   COALESCE(c.company_code, '') AS company_code,
                   e.birth_date, e.address, e.hire_date, e.leave_date,
                   e.guard_training_cert_no, e.note,
                   e.roster_docx_attachment_id, e.photo_attachment_id,
                   e.soc_login_id, e.soc_role,
                   {account_select_sql}
            FROM employees e
            JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = s.company_id
            JOIN tenants t ON t.id = e.tenant_id
            {account_join_sql}
            {where_sql}
            ORDER BY t.tenant_code, e.employee_code
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []

    normalized_rows: list[dict] = []
    for row in rows:
        current = dict(row)
        if current.get("user_role"):
            current["user_role"] = normalize_user_role(current.get("user_role"))
        normalized_rows.append(current)
    return normalized_rows
