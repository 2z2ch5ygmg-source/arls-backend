from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg import sql

from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import normalize_tenant_identifier, resolve_scoped_tenant

router = APIRouter(
    prefix="/admin/tenants",
    tags=["admin-tenants"],
    dependencies=[Depends(apply_rate_limit)],
)


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return bool(cur.fetchone())


def _delete_tenant_rows(conn, table_name: str, tenant_id) -> int:
    if not _table_exists(conn, table_name):
        return 0
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("DELETE FROM {} WHERE tenant_id = %s").format(sql.Identifier(table_name)),
            (tenant_id,),
        )
        return int(cur.rowcount or 0)


def _clear_user_employee_links(conn, tenant_id) -> int:
    if not _table_exists(conn, "arls_users"):
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET employee_id = NULL,
                site_id = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND (employee_id IS NOT NULL OR site_id IS NOT NULL)
            """,
            (tenant_id,),
        )
        return int(cur.rowcount or 0)


@router.post("/reset")
def reset_tenant_hr_data(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(ROLE_DEV, ROLE_BRANCH_MANAGER)),
):
    tenant_header = normalize_tenant_identifier(x_tenant_id)
    if not tenant_header:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
        )

    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=tenant_header,
        require_dev_context=True,
    )
    tenant_id = scoped_tenant.get("id")
    tenant_code = normalize_tenant_identifier(scoped_tenant.get("tenant_code")) or tenant_header
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )

    deleted = {
        "user_links_cleared": _clear_user_employee_links(conn, tenant_id),
        "employees": _delete_tenant_rows(conn, "employees", tenant_id),
        "sites_match_index": _delete_tenant_rows(conn, "sites_match_index", tenant_id),
        "sites": _delete_tenant_rows(conn, "sites", tenant_id),
    }

    if _table_exists(conn, "integration_audit_logs"):
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO integration_audit_logs (
                    id, tenant_id, action_type, source, actor_user_id, actor_role,
                    target_type, target_id, detail, created_at
                )
                VALUES (
                    %s, %s, %s, 'hr', %s, %s,
                    'tenant', %s, %s::jsonb, timezone('utc', now())
                )
                """,
                (
                    uuid.uuid4(),
                    tenant_id,
                    "tenant_hr_reset",
                    user.get("id"),
                    user.get("role"),
                    tenant_code,
                    json.dumps({"deleted": deleted}, ensure_ascii=False),
                ),
            )

    print(
        "[HR RESET] tenant-only reset "
        f"tenant={tenant_code} employees={deleted['employees']} sites={deleted['sites']}"
    )

    return {
        "success": True,
        "tenant_id": str(tenant_id),
        "tenant_code": tenant_code,
        "deleted": deleted,
    }
