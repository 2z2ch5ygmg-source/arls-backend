from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...config import settings
from ...db import fetch_all, fetch_one
from ...deps import get_db_conn
from ...security import verify_password
from ...utils.credential_norm import build_auth_identifier_candidates

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class ValidateAuthRequest(BaseModel):
    tenant_code: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=255)


def _normalize_tenant_code(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _mask_identifier(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return "-"
    if len(normalized) <= 4:
        return "*" * len(normalized)
    return f"{normalized[:3]}***{normalized[-2:]}"


@router.post("/validate")
def validate_credentials(
    payload: ValidateAuthRequest,
    hr_auth_validate_token: Optional[str] = Header(default=None, alias="HR_AUTH_VALIDATE_TOKEN"),
    conn=Depends(get_db_conn),
):
    tenant_code = _normalize_tenant_code(payload.tenant_code)
    identifier_candidates = build_auth_identifier_candidates(payload.username)
    if not tenant_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )
    if not identifier_candidates:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )

    required_token = str(settings.hr_auth_validate_token or "").strip()
    if required_token and str(hr_auth_validate_token or "").strip() != required_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_VALIDATE_TOKEN", "message": "invalid validate token"},
        )

    tenant = fetch_one(
        conn,
        """
        SELECT id
        FROM tenants
        WHERE lower(tenant_code) = %s
          AND COALESCE(is_active, TRUE) = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        LIMIT 1
        """,
        (tenant_code,),
    )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )

    candidates = fetch_all(
        conn,
        """
        SELECT password_hash
        FROM arls_users
        WHERE tenant_id = %s
          AND lower(regexp_replace(COALESCE(username, ''), '[-\\s]+', '', 'g')) = ANY(%s::text[])
          AND is_active = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        ORDER BY COALESCE(last_login_at, updated_at, created_at) DESC
        LIMIT 20
        """,
        (tenant["id"], list(identifier_candidates)),
    )
    matched = any(verify_password(payload.password, row.get("password_hash") or "") for row in candidates)
    if str(settings.environment or "").strip().lower() != "production":
        logger.info(
            "auth.validate tenant_id=%s identifiers=%s candidate_count=%s matched=%s",
            tenant["id"],
            ",".join(_mask_identifier(value) for value in identifier_candidates),
            len(candidates),
            bool(matched),
        )
    if not matched:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )

    return {"success": True}
