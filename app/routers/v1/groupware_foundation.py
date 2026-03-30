from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.groupware_foundation import (
    build_groupware_compatibility_payload,
    build_groupware_foundation_status,
)
from ...utils.permissions import ROLE_DEVELOPER, ROLE_HQ_ADMIN, normalize_user_role

router = APIRouter(
    prefix="/groupware/foundation",
    tags=["groupware-foundation"],
    dependencies=[Depends(apply_rate_limit)],
)

_ALLOWED_FOUNDATION_ROLES = {ROLE_DEVELOPER, ROLE_HQ_ADMIN}


def _ensure_foundation_access(user: dict) -> None:
    if normalize_user_role(user.get("role")) not in _ALLOWED_FOUNDATION_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "그룹웨어 foundation 상태는 관리자만 조회할 수 있습니다."},
        )


@router.get("/status")
def get_groupware_foundation_status(
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_foundation_access(user)
    return build_groupware_foundation_status(conn)


@router.get("/compatibility")
def get_groupware_foundation_compatibility(
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_foundation_access(user)
    return build_groupware_compatibility_payload(conn)
