from __future__ import annotations

import mimetypes
from typing import Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status

from ..deps import apply_rate_limit, get_current_user, get_db_conn
from ..services.announcement_service import (
    AnnouncementNotFound,
    AnnouncementValidationError,
    create_announcement,
    create_announcement_attachment,
    delete_announcement,
    get_announcement_detail,
    list_announcements,
    update_announcement,
    vote_announcement,
)
from ..utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, normalize_role
from ..utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/announcements", tags=["announcements"], dependencies=[Depends(apply_rate_limit)])


def _resolve_tenant_id(conn, user: dict[str, Any]) -> str:
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=user.get("active_tenant_id"),
        require_dev_context=True,
    )
    return str(tenant.get("id") or "").strip()


def _ensure_announcement_write_permission(user: dict[str, Any]) -> None:
    if normalize_role(user.get("role")) not in {ROLE_DEV, ROLE_BRANCH_MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "FORBIDDEN", "message": "본사 관리자만 공지를 발행할 수 있습니다."},
        )


def _map_service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AnnouncementNotFound):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "NOT_FOUND", "message": str(exc) or "해당 공지를 찾을 수 없습니다."},
        )
    if isinstance(exc, AnnouncementValidationError) or isinstance(exc, ValueError):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": str(exc) or "입력값을 확인해주세요."},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "ANNOUNCEMENT_ERROR", "message": "공지 처리 중 오류가 발생했습니다."},
    )


@router.get("")
def list_announcement_items(
    category: str = Query(default="all"),
    cat: str | None = Query(default=None),
    q: str = Query(default="", max_length=120),
    search: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=80, ge=1, le=200),
    scope: str = Query(default="all"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = _resolve_tenant_id(conn, user)
    return list_announcements(
        conn,
        tenant_id=tenant_id,
        user=user,
        category=cat or category,
        q=search if search is not None else q,
        limit=limit,
        scope=scope,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_announcement_item(
    payload: dict[str, Any] = Body(default_factory=dict),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_announcement_write_permission(user)
    tenant_id = _resolve_tenant_id(conn, user)
    try:
        detail = create_announcement(conn, tenant_id=tenant_id, user=user, payload=payload or {})
    except Exception as exc:
        raise _map_service_error(exc) from exc
    return {
        "ok": True,
        "announcement_id": detail.get("id"),
        "notice": detail,
        "announcement": detail,
        **detail,
    }


@router.post("/attachments", status_code=status.HTTP_201_CREATED)
async def upload_announcement_attachment(
    file: UploadFile | None = File(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_announcement_write_permission(user)
    tenant_id = _resolve_tenant_id(conn, user)
    actor_id = str(user.get("id") or "").strip()
    if file is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "이미지 파일을 선택해 주세요."},
        )
    file_name = str(file.filename or "notice-image").strip() or "notice-image"
    mime_type = str(file.content_type or mimetypes.guess_type(file_name)[0] or "").strip().lower()
    raw_bytes = await file.read()
    try:
        return create_announcement_attachment(
            conn,
            tenant_id=tenant_id,
            actor_id=actor_id,
            file_name=file_name,
            mime_type=mime_type,
            raw_bytes=raw_bytes,
        )
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.get("/{announcement_id}")
def get_announcement_item(
    announcement_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = _resolve_tenant_id(conn, user)
    try:
        detail = get_announcement_detail(conn, tenant_id=tenant_id, announcement_id=announcement_id, user=user)
    except Exception as exc:
        raise _map_service_error(exc) from exc
    return {"notice": detail, "announcement": detail, **detail}


@router.patch("/{announcement_id}")
def update_announcement_item(
    announcement_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_announcement_write_permission(user)
    tenant_id = _resolve_tenant_id(conn, user)
    try:
        detail = update_announcement(conn, tenant_id=tenant_id, announcement_id=announcement_id, user=user, payload=payload or {})
    except Exception as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "notice": detail, "announcement": detail, **detail}


@router.post("/{announcement_id}/polls/{poll_id}/vote")
def vote_announcement_poll_item(
    announcement_id: str,
    poll_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant_id = _resolve_tenant_id(conn, user)
    raw_option_ids = payload.get("option_ids") or payload.get("optionIds") or []
    if not isinstance(raw_option_ids, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "VALIDATION_ERROR", "message": "선택지 형식이 올바르지 않습니다."},
        )
    try:
        detail = vote_announcement(
            conn,
            tenant_id=tenant_id,
            announcement_id=announcement_id,
            poll_id=poll_id,
            option_ids=[str(item or "").strip() for item in raw_option_ids],
            user=user,
        )
    except Exception as exc:
        raise _map_service_error(exc) from exc
    return {"ok": True, "notice": detail, "announcement": detail, **detail}


@router.delete("/{announcement_id}")
def delete_announcement_item(
    announcement_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_announcement_write_permission(user)
    tenant_id = _resolve_tenant_id(conn, user)
    try:
        return delete_announcement(conn, tenant_id=tenant_id, announcement_id=announcement_id)
    except Exception as exc:
        raise _map_service_error(exc) from exc


@router.post("/{announcement_id}/delete")
def delete_announcement_item_post(
    announcement_id: str,
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    return delete_announcement_item(announcement_id, conn=conn, user=user)
