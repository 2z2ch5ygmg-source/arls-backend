from __future__ import annotations

import json
import uuid
from typing import Any

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, status
from psycopg import sql

from ...config import settings
from ...deps import apply_rate_limit, get_db_conn, require_roles
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV
from ...utils.tenant_context import normalize_tenant_identifier, resolve_scoped_tenant

router = APIRouter(
    prefix="/admin/reset",
    tags=["admin-reset"],
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


def _call_soc_tenant_reset(*, tenant_context: str) -> dict[str, Any]:
    soc_base_url = str(getattr(settings, "soc_base_url", "") or "").strip().rstrip("/")
    if not soc_base_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "SOC_BASE_URL_MISSING", "message": "SOC_BASE_URL 설정이 필요합니다."},
        )

    hr_reset_token = str(getattr(settings, "hr_reset_token", "") or "").strip()
    if not hr_reset_token:
        print("[HR->SOC] reset-master-data WARN: HR_RESET_TOKEN is empty")

    reset_url = f"{soc_base_url}/api/admin/hr/reset-master-data"
    print(f"[HR->SOC] full-reset POST url={reset_url} tenant={tenant_context}")

    try:
        response = requests.post(
            reset_url,
            headers={
                "X-HR-RESET-TOKEN": hr_reset_token,
                "X-Tenant-Id": tenant_context,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"[HR->SOC] full-reset failed: {repr(exc)} tenant={tenant_context}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "SOC_RESET_FAILED",
                "message": "SOC 테넌트 초기화 호출에 실패했습니다.",
                "detail": str(exc),
            },
        ) from exc

    response_text = (response.text or "").strip()
    print(
        f"[HR->SOC] full-reset status={response.status_code} "
        f"tenant={tenant_context} body={response_text[:200]}"
    )

    parsed_body: Any
    try:
        parsed_body = response.json()
    except Exception:
        parsed_body = response_text[:200]

    if int(response.status_code) >= 400:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "SOC_RESET_FAILED",
                "message": "SOC 테넌트 초기화 응답이 실패했습니다.",
                "detail": {
                    "status_code": int(response.status_code),
                    "body": parsed_body if isinstance(parsed_body, (dict, list)) else response_text[:200],
                },
            },
        )

    return {
        "ok": True,
        "status_code": int(response.status_code),
        "body": parsed_body if isinstance(parsed_body, (dict, list)) else response_text[:200],
    }


@router.post("/full")
def reset_hr_soc_full(
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
    tenant_code = normalize_tenant_identifier(scoped_tenant.get("tenant_code"))
    tenant_context = tenant_code or tenant_header
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )

    print(f"[HR RESET] start full-reset tenant={tenant_context} tenant_id={tenant_id}")

    hr_deleted = {
        "user_links_cleared": _clear_user_employee_links(conn, tenant_id),
        "employees": _delete_tenant_rows(conn, "employees", tenant_id),
        "sites": _delete_tenant_rows(conn, "sites", tenant_id),
    }

    soc_deleted = _call_soc_tenant_reset(tenant_context=tenant_context)

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
                    "hr_soc_full_reset",
                    user.get("id"),
                    user.get("role"),
                    tenant_context,
                    json.dumps({"hr_deleted": hr_deleted, "soc_deleted": soc_deleted}, ensure_ascii=False),
                ),
            )

    print(
        "[HR RESET] completed full-reset "
        f"tenant={tenant_context} employees={hr_deleted['employees']} sites={hr_deleted['sites']}"
    )

    return {
        "success": True,
        "tenant_id": str(tenant_id),
        "tenant_code": tenant_context,
        "hr_deleted": hr_deleted,
        "soc_deleted": soc_deleted,
    }
