from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors

from ...deps import get_db_conn, get_current_user, apply_rate_limit, require_roles
from ...schemas import CompanyCreate, CompanyOut
from ...utils.permissions import ROLE_DEV, normalize_role

router = APIRouter(prefix="/companies", tags=["companies"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)


def _company_manager_roles() -> tuple:
    # Policy: company(tenant-scoped organization) creation is allowed only in MASTER(DEV) console.
    return (ROLE_DEV,)


def _resolve_target_tenant(conn, user, tenant_code: str | None):
    actor_role = normalize_role(user["role"])
    own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    requested_tenant_code = str(tenant_code or "").strip().upper()

    if actor_role != ROLE_DEV:
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return {"id": user["tenant_id"], "tenant_code": own_tenant_code}

    if not requested_tenant_code:
        return {"id": user["tenant_id"], "tenant_code": own_tenant_code}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code
            FROM tenants
            WHERE tenant_code = %s
              AND COALESCE(is_active, TRUE) = TRUE
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (requested_tenant_code,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return row


@router.get("", response_model=list[CompanyOut])
def list_companies(
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user["role"])
    args: tuple = ()
    requested_tenant_code = str(tenant_code or "").strip().upper()

    if actor_role == ROLE_DEV and requested_tenant_code:
        args = (requested_tenant_code,)
    elif actor_role != ROLE_DEV:
        own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        args = (user["tenant_id"],)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT c.id, c.company_code, c.company_name, t.tenant_code
            FROM companies c
            JOIN tenants t ON t.id = c.tenant_id
            WHERE COALESCE(t.is_active, TRUE) = TRUE
              AND COALESCE(t.is_deleted, FALSE) = FALSE
              {"AND t.tenant_code = %s" if actor_role == ROLE_DEV and requested_tenant_code else ""}
              {"AND c.tenant_id = %s" if actor_role != ROLE_DEV else ""}
            ORDER BY c.company_code
            """,
            args,
        )
        return [CompanyOut(**r) for r in cur.fetchall()]


@router.post("", response_model=CompanyOut)
def create_company(
    payload: CompanyCreate,
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(require_roles(*_company_manager_roles())),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    company_code = str(payload.company_code or "").strip()
    company_name = str(payload.company_name or "").strip()
    if not company_code or not company_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_INPUT",
                "message": "입력값을 확인해주세요.",
                "detail": "company_code and company_name are required",
            },
        )

    company_id = uuid.uuid4()
    tenant_id = tenant["id"]

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM companies c
                WHERE c.tenant_id = %s AND c.company_code = %s
                LIMIT 1
                """,
                (tenant_id, company_code),
            )
            if cur.fetchone():
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"error": "COMPANY_EXISTS", "message": "이미 존재하는 회사 코드입니다."},
                )

            cur.execute(
                """
                INSERT INTO companies (id, tenant_id, company_code, company_name)
                VALUES (%s, %s, %s, %s)
                RETURNING id, company_code, company_name, %s AS tenant_code
                """,
                (company_id, tenant_id, company_code, company_name, tenant["tenant_code"]),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to create company")
    except HTTPException:
        raise
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "COMPANY_EXISTS", "message": "이미 존재하는 회사 코드입니다."},
        ) from exc
    except Exception as exc:
        logger.exception(
            "create_company failed: tenant_code=%s company_code=%s",
            tenant.get("tenant_code"),
            company_code,
            exc_info=exc,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc
    return CompanyOut(**row)
