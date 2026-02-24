from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...db import fetch_one
from ...deps import get_db_conn, get_current_user, apply_rate_limit
from ...schemas import AuthUser, LoginRequest, RefreshTokenRequest, TokenResponse
from ...security import decode_refresh_token, encode_refresh_token, encode_token, verify_password
from ...utils.permissions import normalize_role, normalize_user_role

router = APIRouter(prefix="/auth", tags=["auth"])
MASTER_TENANT_CODE = "MASTER"
MASTER_LOGIN_FORBIDDEN_MESSAGE = "슈퍼 관리자 계정만 MASTER로 로그인할 수 있습니다."


def _normalize_tenant_code(value: str | None) -> str:
    return str(value or "").strip().upper()


def _build_auth_user(
    user: dict,
    *,
    tenant_code: str,
    role: str,
    is_master: bool = False,
) -> AuthUser:
    return AuthUser(
        id=user["id"],
        username=user["username"],
        full_name=user["full_name"],
        tenant_id=user["tenant_id"],
        tenant_code=tenant_code,
        role=role,
        employee_id=user.get("employee_id"),
        employee_code=user.get("employee_code"),
        is_master=is_master if is_master else None,
        tenant_scope="ALL" if is_master else None,
    )


def _build_token_response(
    user: dict,
    *,
    tenant_code: str,
    role: str,
    is_master: bool = False,
) -> TokenResponse:
    now_iso = datetime.now(timezone.utc).isoformat()
    token_payload = {
        "sub": str(user["id"]),
        "tenant_id": str(user["tenant_id"]),
        "tenant_code": tenant_code,
        "role": role,
        "employee_id": str(user["employee_id"]) if user.get("employee_id") else None,
        "issued_at": now_iso,
    }
    if is_master:
        token_payload["is_master"] = True
        token_payload["tenant_scope"] = "ALL"

    access_token = encode_token(token_payload)
    refresh_token = encode_refresh_token(token_payload)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user=_build_auth_user(user, tenant_code=tenant_code, role=role, is_master=is_master),
    )


def handle_master_login(payload: LoginRequest, conn):
    user = fetch_one(
        conn,
        """
        SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash,
               au.employee_id, e.employee_code,
               COALESCE((to_jsonb(au)->>'is_super_admin')::boolean, FALSE) AS is_super_admin
        FROM arls_users au
        JOIN tenants t ON t.id = au.tenant_id
        LEFT JOIN employees e ON e.id = au.employee_id
        WHERE lower(au.username) = lower(%s)
          AND au.is_active = TRUE
          AND COALESCE(au.is_deleted, FALSE) = FALSE
          AND COALESCE(t.is_active, TRUE) = TRUE
          AND COALESCE(t.is_deleted, FALSE) = FALSE
        LIMIT 1
        """,
        (payload.username,),
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    is_dev_role = normalize_role(user["role"]) == "dev"
    is_super_admin = bool(user.get("is_super_admin"))
    if not is_dev_role and not is_super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MASTER_LOGIN_FORBIDDEN_MESSAGE)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET last_login_at = timezone('utc', now())
            WHERE id = %s
            """,
            (user["id"],),
        )

    return _build_token_response(
        user,
        tenant_code=MASTER_TENANT_CODE,
        role=normalize_user_role(user.get("role")),
        is_master=True,
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, conn=Depends(get_db_conn)):
    tenant_input = _normalize_tenant_code(payload.tenant_code)
    if tenant_input == MASTER_TENANT_CODE:
        return handle_master_login(payload, conn)

    tenant = fetch_one(
        conn,
        """
        SELECT id, tenant_code, tenant_name
        FROM tenants
        WHERE upper(tenant_code) = upper(%s)
          AND COALESCE(is_active, TRUE) = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (payload.tenant_code,),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user = fetch_one(
        conn,
        """
        SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash, au.employee_id, e.employee_code
        FROM arls_users au
        LEFT JOIN employees e ON e.id = au.employee_id
        WHERE au.tenant_id = %s
          AND lower(au.username) = lower(%s)
          AND au.is_active = TRUE
          AND COALESCE(au.is_deleted, FALSE) = FALSE
        """,
        (tenant["id"], payload.username),
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE arls_users
            SET last_login_at = timezone('utc', now())
            WHERE id = %s
            """,
            (user["id"],),
        )

    user_role = normalize_user_role(user["role"])

    return _build_token_response(
        user,
        tenant_code=tenant["tenant_code"],
        role=user_role,
        is_master=False,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshTokenRequest, conn=Depends(get_db_conn)):
    try:
        token_payload = decode_refresh_token(payload.refresh_token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    user_id = token_payload.get("sub")
    tenant_id = token_payload.get("tenant_id")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    user = fetch_one(
        conn,
        """
        SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.employee_id, au.is_active,
               e.employee_code, t.tenant_code, COALESCE(t.is_active, TRUE) AS tenant_is_active,
               COALESCE(t.is_deleted, FALSE) AS tenant_is_deleted
        FROM arls_users au
        JOIN tenants t ON t.id = au.tenant_id
        LEFT JOIN employees e ON e.id = au.employee_id
        WHERE au.id = %s
          AND au.tenant_id = %s
          AND au.is_active = TRUE
          AND COALESCE(au.is_deleted, FALSE) = FALSE
        LIMIT 1
        """,
        (user_id, tenant_id),
    )
    if not user or not bool(user.get("tenant_is_active", True)) or bool(user.get("tenant_is_deleted", False)):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    role = normalize_user_role(user["role"])
    role_scope = normalize_role(role)
    refresh_tenant_code = _normalize_tenant_code(token_payload.get("tenant_code"))
    is_master = role_scope == "dev" and refresh_tenant_code == MASTER_TENANT_CODE
    tenant_code = MASTER_TENANT_CODE if is_master else user["tenant_code"]
    if refresh_tenant_code and refresh_tenant_code not in {tenant_code, MASTER_TENANT_CODE}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    return _build_token_response(
        user,
        tenant_code=tenant_code,
        role=role,
        is_master=is_master,
    )


@router.get("/tenant-check")
def tenant_check(tenant_code: str = Query(..., min_length=1, max_length=64), conn=Depends(get_db_conn)):
    if _normalize_tenant_code(tenant_code) == MASTER_TENANT_CODE:
        return {
            "exists": True,
            "tenant_code": MASTER_TENANT_CODE,
            "tenant_name": "Master Console",
            "is_master": True,
        }

    tenant = fetch_one(
        conn,
        """
        SELECT tenant_code, tenant_name
        FROM tenants
        WHERE upper(tenant_code) = upper(%s)
          AND COALESCE(is_active, TRUE) = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (tenant_code.strip(),),
    )
    if not tenant:
        return {"exists": False}
    return {
        "exists": True,
        "tenant_code": tenant["tenant_code"],
        "tenant_name": tenant["tenant_name"],
    }


@router.get("/me", response_model=AuthUser, dependencies=[Depends(apply_rate_limit)])
def me(user=Depends(get_current_user)):
    is_master = normalize_role(user["role"]) == "dev" and _normalize_tenant_code(user.get("tenant_code")) == MASTER_TENANT_CODE
    return AuthUser(
        id=user["id"],
        username=user["username"],
        full_name=user["full_name"],
        tenant_id=user["tenant_id"],
        tenant_code=user["tenant_code"],
        role=normalize_user_role(user["role"]),
        employee_id=user.get("employee_id"),
        employee_code=user.get("employee_code"),
        is_master=is_master,
        tenant_scope="ALL" if is_master else None,
    )
