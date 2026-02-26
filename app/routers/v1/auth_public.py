from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ...config import settings
from ...db import fetch_one
from ...deps import get_db_conn
from ...security import verify_password
from ...utils.credential_norm import normalize_auth_identifier

router = APIRouter(prefix="/auth", tags=["auth"])


class ValidateAuthRequest(BaseModel):
    tenant_code: str = Field(min_length=1, max_length=64)
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=255)


def _normalize_tenant_code(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


@router.post("/validate")
def validate_credentials(
    payload: ValidateAuthRequest,
    hr_auth_validate_token: Optional[str] = Header(default=None, alias="HR_AUTH_VALIDATE_TOKEN"),
    conn=Depends(get_db_conn),
):
    tenant_code = _normalize_tenant_code(payload.tenant_code)
    normalized_username = normalize_auth_identifier(payload.username)
    if not tenant_code:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )
    if not normalized_username:
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

    user = fetch_one(
        conn,
        """
        SELECT password_hash
        FROM arls_users
        WHERE tenant_id = %s
          AND lower(regexp_replace(COALESCE(username, ''), '[-\\s]+', '', 'g')) = lower(%s)
          AND is_active = TRUE
          AND COALESCE(is_deleted, FALSE) = FALSE
        LIMIT 1
        """,
        (tenant["id"], normalized_username),
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "INVALID_CREDENTIALS", "message": "invalid credentials"},
        )

    return {"success": True}
