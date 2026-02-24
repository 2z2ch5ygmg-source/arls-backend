from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import (
    UserAdminActiveUpdate,
    UserAdminCreate,
    UserAdminOut,
    UserAdminPasswordReset,
    UserAdminRoleUpdate,
    UserSelfPasswordChange,
)
from ...security import hash_password, verify_password
from ...utils.permissions import (
    ALL_USER_ROLES,
    ROLE_BRANCH_MANAGER,
    ROLE_DEVELOPER,
    ROLE_DEV,
    can_manage_user_accounts,
    normalize_role,
    normalize_user_role,
)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(apply_rate_limit)])


def _require_account_manager(user: dict) -> str:
    actor_role = normalize_role(user.get("role"))
    if not can_manage_user_accounts(
        actor_role,
        allow_branch_manager=settings.allow_branch_manager_user_manage,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return actor_role


def _require_same_tenant_for_branch_manager(user: dict, tenant_code: str, actor_role: str) -> None:
    if actor_role != ROLE_BRANCH_MANAGER:
        return
    own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    target_tenant_code = str(tenant_code or "").strip().upper()
    if not own_tenant_code or not target_tenant_code or own_tenant_code != target_tenant_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _validate_target_role(user: dict, next_role: str, tenant_code: str, actor_role: str) -> None:
    if next_role not in ALL_USER_ROLES:
        raise HTTPException(status_code=400, detail="invalid role")
    if next_role == ROLE_DEVELOPER and actor_role != ROLE_DEV:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _resolve_tenant(conn, *, tenant_id: uuid.UUID | None = None, tenant_code: str | None = None):
    normalized_code = str(tenant_code or "").strip().lower()
    if tenant_id is None and not normalized_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "tenant_id 또는 tenant_code가 필요합니다."},
        )

    with conn.cursor() as cur:
        if tenant_id is not None:
            cur.execute(
                """
                SELECT id, tenant_code
                FROM tenants
                WHERE id = %s
                  AND COALESCE(is_active, TRUE) = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                LIMIT 1
                """,
                (tenant_id,),
            )
        else:
            cur.execute(
                """
                SELECT id, tenant_code
                FROM tenants
                WHERE lower(trim(tenant_code)) = %s
                  AND COALESCE(is_active, TRUE) = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                LIMIT 1
                """,
                (normalized_code,),
            )
        tenant = cur.fetchone()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )
    return tenant


def _resolve_employee_id(conn, tenant_id, employee_code: str | None):
    code = str(employee_code or "").strip()
    if not code:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM employees
            WHERE tenant_id = %s AND employee_code = %s
            """,
            (tenant_id, code),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="employee not found")
    return row["id"]


def _fetch_user_row(conn, user_id: uuid.UUID):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id, au.tenant_id, t.tenant_code, au.username, au.full_name, au.role, au.is_active,
                   au.employee_id, e.employee_code, au.last_login_at, au.created_at, au.updated_at
            FROM arls_users au
            JOIN tenants t ON t.id = au.tenant_id
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE au.id = %s
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND COALESCE(t.is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (user_id,),
        )
        return cur.fetchone()


def _fetch_user_password_row(conn, user_id: uuid.UUID):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_id, password_hash, role, is_active
            FROM arls_users
            WHERE id = %s
              AND COALESCE(is_deleted, FALSE) = FALSE
            LIMIT 1
            """,
            (user_id,),
        )
        return cur.fetchone()


def _assert_manageable_target(user: dict, target_row, actor_role: str) -> None:
    if not target_row:
        raise HTTPException(status_code=404, detail="user not found")
    if actor_role == ROLE_DEV:
        return
    _require_same_tenant_for_branch_manager(user, target_row.get("tenant_code"), actor_role)
    if normalize_role(target_row.get("role")) == ROLE_DEV:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")


