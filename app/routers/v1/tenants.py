from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import errors as pg_errors

from ...deps import get_db_conn, get_current_user, apply_rate_limit
from ...schemas import TenantCreate, TenantOut, TenantUpdate
from ...utils.permissions import (
    ROLE_BRANCH_MANAGER,
    ROLE_DEV,
    can_manage_tenant,
    normalize_role,
)

router = APIRouter(prefix="/tenants", tags=["tenants"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)


def _normalize_tenant_code(value: str | None) -> str:
    return str(value or "").strip().lower()


TENANT_CODE_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _slugify_tenant_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "company"


def _resolve_unique_tenant_code(conn, base_code: str) -> str:
    normalized_base = _normalize_tenant_code(base_code) or "company"
    for idx in range(1, 10000):
        candidate = normalized_base if idx == 1 else f"{normalized_base}-{idx}"
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM tenants
                WHERE lower(trim(tenant_code)) = %s
                LIMIT 1
                """,
                (candidate,),
            )
            exists = cur.fetchone()
        if not exists:
            return candidate
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "TENANT_CODE_GENERATION_FAILED", "message": "회사 코드 자동 생성에 실패했습니다."},
    )


@router.get("", response_model=list[TenantOut])
def list_tenants(
    include_inactive: bool = Query(default=False),
    include_deleted: bool = Query(default=False),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    where_clauses: list[str] = []
    if not include_deleted:
        where_clauses.append("COALESCE(is_deleted, FALSE) = FALSE")
    if not include_inactive:
        where_clauses.append("COALESCE(is_active, TRUE) = TRUE")
    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            {where}
            ORDER BY tenant_name
            """
        )
        rows = [TenantOut(**r) for r in cur.fetchall()]
    return rows


@router.post("", response_model=TenantOut)
def create_tenant(payload: TenantCreate, conn=Depends(get_db_conn), user=Depends(get_current_user)):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    tenant_name = str(payload.tenant_name or "").strip()
    if not tenant_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "INVALID_INPUT",
                "message": "입력값을 확인해주세요.",
                "fields": {"tenant_name": "required"},
                "detail": "tenant_name is required",
            },
        )

    tenant_code_input = _normalize_tenant_code(payload.tenant_code)
    tenant_code_auto = _slugify_tenant_name(tenant_name)
    if tenant_code_input:
        if not TENANT_CODE_PATTERN.fullmatch(tenant_code_input):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "INVALID_INPUT",
                    "message": "입력값을 확인해주세요.",
                    "fields": {"tenant_code": "invalid"},
                },
            )
        tenant_code_normalized = tenant_code_input
    else:
        tenant_code_normalized = _resolve_unique_tenant_code(conn, tenant_code_auto)

    tenant_id = uuid.uuid4()
    try:
        with conn.cursor() as cur:
            if tenant_code_input:
                cur.execute(
                    """
                    SELECT id,
                           tenant_code,
                           COALESCE(is_active, TRUE) AS is_active,
                           COALESCE(is_deleted, FALSE) AS is_deleted
                    FROM tenants
                    WHERE lower(trim(tenant_code)) = %s
                    LIMIT 1
                    """,
                    (tenant_code_normalized,),
                )
                existing = cur.fetchone()
                if existing:
                    logger.warning(
                        "create_tenant conflict: requested=%s normalized=%s existing_id=%s existing_code=%s existing_active=%s existing_deleted=%s",
                        payload.tenant_code,
                        tenant_code_normalized,
                        existing.get("id"),
                        existing.get("tenant_code"),
                        existing.get("is_active"),
                        existing.get("is_deleted"),
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail={
                            "error": "TENANT_EXISTS",
                            "message": "이미 존재하는 회사 코드입니다.",
                            "detail": {
                                "tenant_id": str(existing.get("id") or ""),
                                "tenant_code": str(existing.get("tenant_code") or ""),
                                "is_active": bool(existing.get("is_active", True)),
                                "is_deleted": bool(existing.get("is_deleted", False)),
                            },
                        },
                    )

            cur.execute(
                """
                INSERT INTO tenants (id, tenant_code, tenant_name, is_active, updated_at)
                VALUES (%s, %s, %s, %s, timezone('utc', now()))
                RETURNING id, tenant_code, tenant_name, COALESCE(is_active, TRUE) AS is_active
                """,
                (tenant_id, tenant_code_normalized, tenant_name, payload.is_active),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to create tenant")
    except HTTPException:
        raise
    except pg_errors.UniqueViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "TENANT_EXISTS", "message": "이미 존재하는 회사 코드입니다."},
        ) from exc
    except Exception as exc:
        logger.exception("create_tenant failed: tenant_code=%s", tenant_code_normalized, exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL", "message": "서버 오류입니다. 잠시 후 다시 시도해주세요."},
        ) from exc
    return TenantOut(**row)


