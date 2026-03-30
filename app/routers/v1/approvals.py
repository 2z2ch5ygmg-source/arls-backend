from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.approval_engine import (
    APPROVAL_FORM_BY_KEY,
    create_approval_document,
    fetch_approval_document_detail,
    list_approval_documents,
    list_approval_forms,
    list_approval_review_queue,
    record_approval_action,
)
from ...utils.permissions import is_super_admin, normalize_user_role

router = APIRouter(prefix="/approvals", tags=["approvals"], dependencies=[Depends(apply_rate_limit)])


class ApprovalDocumentCreateIn(BaseModel):
    form_key: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    watcher_user_ids: list[str] = Field(default_factory=list)
    comment_text: str | None = Field(default=None, max_length=1000)
    submit: bool = True
    employee_id: str | None = Field(default=None, max_length=64)
    site_id: str | None = Field(default=None, max_length=64)
    company_id: str | None = Field(default=None, max_length=64)

    @field_validator("form_key", mode="before")
    @classmethod
    def _normalize_form_key(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in APPROVAL_FORM_BY_KEY:
            raise ValueError("unsupported form_key")
        return normalized


class ApprovalActionIn(BaseModel):
    action_type: str = Field(min_length=1, max_length=32)
    comment_text: str | None = Field(default=None, max_length=1000)

    @field_validator("action_type", mode="before")
    @classmethod
    def _normalize_action_type(cls, value: str | None) -> str:
        return str(value or "").strip().lower()


def _resolve_target_tenant(conn, user, tenant_code: str | None):
    own_tenant_id = str(user.get("tenant_id") or "").strip()
    own_tenant_code = str(user.get("tenant_code") or "").strip().upper()
    requested_tenant_code = str(tenant_code or "").strip().upper()

    if not is_super_admin(user.get("role")):
        if requested_tenant_code and requested_tenant_code != own_tenant_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant mismatch")
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    if not requested_tenant_code:
        return {"id": own_tenant_id, "tenant_code": own_tenant_code}

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, tenant_code
            FROM tenants
            WHERE tenant_code = %s
              AND COALESCE(is_active, TRUE) = TRUE
            LIMIT 1
            """,
            (requested_tenant_code,),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return row


def _can_access_document(user: dict, document: dict[str, Any]) -> bool:
    if is_super_admin(user.get("role")):
        return True
    if normalize_user_role(user.get("role")) == "hq_admin":
        return True
    user_id = str(user.get("id") or "").strip()
    if user_id and str(document.get("requester_user_id") or "").strip() == user_id:
        return True
    for step in document.get("steps") or []:
        if str(step.get("approver_user_id") or "").strip() == user_id:
            return True
    return False


@router.get("/forms")
def get_approval_forms(
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    return {
        "items": list_approval_forms(conn, tenant_id=str(tenant["id"]), actor_user_id=str(user.get("id") or "").strip() or None)
    }


@router.get("/documents")
def get_approval_documents(
    scope: str = Query(default="mine"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=300),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    return {
        "items": list_approval_documents(
            conn,
            tenant_id=str(tenant["id"]),
            current_user=user,
            scope=scope,
            limit=limit,
            status_filter=status_filter,
        )
    }


@router.get("/review-queue")
def get_approval_review_queue(
    limit: int = Query(default=100, ge=1, le=300),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    return {
        "items": list_approval_review_queue(
            conn,
            tenant_id=str(tenant["id"]),
            reviewer_user_id=str(user.get("id") or "").strip(),
            limit=limit,
        )
    }


@router.get("/documents/{document_id}")
def get_approval_document(
    document_id: str,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    document = fetch_approval_document_detail(conn, tenant_id=str(tenant["id"]), document_id=document_id)
    if not _can_access_document(user, document):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
    return document


@router.post("/documents")
def post_approval_document(
    payload: ApprovalDocumentCreateIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    document = create_approval_document(
        conn,
        tenant_id=str(tenant["id"]),
        form_key=payload.form_key,
        title=payload.title,
        requester_user_id=str(user.get("id") or "").strip() or None,
        requester_role=str(user.get("role") or "").strip() or None,
        employee_id=payload.employee_id or str(user.get("employee_id") or "").strip() or None,
        site_id=payload.site_id or str(user.get("site_id") or "").strip() or None,
        company_id=payload.company_id,
        payload=payload.payload,
        watcher_user_ids=payload.watcher_user_ids,
        submit=payload.submit,
        comment_text=payload.comment_text,
    )
    return document


@router.post("/documents/{document_id}/actions")
def post_approval_document_action(
    document_id: str,
    payload: ApprovalActionIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_target_tenant(conn, user, tenant_code)
    return record_approval_action(
        conn,
        tenant_id=str(tenant["id"]),
        document_id=document_id,
        actor_user_id=str(user.get("id") or "").strip(),
        actor_role=str(user.get("role") or "").strip() or None,
        action_type=payload.action_type,
        comment_text=payload.comment_text,
    )
