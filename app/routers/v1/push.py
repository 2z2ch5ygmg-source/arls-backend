from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import PushDeviceRegisterIn, PushDeviceRegisterOut
from ...services.push_notifications import normalize_push_platform, register_push_device

router = APIRouter(prefix="/push", tags=["push"], dependencies=[Depends(apply_rate_limit)])


@router.post("/devices", response_model=PushDeviceRegisterOut)
def register_push_device_endpoint(
    payload: PushDeviceRegisterIn,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = str(user.get("tenant_id") or "").strip()
    user_id = str(user.get("id") or "").strip()
    if not tenant_id or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")

    row = register_push_device(
        conn,
        tenant_id=tenant_id,
        user_id=user_id,
        device_token=payload.token,
        platform=normalize_push_platform(payload.platform),
        device_id=payload.device_id,
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="register failed")
    return PushDeviceRegisterOut(
        id=row["id"],
        platform=row["platform"],
        is_active=True,
        last_seen_at=row["last_seen_at"],
    )
