from __future__ import annotations

from fastapi import APIRouter, Depends

from ...deps import apply_rate_limit, get_current_user
from ...schemas import MeResponse
from ...utils.permissions import resolve_permission_group, to_role_enum

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeResponse, dependencies=[Depends(apply_rate_limit)])
def me(user=Depends(get_current_user)):
    return MeResponse(
        user_id=user["id"],
        tenant_id=user["tenant_id"],
        site_code=user.get("site_code"),
        role=to_role_enum(user.get("role")),
        group=resolve_permission_group(user.get("role")),
    )
