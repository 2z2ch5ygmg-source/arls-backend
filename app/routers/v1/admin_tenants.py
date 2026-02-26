from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from psycopg import sql

from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import normalize_tenant_identifier, resolve_scoped_tenant

router = APIRouter(
    prefix="/admin/tenants",
    tags=["admin-tenants"],
    dependencies=[Depends(apply_rate_limit)],
)

logger = logging.getLogger(__name__)
PROTECTED_TENANT_CODES = {"master", "platform"}


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


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return bool(cur.fetchone())


def _delete_tenant_rows(conn, table_name: str, *, tenant_id: str, tenant_code: str) -> int:
    if not _table_exists(conn, table_name):
        return 0
    deleted = 0
    with conn.cursor() as cur:
        if tenant_id and _column_exists(conn, table_name, "tenant_id"):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE tenant_id::text = %s").format(sql.Identifier(table_name)),
                (tenant_id,),
            )
            deleted += int(cur.rowcount or 0)
        if tenant_code and _column_exists(conn, table_name, "tenant_code"):
            cur.execute(
                sql.SQL("DELETE FROM {} WHERE lower(trim(tenant_code::text)) = %s").format(sql.Identifier(table_name)),
                (tenant_code,),
            )
            deleted += int(cur.rowcount or 0)
    return deleted


def _clear_user_employee_links(conn, tenant_id: str) -> int:
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

    stage = "resolve_tenant_scope"
    tenant_id = ""
    tenant_code = tenant_header
    try:
        scoped_tenant = resolve_scoped_tenant(
            conn,
            user,
            header_tenant_id=tenant_header,
            require_dev_context=True,
        )
        tenant_id = str(scoped_tenant.get("id") or "").strip()
        tenant_code = normalize_tenant_identifier(scoped_tenant.get("tenant_code")) or tenant_header
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
            )

        stage = "protect_tenant_guard"
        if tenant_code in PROTECTED_TENANT_CODES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "TENANT_RESET_FORBIDDEN", "message": "보호 테넌트는 초기화할 수 없습니다."},
            )

        deleted: dict[str, int] = {}

        # 1) Upload sessions / temporary attachments
        stage = "delete_guard_roster_import_files"
        deleted["guard_roster_import_files"] = _delete_tenant_rows(
            conn, "guard_roster_import_files", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_guard_roster_import_sessions"
        deleted["guard_roster_import_sessions"] = _delete_tenant_rows(
            conn, "guard_roster_import_sessions", tenant_id=tenant_id, tenant_code=tenant_code
        )

        # 2) Employees
        stage = "delete_employees"
        deleted["employees"] = _delete_tenant_rows(conn, "employees", tenant_id=tenant_id, tenant_code=tenant_code)

        # 3) Schedules / attendance / leaves
        stage = "delete_monthly_schedules"
        deleted["monthly_schedules"] = _delete_tenant_rows(
            conn, "monthly_schedules", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_attendance_records"
        deleted["attendance_records"] = _delete_tenant_rows(
            conn, "attendance_records", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_attendance_requests"
        deleted["attendance_requests"] = _delete_tenant_rows(
            conn, "attendance_requests", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_leave_requests"
        deleted["leave_requests"] = _delete_tenant_rows(
            conn, "leave_requests", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_schedule_import_rows"
        deleted["schedule_import_rows"] = _delete_tenant_rows(
            conn, "schedule_import_rows", tenant_id=tenant_id, tenant_code=tenant_code
        )
        stage = "delete_schedule_import_batches"
        deleted["schedule_import_batches"] = _delete_tenant_rows(
            conn, "schedule_import_batches", tenant_id=tenant_id, tenant_code=tenant_code
        )

        # 4) Sites match index
        stage = "delete_sites_match_index"
        deleted["sites_match_index"] = _delete_tenant_rows(
            conn, "sites_match_index", tenant_id=tenant_id, tenant_code=tenant_code
        )

        # 5) Sites
        stage = "delete_sites"
        deleted["sites"] = _delete_tenant_rows(conn, "sites", tenant_id=tenant_id, tenant_code=tenant_code)

        # 6) Keep user accounts and clear employee/site links only
        stage = "clear_user_links"
        deleted["user_links_cleared"] = _clear_user_employee_links(conn, tenant_id)

        stage = "write_audit_log"
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
            "tenant_id": tenant_id,
            "tenant_code": tenant_code,
            "deleted": deleted,
        }
    except HTTPException:
        raise
    except Exception as exc:
        conn.rollback()
        logger.exception(
            "tenant reset failed tenant_code=%s tenant_id=%s stage=%s",
            tenant_code,
            tenant_id,
            stage,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "data": None,
                "error": {
                    "code": "TENANT_RESET_FAILED",
                    "stage": stage,
                    "message": "테넌트 데이터 초기화 중 오류가 발생했습니다.",
                    "detail": str(exc),
                },
            },
        )