def _row_to_out(row) -> UserAdminOut:
    return UserAdminOut(
        id=row["id"],
        tenant_id=row["tenant_id"],
        tenant_code=row["tenant_code"],
        username=row["username"],
        full_name=row["full_name"],
        role=normalize_user_role(row["role"]),
        is_active=bool(row["is_active"]),
        employee_id=row.get("employee_id"),
        employee_code=row.get("employee_code"),
        last_login_at=row.get("last_login_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
    )


@router.get("", response_model=list[UserAdminOut])
def list_users(
    tenant_code: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=120),
    include_inactive: bool = Query(default=True),
    limit: int = Query(default=200, ge=1, le=500),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = normalize_role(user.get("role"))
    if actor_role not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")

    clauses: list[str] = [
        "COALESCE(t.is_active, TRUE) = TRUE",
        "COALESCE(t.is_deleted, FALSE) = FALSE",
        "COALESCE(au.is_deleted, FALSE) = FALSE",
    ]
    params: list = []

    target_tenant = str(tenant_code or "").strip()
    if actor_role == ROLE_BRANCH_MANAGER:
        own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
        if target_tenant and target_tenant.upper() != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        target_tenant = own_tenant_code

    if target_tenant:
        clauses.append("lower(trim(t.tenant_code)) = %s")
        params.append(target_tenant.strip().lower())

    keyword = str(q or "").strip()
    if keyword:
        like = f"%{keyword}%"
        clauses.append("(au.username ILIKE %s OR au.full_name ILIKE %s OR t.tenant_code ILIKE %s)")
        params.extend([like, like, like])

    if not include_inactive:
        clauses.append("au.is_active = TRUE")

    params.append(limit)
    where_sql = " AND ".join(clauses) if clauses else "TRUE"

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT au.id, au.tenant_id, t.tenant_code, au.username, au.full_name, au.role, au.is_active,
                   au.employee_id, e.employee_code, au.last_login_at, au.created_at, au.updated_at
            FROM arls_users au
            JOIN tenants t ON t.id = au.tenant_id
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE {where_sql}
            ORDER BY t.tenant_code, au.username
            LIMIT %s
            """,
            tuple(params),
        )
        rows = cur.fetchall()
    return [_row_to_out(row) for row in rows]


@router.post("", response_model=UserAdminOut)
def create_user(
    payload: UserAdminCreate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_account_manager(user)
    tenant = _resolve_tenant(
        conn,
        tenant_id=payload.tenant_id,
        tenant_code=payload.tenant_code,
    )
    _require_same_tenant_for_branch_manager(user, tenant["tenant_code"], actor_role)

    normalized_role = normalize_user_role(payload.role)
    _validate_target_role(user, normalized_role, tenant["tenant_code"], actor_role)

    employee_id = _resolve_employee_id(conn, tenant["id"], payload.employee_code)
    user_id = uuid.uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO arls_users (
                id, tenant_id, username, password_hash, full_name, role, is_active, employee_id, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, timezone('utc', now()), timezone('utc', now()))
            ON CONFLICT (tenant_id, username) DO NOTHING
            RETURNING id
            """,
            (
                user_id,
                tenant["id"],
                payload.username.strip(),
                hash_password(payload.password),
                payload.full_name.strip(),
                normalized_role,
                payload.is_active,
                employee_id,
            ),
        )
        created = cur.fetchone()
    if not created:
        raise HTTPException(status_code=409, detail="username already exists in tenant")
    row = _fetch_user_row(conn, user_id)
    if not row:
        raise HTTPException(status_code=500, detail="failed to create user")
    return _row_to_out(row)


@router.patch("/me/password")
def change_own_password(
    payload: UserSelfPasswordChange,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    row = _fetch_user_password_row(conn, user["id"])
    if not row or not row.get("is_active"):
        raise HTTPException(status_code=404, detail="account not found")

    if not verify_password(payload.current_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="invalid current password")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="new password must be different")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET password_hash = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (hash_password(payload.new_password), user["id"]),
        )
    return {"ok": True}


@router.patch("/{user_id}/role", response_model=UserAdminOut)
def update_user_role(
    user_id: uuid.UUID,
    payload: UserAdminRoleUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_account_manager(user)
    next_role = normalize_user_role(payload.role)

    row = _fetch_user_row(conn, user_id)
    _assert_manageable_target(user, row, actor_role)
    _validate_target_role(user, next_role, row["tenant_code"], actor_role)

    current_actor_role = normalize_user_role(user.get("role"))
    if str(row["id"]) == str(user["id"]) and next_role != current_actor_role:
        raise HTTPException(status_code=400, detail="cannot change current account role")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET role = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (next_role, user_id),
        )
    updated = _fetch_user_row(conn, user_id)
    if not updated:
        raise HTTPException(status_code=500, detail="user update failed")
    return _row_to_out(updated)


@router.patch("/{user_id}/password", response_model=UserAdminOut)
def reset_user_password(
    user_id: uuid.UUID,
    payload: UserAdminPasswordReset,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_account_manager(user)
    row = _fetch_user_row(conn, user_id)
    _assert_manageable_target(user, row, actor_role)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET password_hash = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (hash_password(payload.new_password), user_id),
        )

    updated = _fetch_user_row(conn, user_id)
    if not updated:
        raise HTTPException(status_code=500, detail="user update failed")
    return _row_to_out(updated)


@router.patch("/{user_id}/active", response_model=UserAdminOut)
def update_user_active(
    user_id: uuid.UUID,
    payload: UserAdminActiveUpdate,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    actor_role = _require_account_manager(user)
    if str(user_id) == str(user.get("id")) and not payload.is_active:
        raise HTTPException(status_code=400, detail="cannot deactivate current account")

    row = _fetch_user_row(conn, user_id)
    _assert_manageable_target(user, row, actor_role)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET is_active = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (payload.is_active, user_id),
        )
    updated = _fetch_user_row(conn, user_id)
    if not updated:
        raise HTTPException(status_code=500, detail="user update failed")
    return _row_to_out(updated)