@router.put("/{tenant_id}", response_model=TenantOut)
def update_tenant(
    tenant_id: uuid.UUID,
    payload: TenantUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_tenant(user["role"]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    if str(user.get("tenant_id")) == str(tenant_id) and not payload.is_active:
        raise HTTPException(status_code=400, detail="cannot deactivate current tenant")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE tenants
            SET tenant_name = %s,
                is_active = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            RETURNING id, tenant_code, tenant_name, COALESCE(is_active, TRUE) AS is_active
            """,
            (payload.tenant_name, payload.is_active, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="tenant not found")
    return TenantOut(**row)


def _append_integration_audit_log(
    conn,
    *,
    tenant_id: uuid.UUID | None,
    action_type: str,
    actor_user_id: uuid.UUID | None,
    actor_role: str | None,
    target_type: str,
    target_id: str,
    detail: dict,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO integration_audit_logs (
                id, tenant_id, action_type, source, actor_user_id, actor_role,
                target_type, target_id, detail, created_at
            )
            VALUES (
                %s, %s, %s, 'hr', %s, %s,
                %s, %s, %s::jsonb, timezone('utc', now())
            )
            """,
            (
                uuid.uuid4(),
                tenant_id,
                action_type,
                actor_user_id,
                actor_role,
                target_type,
                target_id,
                json.dumps(detail, ensure_ascii=False),
            ),
        )


def _ensure_can_delete_account(actor: dict) -> str:
    actor_role = normalize_role(actor.get("role"))
    if actor_role not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "계정 삭제 권한이 없습니다."},
        )
    return actor_role


def _count_remaining_same_role_users(conn, *, tenant_id: uuid.UUID | None, role: str, exclude_user_id: uuid.UUID) -> int:
    with conn.cursor() as cur:
        if tenant_id is None:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM arls_users
                WHERE role = %s
                  AND id <> %s
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """,
                (role, exclude_user_id),
            )
        else:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM arls_users
                WHERE tenant_id = %s
                  AND role = %s
                  AND id <> %s
                  AND COALESCE(is_deleted, FALSE) = FALSE
                """,
                (tenant_id, role, exclude_user_id),
            )
        row = cur.fetchone() or {}
    return int(row.get("total") or 0)


@router.delete("/{tenant_id}/users/{user_id}")
def delete_tenant_user(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _ensure_can_delete_account(user)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            WHERE id = %s
            LIMIT 1
            """,
            (tenant_id,),
        )
        tenant_row = cur.fetchone()
    if not tenant_row or tenant_row.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "테넌트를 찾을 수 없습니다."},
        )

    if actor_role == ROLE_BRANCH_MANAGER and str(user.get("tenant_id")) != str(tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "다른 테넌트 계정은 삭제할 수 없습니다."},
        )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id, au.tenant_id, au.username, au.role, au.is_active,
                   COALESCE(au.is_deleted, FALSE) AS is_deleted
            FROM arls_users au
            WHERE au.id = %s
              AND au.tenant_id = %s
            LIMIT 1
            """,
            (user_id, tenant_id),
        )
        target_user = cur.fetchone()

    if not target_user or target_user.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "USER_NOT_FOUND", "message": "계정을 찾을 수 없습니다."},
        )

    if str(target_user.get("id")) == str(user.get("id")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "SELF_DELETE_FORBIDDEN", "message": "현재 로그인 계정은 삭제할 수 없습니다."},
        )

    target_role = normalize_role(target_user.get("role"))
    if actor_role == ROLE_BRANCH_MANAGER and target_role == ROLE_DEV:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "개발자 계정은 삭제할 수 없습니다."},
        )

    if target_role == ROLE_BRANCH_MANAGER:
        remain = _count_remaining_same_role_users(
            conn,
            tenant_id=tenant_id,
            role=ROLE_BRANCH_MANAGER,
            exclude_user_id=user_id,
        )
        if remain <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "LAST_MANAGER_DELETE_FORBIDDEN", "message": "마지막 지점관리자 계정은 삭제할 수 없습니다."},
            )

    if target_role == ROLE_DEV:
        remain = _count_remaining_same_role_users(
            conn,
            tenant_id=None,
            role=ROLE_DEV,
            exclude_user_id=user_id,
        )
        if remain <= 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"error": "LAST_DEV_DELETE_FORBIDDEN", "message": "마지막 개발자 계정은 삭제할 수 없습니다."},
            )

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET is_deleted = TRUE,
                deleted_at = timezone('utc', now()),
                deleted_by = %s,
                is_active = FALSE,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            RETURNING id, username
            """,
            (user.get("id"), user_id, tenant_id),
        )
        deleted_row = cur.fetchone()

    if not deleted_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "USER_NOT_FOUND", "message": "계정을 찾을 수 없습니다."},
        )

    _append_integration_audit_log(
        conn,
        tenant_id=tenant_id,
        action_type="user_soft_delete",
        actor_user_id=user.get("id"),
        actor_role=actor_role,
        target_type="user",
        target_id=str(user_id),
        detail={
            "tenant_code": tenant_row.get("tenant_code"),
            "username": deleted_row.get("username"),
            "target_role": target_role,
            "mode": "soft_delete",
        },
    )

    return {
        "ok": True,
        "tenant_id": str(tenant_id),
        "deleted_user_id": str(user_id),
        "username": deleted_row.get("username"),
        "mode": "soft_delete",
    }
