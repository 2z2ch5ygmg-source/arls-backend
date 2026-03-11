from __future__ import annotations

from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ...config import settings
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.apple_weekly_truth import (
    APPLE_TENANT_CODE,
    build_apple_weekly_truth_contract,
    build_apple_weekly_truth_failure_contract,
    normalize_week_start,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/apple-weekly", tags=["apple-weekly"], dependencies=[Depends(apply_rate_limit)])
ALLOWED_ROLES = {ROLE_DEV, ROLE_BRANCH_MANAGER}
logger = logging.getLogger(__name__)


def _require_contract_access(user: dict) -> None:
    if normalize_role(user.get("role")) not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "접근 권한이 없습니다."},
        )


def _resolve_target_tenant(conn, user: dict, tenant_code: str | None):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    tenant_code_text = str(tenant.get("tenant_code") or "").strip().upper()
    if tenant_code_text != APPLE_TENANT_CODE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "Apple Weekly truth contract는 APPLE 테넌트에서만 사용할 수 있습니다."},
        )
    return tenant


@router.get("/truth")
def get_apple_weekly_truth(
    week_start: date = Query(..., description="Any date within the target week; normalized to Monday in KST."),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_contract_access(user)
    if not settings.apple_weekly_truth_enabled:
        failure_contract = build_apple_weekly_truth_failure_contract(
            tenant_code=tenant_code or APPLE_TENANT_CODE,
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            message="Apple Weekly truth service is disabled by rollout flag.",
            debug_enabled=False,
        )
        failure_contract["service_state"] = "contract_failure"
        failure_contract["failure_mode"] = {
            "state": "contract_failure",
            "retryable": False,
            "message": "Apple Weekly truth service is disabled by rollout flag.",
        }
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=failure_contract)
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    try:
        return build_apple_weekly_truth_contract(
            conn,
            tenant_row=tenant,
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            include_debug=False,
        )
    except LookupError as exc:
        if str(exc) == "site_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "SITE_NOT_FOUND", "message": "site_code를 찾을 수 없습니다."},
            ) from exc
        raise
    except Exception as exc:
        logger.exception(
            "apple_weekly_truth_route_failed",
            extra={
                "tenant_code": str(tenant.get("tenant_code") or "").strip().upper(),
                "week_start": normalize_week_start(week_start).isoformat(),
                "site_code": str(site_code or "").strip().upper() or None,
            },
            exc_info=exc,
        )
        failure_contract = build_apple_weekly_truth_failure_contract(
            tenant_code=str(tenant.get("tenant_code") or "").strip().upper(),
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            message="Apple Weekly truth generation failed inside ARLS.",
            debug_enabled=False,
        )
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=failure_contract)


@router.get("/truth/debug")
def get_apple_weekly_truth_debug(
    week_start: date = Query(..., description="Any date within the target week; normalized to Monday in KST."),
    site_code: str | None = Query(default=None, max_length=64),
    tenant_code: str | None = Query(default=None, max_length=64),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _require_contract_access(user)
    if not settings.apple_weekly_truth_enabled:
        failure_contract = build_apple_weekly_truth_failure_contract(
            tenant_code=tenant_code or APPLE_TENANT_CODE,
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            message="Apple Weekly truth service is disabled by rollout flag.",
            debug_enabled=True,
        )
        failure_contract["service_state"] = "contract_failure"
        failure_contract["failure_mode"] = {
            "state": "contract_failure",
            "retryable": False,
            "message": "Apple Weekly truth service is disabled by rollout flag.",
        }
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=failure_contract)
    if not settings.apple_weekly_truth_debug_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": "debug endpoint is disabled"},
        )
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    try:
        return build_apple_weekly_truth_contract(
            conn,
            tenant_row=tenant,
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            include_debug=True,
        )
    except LookupError as exc:
        if str(exc) == "site_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"error": "SITE_NOT_FOUND", "message": "site_code를 찾을 수 없습니다."},
            ) from exc
        raise
    except Exception as exc:
        logger.exception(
            "apple_weekly_truth_debug_route_failed",
            extra={
                "tenant_code": str(tenant.get("tenant_code") or "").strip().upper(),
                "week_start": normalize_week_start(week_start).isoformat(),
                "site_code": str(site_code or "").strip().upper() or None,
            },
            exc_info=exc,
        )
        failure_contract = build_apple_weekly_truth_failure_contract(
            tenant_code=str(tenant.get("tenant_code") or "").strip().upper(),
            week_start=normalize_week_start(week_start),
            site_code=site_code,
            message="Apple Weekly truth debug generation failed inside ARLS.",
            debug_enabled=True,
        )
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=failure_contract)
