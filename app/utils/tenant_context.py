from __future__ import annotations

import re
import threading
import time

from fastapi import HTTPException, status

from .permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, ROLE_EMPLOYEE, normalize_role

TENANT_ID_PATTERN = re.compile(r"^[a-z0-9_]{3,32}$")
TENANT_ID_INPUT_PATTERN = re.compile(r"^[a-z0-9_-]{3,32}$")
_TENANT_ROW_CACHE_TTL_SECONDS = 12.0
_TENANT_ROW_CACHE_MAX_SIZE = 1024
_TENANT_ROW_CACHE_LOCK = threading.Lock()
_TENANT_ROW_CACHE: dict[tuple[str, ...], tuple[float, dict | None]] = {}


def normalize_tenant_identifier(value: str | None) -> str:
    return str(value or "").strip().lower()


def canonical_tenant_identifier(value: str | None) -> str:
    return normalize_tenant_identifier(value).replace("-", "_")


def build_tenant_identifier_candidates(value: str | None) -> tuple[str, ...]:
    raw = normalize_tenant_identifier(value)
    if not raw:
        return ()

    canonical = raw.replace("-", "_")
    legacy_dash = canonical.replace("_", "-")
    values: list[str] = []
    for item in (raw, canonical, legacy_dash):
        if item and item not in values:
            values.append(item)
    return tuple(values)


def is_valid_new_tenant_identifier(value: str | None) -> bool:
    return bool(TENANT_ID_PATTERN.fullmatch(canonical_tenant_identifier(value)))


def is_valid_tenant_identifier_input(value: str | None) -> bool:
    normalized = normalize_tenant_identifier(value)
    return bool(normalized and TENANT_ID_INPUT_PATTERN.fullmatch(normalized))


def resolve_tenant_context_ref(*values: str | None) -> str:
    for value in values:
        normalized = normalize_tenant_identifier(value)
        if normalized:
            return normalized
    return ""


