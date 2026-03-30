from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.certificates_mail import (
    list_mail_accounts,
    list_mail_delivery_events,
    list_mail_sender_profiles,
    list_mail_templates,
    list_outbound_mail_jobs,
    retry_outbound_mail_job,
    upsert_mail_sender_profile,
    upsert_mail_template,
)
from ...utils.permissions import ROLE_DEVELOPER, ROLE_HQ_ADMIN, normalize_user_role
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/mail", tags=["mail"], dependencies=[Depends(apply_rate_limit)])


class MailSenderProfileUpsertIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    reply_to_email: str | None = Field(default=None, max_length=255)
    from_email: str | None = Field(default=None, max_length=255)
    is_default: bool = False

    @field_validator("display_name", mode="before")
    @classmethod
    def _normalize_display_name(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("display_name is required")
        return normalized


class MailTemplateUpsertIn(BaseModel):
    subject_template: str = Field(min_length=1, max_length=255)
    body_template: str = Field(min_length=1, max_length=8000)
    is_active: bool = True

    @field_validator("subject_template", "body_template", mode="before")
    @classmethod
    def _normalize_text(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("template field is required")
        return normalized


def _ensure_mail_admin(user: dict) -> None:
    if normalize_user_role(user.get("role")) not in {ROLE_DEVELOPER, ROLE_HQ_ADMIN}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "메일 설정은 관리자만 조회할 수 있습니다."},
        )


@router.get("/accounts")
def get_mail_accounts(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {"items": list_mail_accounts(conn, tenant_id=str(tenant.get("id") or "").strip())}


@router.get("/sender-profiles")
def get_mail_sender_profiles(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {"items": list_mail_sender_profiles(conn, tenant_id=str(tenant.get("id") or "").strip())}


@router.put("/sender-profiles/{profile_key}")
def put_mail_sender_profile(
    profile_key: str,
    payload: MailSenderProfileUpsertIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return upsert_mail_sender_profile(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        profile_key=str(profile_key or "").strip().lower(),
        display_name=payload.display_name,
        reply_to_email=payload.reply_to_email,
        from_email=payload.from_email,
        is_default=payload.is_default,
        actor_user_id=str(user.get("id") or "").strip() or None,
    )


@router.get("/templates")
def get_mail_templates(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {"items": list_mail_templates(conn, tenant_id=str(tenant.get("id") or "").strip())}


@router.put("/templates/{template_key}")
def put_mail_template(
    template_key: str,
    payload: MailTemplateUpsertIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return upsert_mail_template(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        template_key=str(template_key or "").strip().lower(),
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        is_active=payload.is_active,
        actor_user_id=str(user.get("id") or "").strip() or None,
    )


@router.get("/jobs")
def get_mail_jobs(
    limit: int = Query(default=100, ge=1, le=300),
    state_filter: str | None = Query(default=None, alias="state"),
    source_type: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {
        "items": list_outbound_mail_jobs(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            limit=limit,
            state_filter=state_filter,
            source_type=source_type,
        )
    }


@router.get("/jobs/{job_id}/events")
def get_mail_job_events(
    job_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return {"items": list_mail_delivery_events(conn, tenant_id=str(tenant.get("id") or "").strip(), job_id=job_id)}


@router.post("/jobs/{job_id}/retry")
def post_retry_mail_job(
    job_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_mail_admin(user)
    tenant = resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)
    return retry_outbound_mail_job(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        job_id=job_id,
        actor_user_id=str(user.get("id") or "").strip() or None,
        actor_role=str(user.get("role") or "").strip() or None,
    )
