from __future__ import annotations

from fastapi import APIRouter, Depends

from ...config import settings
from ...deps import apply_rate_limit, require_roles

router = APIRouter(
    prefix="/debug",
    tags=["debug"],
    dependencies=[Depends(apply_rate_limit)],
)


@router.get("/integrations")
def debug_integrations(_user=Depends(require_roles("DEVELOPER"))):
    return {
        "soc_integration_enabled": bool(settings.soc_integration_enabled),
        "soc_base_url": str(settings.soc_base_url or ""),
        "soc_employee_sync_url": str(settings.soc_employee_sync_url or ""),
    }