def fetch_tenant_row_any(conn, tenant_ref: str | None):
    candidates = list(build_tenant_identifier_candidates(tenant_ref))
    if not candidates:
        return None

    cache_key = tuple(sorted(candidates))
    now = time.monotonic()
    with _TENANT_ROW_CACHE_LOCK:
        cached = _TENANT_ROW_CACHE.get(cache_key)
        if cached and cached[0] > now:
            payload = cached[1]
            return dict(payload) if isinstance(payload, dict) else None

    primary = candidates[0]
    fallback = candidates[1] if len(candidates) > 1 else primary
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code, tenant_name,
                   COALESCE(is_active, TRUE) AS is_active,
                   COALESCE(is_deleted, FALSE) AS is_deleted
            FROM tenants
            WHERE id::text = ANY(%s::text[])
               OR lower(trim(tenant_code)) = ANY(%s::text[])
            ORDER BY CASE
                WHEN lower(trim(tenant_code)) = %s THEN 0
                WHEN lower(trim(tenant_code)) = %s THEN 1
                ELSE 9
            END
            LIMIT 1
            """,
            (candidates, candidates, primary, fallback),
        )
        row = cur.fetchone()

    row_payload = dict(row) if row else None
    with _TENANT_ROW_CACHE_LOCK:
        _TENANT_ROW_CACHE[cache_key] = (now + _TENANT_ROW_CACHE_TTL_SECONDS, row_payload)
        if len(_TENANT_ROW_CACHE) > _TENANT_ROW_CACHE_MAX_SIZE:
            expired = [key for key, (expires_at, _) in _TENANT_ROW_CACHE.items() if expires_at <= now]
            for key in expired:
                _TENANT_ROW_CACHE.pop(key, None)
            if len(_TENANT_ROW_CACHE) > _TENANT_ROW_CACHE_MAX_SIZE:
                for key, _ in sorted(_TENANT_ROW_CACHE.items(), key=lambda item: item[1][0])[
                    : len(_TENANT_ROW_CACHE) - _TENANT_ROW_CACHE_MAX_SIZE
                ]:
                    _TENANT_ROW_CACHE.pop(key, None)
    return row_payload


def _build_own_tenant_row_from_user(user: dict) -> dict | None:
    tenant_id = str(user.get("tenant_id") or "").strip()
    tenant_code = str(user.get("tenant_code") or "").strip()
    if not tenant_id:
        return None
    return {
        "id": tenant_id,
        "tenant_code": tenant_code,
        "tenant_name": str(user.get("tenant_name") or "").strip(),
        "is_active": bool(user.get("tenant_is_active", True)),
        "is_deleted": bool(user.get("tenant_is_deleted", False)),
    }


def ensure_tenant_active(row: dict | None):
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "TENANT_NOT_FOUND", "message": "tenant not found"},
        )
    if not bool(row.get("is_active", True)) or bool(row.get("is_deleted", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "TENANT_DISABLED", "message": "tenant disabled"},
        )
    return row


def resolve_scoped_tenant(
    conn,
    user: dict,
    *,
    query_tenant_code: str | None = None,
    body_tenant_id: str | None = None,
    header_tenant_id: str | None = None,
    require_dev_context: bool = True,
):
    actor_role = normalize_role(user.get("role"))
    header_ref = normalize_tenant_identifier(header_tenant_id or user.get("active_tenant_id"))
    body_ref = normalize_tenant_identifier(body_tenant_id)
    query_ref = normalize_tenant_identifier(query_tenant_code)
    requested_ref = resolve_tenant_context_ref(header_ref, body_ref, query_ref)

    own_ref = resolve_tenant_context_ref(str(user.get("tenant_id") or ""), user.get("tenant_code"))
    own_row = _build_own_tenant_row_from_user(user)
    if own_row:
        ensure_tenant_active(own_row)
    else:
        own_row = ensure_tenant_active(fetch_tenant_row_any(conn, own_ref))
    own_candidates = set(build_tenant_identifier_candidates(own_ref))
    if str(own_row.get("id") or ""):
        own_candidates.add(str(own_row["id"]))

    if actor_role == ROLE_DEV:
        if not requested_ref:
            if require_dev_context:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"error": "TENANT_CONTEXT_REQUIRED", "message": "작업회사 선택이 필요합니다."},
                )
            return own_row
        requested_candidates = set(build_tenant_identifier_candidates(requested_ref))
        if requested_candidates & own_candidates:
            return own_row
        return ensure_tenant_active(fetch_tenant_row_any(conn, requested_ref))

    if actor_role == ROLE_BRANCH_MANAGER:
        if requested_ref:
            requested_candidates = set(build_tenant_identifier_candidates(requested_ref))
            if not (requested_candidates & own_candidates):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
                )
        return own_row

    if actor_role == ROLE_EMPLOYEE and requested_ref:
        requested_candidates = set(build_tenant_identifier_candidates(requested_ref))
        if not (requested_candidates & own_candidates):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
            )

    # Employee scope is fixed to own tenant.
    return own_row


def enforce_staff_site_scope(
    user: dict,
    *,
    request_site_id: str | None = None,
    request_site_code: str | None = None,
) -> dict[str, str] | None:
    actor_role = normalize_role(user.get("role"))
    if actor_role != ROLE_EMPLOYEE:
        return None

    own_site_id = str(user.get("site_id") or "").strip()
    own_site_code = str(user.get("site_code") or "").strip().upper()
    if not own_site_id or not own_site_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "SITE_SCOPE_REQUIRED", "message": "현장 권한이 설정되지 않았습니다."},
        )

    requested_site_id = str(request_site_id or "").strip()
    requested_site_code = str(request_site_code or "").strip().upper()
    if requested_site_id and requested_site_id != own_site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )
    if requested_site_code and requested_site_code != own_site_code:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )

    return {"site_id": own_site_id, "site_code": own_site_code}
