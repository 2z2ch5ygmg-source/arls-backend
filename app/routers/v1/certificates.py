from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, status

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.certificates_mail import (
    backfill_legacy_employment_certificate_requests,
    list_admin_certificate_requests,
    list_certificate_issue_jobs,
    list_certificate_requests,
    list_certificate_types,
    retry_certificate_issue_job,
)
from ...utils.permissions import ROLE_DEVELOPER, ROLE_HQ_ADMIN, normalize_user_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/certificates", tags=["certificates"], dependencies=[Depends(apply_rate_limit)])


def _ensure_admin(user: dict) -> None:
    if normalize_user_role(user.get("role")) not in {ROLE_DEVELOPER, ROLE_HQ_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "증명서 관리 화면은 관리자만 조회할 수 있습니다."},
        )


def _ensure_employee_context(user: dict) -> str:
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "EMPLOYEE_CONTEXT_REQUIRED", "message": "직원 계정 연결이 필요합니다."},
        )
    return employee_id


@router.get("/types")
def get_certificate_types(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {"items": list_certificate_types(conn, tenant_id=str(tenant.get("id") or "").strip())}


@router.get("/requests")
def get_my_certificate_requests(
    limit: int = Query(default=100, ge=1, le=300),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_context(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    tenant_id = str(tenant.get("id") or "").strip()
    return {
        "items": list_certificate_requests(
            conn,
            tenant_id=tenant_id,
            employee_id=employee_id,
            requester_user_id=str(user.get("id") or "").strip() or None,
            limit=limit,
        )
    }


@router.get("/admin/requests")
def get_admin_certificate_requests(
    limit: int = Query(default=100, ge=1, le=300),
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {
        "items": list_admin_certificate_requests(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            limit=limit,
            status_filter=status_filter,
            query=q,
        )
    }


@router.get("/admin/issue-jobs")
def get_certificate_issue_jobs(
    limit: int = Query(default=100, ge=1, le=300),
    state_filter: str | None = Query(default=None, alias="state"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {
        "items": list_certificate_issue_jobs(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            limit=limit,
            state_filter=state_filter,
        )
    }


@router.post("/admin/backfill-legacy")
def post_certificate_backfill_legacy(
    limit: int = Query(default=200, ge=1, le=1000),
    status_filter: str | None = Query(default=None, alias="status"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return backfill_legacy_employment_certificate_requests(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        actor_user_id=str(user.get("id") or "").strip() or None,
        actor_role=str(user.get("role") or "").strip() or None,
        limit=limit,
        status_filter=status_filter,
    )


@router.post("/admin/issue-jobs/{issue_job_id}/retry")
def post_retry_certificate_issue_job(
    issue_job_id: str,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    result = retry_certificate_issue_job(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        issue_job_id=issue_job_id,
        actor_user_id=str(user.get("id") or "").strip() or None,
        actor_role=str(user.get("role") or "").strip() or None,
    )
    if str(result.get("legacy_source_id") or "").strip():
        from .hr_documents import _process_employment_certificate_issue_job

        background_tasks.add_task(
            _process_employment_certificate_issue_job,
            str(result["legacy_source_id"]),
        )
    return result
