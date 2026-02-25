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
    hr_reset_token = str(getattr(settings, "hr_reset_token", "") or "")
    return {
        "soc_integration_enabled": bool(settings.soc_integration_enabled),
        "soc_base_url": str(settings.soc_base_url or ""),
        "soc_employee_sync_url": str(settings.soc_employee_sync_url or ""),
        "soc_site_sync_url": str(settings.soc_site_sync_url or ""),
        "soc_reset_url": str(settings.soc_reset_url or ""),
        "hr_reset_token_set": bool(hr_reset_token.strip()),
        "hr_reset_token_len": len(hr_reset_token.strip()),
    }
