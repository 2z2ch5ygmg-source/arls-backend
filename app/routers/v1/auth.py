from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...config import settings
from ...db import fetch_all, fetch_one
from ...deps import get_db_conn, get_current_user, apply_rate_limit
from ...schemas import AuthUser, LoginRequest, RefreshTokenRequest, TokenResponse
from ...security import decode_refresh_token, encode_refresh_token, encode_token, verify_password
from ...utils.credential_norm import build_auth_identifier_candidates
from ...utils.permissions import normalize_role, normalize_user_role

router = APIRouter(prefix="/auth", tags=["auth"])
MASTER_TENANT_CODE = "master"
MASTER_LOGIN_FORBIDDEN_MESSAGE = "슈퍼 관리자 계정만 MASTER로 로그인할 수 있습니다."
logger = logging.getLogger(__name__)


def _normalize_tenant_code(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _mask_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "-"
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return f"{normalized[:3]}***{normalized[-2:]}"


def _debug_auth_lookup(
    *,
    tenant_id,
    identifier_candidates: tuple[str, ...],
    matched_user: Optional[dict],
    candidate_count: int,
) -> None:
    if str(settings.environment or "").strip().lower() == "production":
        return
    masked_candidates = [_mask_identifier(value) for value in identifier_candidates]
    logger.info(
        "auth.lookup tenant_id=%s identifiers=%s candidate_count=%s matched_user_id=%s matched_deleted=%s",
        tenant_id,
        ",".join(masked_candidates) if masked_candidates else "-",
        int(candidate_count),
        (matched_user or {}).get("id"),
        bool((matched_user or {}).get("is_deleted")),
    )


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
        must_change_password=bool(user.get("must_change_password", False)),
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


def _find_tenant_user_by_password(
    conn,
    *,
    tenant_id,
    identifier_candidates: tuple[str, ...],
    password: str,
) -> Optional[dict]:
    if not identifier_candidates:
        _debug_auth_lookup(
            tenant_id=tenant_id,
            identifier_candidates=identifier_candidates,
            matched_user=None,
            candidate_count=0,
        )
        return None

    candidates = fetch_all(
        conn,
        """
        SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash,
               au.employee_id, e.employee_code,
               COALESCE(au.must_change_password, FALSE) AS must_change_password,
               COALESCE(au.is_deleted, FALSE) AS is_deleted
        FROM arls_users au
        LEFT JOIN employees e ON e.id = au.employee_id
        WHERE au.tenant_id = %s
          AND lower(regexp_replace(COALESCE(au.username, ''), '[-\\s]+', '', 'g')) = ANY(%s::text[])
          AND au.is_active = TRUE
          AND COALESCE(au.is_deleted, FALSE) = FALSE
        ORDER BY COALESCE(au.last_login_at, au.updated_at, au.created_at) DESC
        LIMIT 20
        """,
        (tenant_id, list(identifier_candidates)),
    )
    matched_user = None
    for row in candidates:
        if verify_password(password, row.get("password_hash") or ""):
            matched_user = row
            break

    _debug_auth_lookup(
        tenant_id=tenant_id,
        identifier_candidates=identifier_candidates,
        matched_user=matched_user,
        candidate_count=len(candidates),
    )
    return matched_user


def handle_master_login(payload: LoginRequest, conn):
    identifier_candidates = build_auth_identifier_candidates(payload.username)
    if not identifier_candidates:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    master_candidates = fetch_all(
        conn,
        """
        SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash,
               au.employee_id, e.employee_code, t.tenant_code,
               COALESCE(au.must_change_password, FALSE) AS must_change_password,
               COALESCE((to_jsonb(au)->>'is_super_admin')::boolean, FALSE) AS is_super_admin
        FROM arls_users au
        JOIN tenants t ON t.id = au.tenant_id
        LEFT JOIN employees e ON e.id = au.employee_id
        WHERE lower(regexp_replace(COALESCE(au.username, ''), '[-\\s]+', '', 'g')) = ANY(%s::text[])
          AND au.is_active = TRUE
          AND COALESCE(au.is_deleted, FALSE) = FALSE
          AND COALESCE(t.is_active, TRUE) = TRUE
          AND COALESCE(t.is_deleted, FALSE) = FALSE
          AND lower(t.tenant_code) = %s
        ORDER BY COALESCE(au.last_login_at, au.updated_at, au.created_at) DESC
        LIMIT 10
        """,
        (list(identifier_candidates), MASTER_TENANT_CODE),
    )

    matched_users = [row for row in master_candidates if verify_password(payload.password, row["password_hash"])]
    if not matched_users:
        privileged_candidates = fetch_all(
            conn,
            """
            SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash,
                   au.employee_id, e.employee_code, t.tenant_code,
                   COALESCE(au.must_change_password, FALSE) AS must_change_password,
                   COALESCE((to_jsonb(au)->>'is_super_admin')::boolean, FALSE) AS is_super_admin
            FROM arls_users au
            JOIN tenants t ON t.id = au.tenant_id
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE lower(regexp_replace(COALESCE(au.username, ''), '[-\\s]+', '', 'g')) = ANY(%s::text[])
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND COALESCE(t.is_active, TRUE) = TRUE
              AND COALESCE(t.is_deleted, FALSE) = FALSE
              AND (
                    lower(au.role) IN ('developer', 'dev', 'platform_admin')
                    OR COALESCE((to_jsonb(au)->>'is_super_admin')::boolean, FALSE) = TRUE
              )
            ORDER BY COALESCE(au.last_login_at, au.updated_at, au.created_at) DESC
            LIMIT 20
            """,
            (list(identifier_candidates),),
        )
        matched_users = [row for row in privileged_candidates if verify_password(payload.password, row["password_hash"])]

    if not matched_users:
        fallback_candidates = fetch_all(
            conn,
            """
            SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.password_hash,
                   au.employee_id, e.employee_code, t.tenant_code,
                   COALESCE(au.must_change_password, FALSE) AS must_change_password,
                   COALESCE((to_jsonb(au)->>'is_super_admin')::boolean, FALSE) AS is_super_admin
            FROM arls_users au
            JOIN tenants t ON t.id = au.tenant_id
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE lower(regexp_replace(COALESCE(au.username, ''), '[-\\s]+', '', 'g')) = ANY(%s::text[])
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND COALESCE(t.is_active, TRUE) = TRUE
              AND COALESCE(t.is_deleted, FALSE) = FALSE
            ORDER BY COALESCE(au.last_login_at, au.updated_at, au.created_at) DESC
            LIMIT 10
            """,
            (list(identifier_candidates),),
        )
        matched_fallback = [
            row for row in fallback_candidates if verify_password(payload.password, row["password_hash"])
        ]
        if matched_fallback:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=MASTER_LOGIN_FORBIDDEN_MESSAGE)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    def _priority(row: dict) -> tuple[int, int]:
        is_master_tenant = _normalize_tenant_code(row.get("tenant_code")) == MASTER_TENANT_CODE
        is_dev_role = normalize_role(row.get("role")) == "dev"
        is_super_admin = bool(row.get("is_super_admin"))
        can_master_login = is_dev_role or is_super_admin
        return (
            0 if is_master_tenant else 1,
            0 if can_master_login else 1,
        )

    user = sorted(matched_users, key=_priority)[0]

    is_dev_role = normalize_role(user.get("role")) == "dev"
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
    identifier_candidates = build_auth_identifier_candidates(payload.username)
    if not identifier_candidates:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if tenant_input == MASTER_TENANT_CODE:
        return handle_master_login(payload, conn)

    tenant = fetch_one(
        conn,
        """
        SELECT id, tenant_code, tenant_name
        FROM tenants
        WHERE lower(tenant_code) = %s
          AND COALESCE(is_active, TRUE) = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (tenant_input,),
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    user = _find_tenant_user_by_password(
        conn,
        tenant_id=tenant["id"],
        identifier_candidates=identifier_candidates,
        password=payload.password,
    )
    if not user:
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
        tenant_code=_normalize_tenant_code(tenant["tenant_code"]),
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
               COALESCE(au.must_change_password, FALSE) AS must_change_password,
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
    tenant_code = MASTER_TENANT_CODE if is_master else _normalize_tenant_code(user["tenant_code"])
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
        WHERE lower(tenant_code) = %s
          AND COALESCE(is_active, TRUE) = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        """,
        (_normalize_tenant_code(tenant_code),),
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
        tenant_code=_normalize_tenant_code(user["tenant_code"]),
        role=normalize_user_role(user["role"]),
        employee_id=user.get("employee_id"),
        employee_code=user.get("employee_code"),
        must_change_password=bool(user.get("must_change_password", False)),
        is_master=is_master,
        tenant_scope="ALL" if is_master else None,
    )
