from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field, field_validator

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.messenger import (
    ALLOWED_ANNOUNCEMENT_SCOPES,
    ALLOWED_CONVERSATION_TYPES,
    ALLOWED_MESSAGE_TYPES,
    ALLOWED_PRESENCE_STATUSES,
    add_message_reaction,
    create_conversation,
    create_message,
    delete_message,
    get_conversation_detail,
    list_announcement_rooms,
    list_conversations,
    list_messages,
    list_presence,
    mark_conversation_read,
    remove_message_reaction,
    search_messages,
    update_message,
    upsert_presence_session,
)
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/messenger", tags=["messenger"], dependencies=[Depends(apply_rate_limit)])


class ConversationCreateIn(BaseModel):
    conversation_type: str = Field(default="group", min_length=2, max_length=24)
    member_user_ids: list[str] = Field(default_factory=list)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=300)
    site_id: str | None = Field(default=None, max_length=64)
    meta_json: dict[str, Any] = Field(default_factory=dict)
    announcement_room_key: str | None = Field(default=None, max_length=64)
    announcement_scope_type: str | None = Field(default=None, max_length=16)

    @field_validator("conversation_type", mode="before")
    @classmethod
    def _normalize_conversation_type(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_CONVERSATION_TYPES:
            raise ValueError("unsupported conversation_type")
        return normalized

    @field_validator("announcement_scope_type", mode="before")
    @classmethod
    def _normalize_announcement_scope_type(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_ANNOUNCEMENT_SCOPES:
            raise ValueError("unsupported announcement_scope_type")
        return normalized


class MessageCreateIn(BaseModel):
    body: str | None = Field(default=None, max_length=4000)
    message_type: str = Field(default="text", min_length=1, max_length=24)
    parent_message_id: str | None = Field(default=None, max_length=64)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    mentioned_user_ids: list[str] = Field(default_factory=list)
    attachment_object_ids: list[str] = Field(default_factory=list)
    poll_question: str | None = Field(default=None, max_length=400)
    poll_options: list[str] = Field(default_factory=list)

    @field_validator("message_type", mode="before")
    @classmethod
    def _normalize_message_type(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_MESSAGE_TYPES:
            raise ValueError("unsupported message_type")
        return normalized


class MessageUpdateIn(BaseModel):
    body: str = Field(min_length=1, max_length=4000)
    mentioned_user_ids: list[str] = Field(default_factory=list)


class ConversationReadIn(BaseModel):
    message_id: str | None = Field(default=None, max_length=64)


class ReactionIn(BaseModel):
    reaction: str = Field(min_length=1, max_length=16)


class PresenceSessionIn(BaseModel):
    session_key: str = Field(min_length=1, max_length=120)
    status: str = Field(default="online", min_length=1, max_length=16)
    device_type: str = Field(default="web", min_length=1, max_length=24)
    meta_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_PRESENCE_STATUSES:
            raise ValueError("unsupported status")
        return normalized


def _resolve_tenant(conn, user: dict, x_tenant_id: str | None):
    return resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)


@router.get("/conversations")
def get_conversations(
    limit: int = Query(default=100, ge=1, le=300),
    conversation_type: str | None = Query(default=None, alias="type"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return {
        "items": list_conversations(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            current_user=user,
            limit=limit,
            conversation_type=conversation_type,
        )
    }


@router.post("/conversations")
def post_conversation(
    payload: ConversationCreateIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return create_conversation(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        current_user=user,
        conversation_type=payload.conversation_type,
        member_user_ids=payload.member_user_ids,
        title=payload.title,
        description=payload.description,
        site_id=payload.site_id,
        meta_json=payload.meta_json,
        announcement_room_key=payload.announcement_room_key,
        announcement_scope_type=payload.announcement_scope_type,
    )


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return get_conversation_detail(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        conversation_id=conversation_id,
        current_user=user,
    )


@router.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=300),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return {
        "items": list_messages(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            conversation_id=conversation_id,
            current_user=user,
            limit=limit,
        )
    }


@router.post("/conversations/{conversation_id}/messages")
def post_conversation_message(
    conversation_id: str,
    payload: MessageCreateIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return create_message(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        conversation_id=conversation_id,
        current_user=user,
        body=payload.body,
        message_type=payload.message_type,
        parent_message_id=payload.parent_message_id,
        payload_json=payload.payload_json,
        mentioned_user_ids=payload.mentioned_user_ids,
        attachment_object_ids=payload.attachment_object_ids,
        poll_question=payload.poll_question,
        poll_options=payload.poll_options,
    )


@router.post("/conversations/{conversation_id}/read")
def post_conversation_read(
    conversation_id: str,
    payload: ConversationReadIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return mark_conversation_read(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        conversation_id=conversation_id,
        current_user=user,
        message_id=payload.message_id,
    )


@router.patch("/messages/{message_id}")
def patch_message(
    message_id: str,
    payload: MessageUpdateIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return update_message(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        message_id=message_id,
        current_user=user,
        body=payload.body,
        mentioned_user_ids=payload.mentioned_user_ids,
    )


@router.delete("/messages/{message_id}")
def delete_message_route(
    message_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return delete_message(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        message_id=message_id,
        current_user=user,
    )


@router.post("/messages/{message_id}/reactions")
def post_message_reaction(
    message_id: str,
    payload: ReactionIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return add_message_reaction(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        message_id=message_id,
        current_user=user,
        reaction=payload.reaction,
    )


@router.delete("/messages/{message_id}/reactions/{reaction}")
def delete_message_reaction(
    message_id: str,
    reaction: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return remove_message_reaction(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        message_id=message_id,
        current_user=user,
        reaction=reaction,
    )


@router.get("/search/messages")
def get_message_search(
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=50, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return {
        "items": search_messages(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            current_user=user,
            query=q,
            limit=limit,
        )
    }


@router.put("/presence/session")
def put_presence_session(
    payload: PresenceSessionIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return upsert_presence_session(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        current_user=user,
        session_key=payload.session_key,
        status_value=payload.status,
        device_type=payload.device_type,
        meta_json=payload.meta_json,
    )


@router.get("/presence")
def get_presence(
    conversation_id: str | None = Query(default=None),
    user_ids: str | None = Query(default=None, description="comma-separated user ids"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    resolved_user_ids = [item.strip() for item in str(user_ids or "").split(",") if item.strip()]
    return {
        "items": list_presence(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            current_user=user,
            conversation_id=conversation_id,
            user_ids=resolved_user_ids,
        )
    }


@router.get("/announcement-rooms")
def get_announcement_rooms(
    active_only: bool = Query(default=True),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return {
        "items": list_announcement_rooms(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            current_user=user,
            active_only=active_only,
        )
    }
