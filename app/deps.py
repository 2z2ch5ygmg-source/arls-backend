from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_connection
from .security import decode_token
from .utils.permissions import normalize_role, normalize_user_role
from .utils.tenant_context import normalize_tenant_identifier
from .utils.guards import IDEMPOTENCY, RATE_LIMITER

security_scheme = HTTPBearer(auto_error=False)


def _unauthorized(message: str = "로그인이 필요합니다.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "UNAUTHORIZED", "message": message},
    )


def _forbidden(message: str = "접근 권한이 없습니다.") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"error": "FORBIDDEN", "message": message},
    )


def get_db_conn():
    with get_connection() as conn:
        yield conn


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
):
    if credentials is None:
        raise _unauthorized("로그인이 필요합니다.")
    if str(credentials.scheme or "").lower() != "bearer":
        raise _unauthorized("Bearer 토큰이 필요합니다.")
    token = str(credentials.credentials or "").strip()
    if not token:
        raise _unauthorized("Bearer 토큰이 비어 있습니다.")

    try:
        payload = decode_token(token)
    except Exception as exc:
        raise _unauthorized("유효하지 않은 인증 토큰입니다.") from exc

    token_use = str(payload.get("token_use") or "").strip().lower()
    if token_use == "refresh":
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = normalize_role(payload.get("role"))
    if not user_id or not tenant_id or not role:
        raise _unauthorized("유효하지 않은 인증 토큰입니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id, au.tenant_id, au.username, au.full_name, au.role, au.is_active,
                   au.employee_id, COALESCE(au.site_id, e.site_id) AS site_id, s.site_code,
                   e.employee_code, t.tenant_code, t.tenant_name,
                   COALESCE(t.is_active, TRUE) AS tenant_is_active,
                   COALESCE(t.is_deleted, FALSE) AS tenant_is_deleted
            FROM arls_users au
            JOIN tenants t ON t.id = au.tenant_id
            LEFT JOIN employees e ON e.id = au.employee_id
            LEFT JOIN sites s ON s.id = COALESCE(au.site_id, e.site_id)
            WHERE au.id = %s
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
            """,
            (user_id,),
        )
        row = cur.fetchone()

    if not row or not bool(row.get("tenant_is_active", True)) or bool(row.get("tenant_is_deleted", False)):
        raise _unauthorized("계정을 찾을 수 없습니다.")

    result = dict(row)
    result["role"] = normalize_user_role(result.get("role"))
    result["active_tenant_id"] = normalize_tenant_identifier(x_tenant_id)
    return result


def require_roles(*roles):
    allowed = {normalize_role(role) for role in roles}

    def _guard(user=Depends(get_current_user)):
        if normalize_role(user.get("role")) not in allowed:
            raise _forbidden("접근 권한이 없습니다.")
        return user

    return _guard


def apply_rate_limit(request: Request, user=Depends(get_current_user)):
    token = str(request.client.host or "unknown")
    RATE_LIMITER.check(token, str(user["tenant_id"]))
    return None


def get_idempotency_key(
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(get_current_user),
):
    if not idempotency_key:
        return None
    if IDEMPOTENCY.seen(user["tenant_code"], user["id"], idempotency_key):
        raise HTTPException(status_code=409, detail="duplicate request")

    with get_connection() as conn:
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO api_idempotency_keys
                (tenant_id, user_id, request_key, method, path, request_hash, first_seen_at, last_seen_at, call_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (tenant_id, user_id, request_key)
                DO UPDATE SET last_seen_at = EXCLUDED.last_seen_at, call_count = api_idempotency_keys.call_count + 1
                """,
                (
                    user["tenant_id"],
                    user["id"],
                    idempotency_key,
                    request.method,
                    request.url.path,
                    request.method + request.url.path,
                    now,
                    now,
                ),
            )
    return idempotency_key
