from fastapi import APIRouter, Depends
from app.config import settings
from app.dependencies import require_roles

router = APIRouter(
    prefix="/debug",
    tags=["debug"],
)

@router.get("/integrations")
def debug_integrations(_user=Depends(require_roles("DEVELOPER"))):
    """
    DEV 전용 통합 설정 확인용 엔드포인트

    반환:
    - soc_integration_enabled
    - soc_base_url
    - soc_employee_sync_url
    - soc_site_sync_url
    """
    return {
        "success": True,
        "data": {
            "soc_integration_enabled": bool(settings.soc_integration_enabled),
            "soc_base_url": settings.soc_base_url,
            "soc_employee_sync_url": settings.soc_employee_sync_url,
            "soc_site_sync_url": settings.soc_site_sync_url,
        },
        "error": None,
    }
