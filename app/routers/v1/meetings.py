from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field, field_validator

from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.meetings import (
    ALLOWED_MEDIA_BACKENDS,
    ALLOWED_ROLLOUT_STATUSES,
    add_meeting_chat_link,
    add_meeting_participants,
    create_meeting_room,
    end_meeting_session,
    get_meeting_rollout_status,
    get_meeting_room_by_key,
    get_meeting_room_detail,
    join_meeting_session,
    list_meeting_rooms,
    record_meeting_event,
    record_rollout_check,
    start_meeting_session,
    leave_meeting_session,
)
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/meetings", tags=["meetings"], dependencies=[Depends(apply_rate_limit)])


class MeetingRoomCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    participant_user_ids: list[str] = Field(default_factory=list)
    scheduled_for: datetime | None = None
    room_key: str | None = Field(default=None, max_length=64)
    settings_json: dict[str, Any] = Field(default_factory=dict)
    linked_conversation_id: str | None = Field(default=None, max_length=64)
    start_now: bool = False


class MeetingParticipantsIn(BaseModel):
    participant_user_ids: list[str] = Field(default_factory=list)


class MeetingChatLinkIn(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=64)
    link_type: str = Field(default="primary", min_length=1, max_length=32)


class MeetingSessionStartIn(BaseModel):
    media_backend: str = Field(default="pion", min_length=1, max_length=24)
    session_key: str | None = Field(default=None, max_length=64)
    meta_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("media_backend", mode="before")
    @classmethod
    def _normalize_media_backend(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_MEDIA_BACKENDS:
            raise ValueError("unsupported media_backend")
        return normalized


class MeetingJoinIn(BaseModel):
    reconnect: bool = False
    device_type: str = Field(default="web", min_length=1, max_length=24)


class MeetingEventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=40)
    payload_json: dict[str, Any] = Field(default_factory=dict)


class MeetingRolloutCheckIn(BaseModel):
    environment_key: str = Field(default="default", min_length=1, max_length=40)
    check_type: str = Field(min_length=1, max_length=40)
    status: str = Field(min_length=1, max_length=16)
    summary: str = Field(min_length=1, max_length=300)
    detail_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", mode="before")
    @classmethod
    def _normalize_status(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in ALLOWED_ROLLOUT_STATUSES:
            raise ValueError("unsupported status")
        return normalized


def _resolve_tenant(conn, user: dict, x_tenant_id: str | None):
    return resolve_scoped_tenant(conn, user, header_tenant_id=x_tenant_id, require_dev_context=True)


@router.get("/rooms")
def get_meeting_rooms(
    limit: int = Query(default=100, ge=1, le=300),
    state_filter: str | None = Query(default=None, alias="state"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return {
        "items": list_meeting_rooms(
            conn,
            tenant_id=str(tenant.get("id") or "").strip(),
            current_user=user,
            limit=limit,
            state_filter=state_filter,
        )
    }


@router.post("/rooms")
def post_meeting_room(
    payload: MeetingRoomCreateIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return create_meeting_room(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        current_user=user,
        title=payload.title,
        participant_user_ids=payload.participant_user_ids,
        scheduled_for=payload.scheduled_for,
        room_key=payload.room_key,
        settings_json=payload.settings_json,
        linked_conversation_id=payload.linked_conversation_id,
        start_now=payload.start_now,
    )


@router.get("/rooms/{room_id}")
def get_meeting_room(
    room_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return get_meeting_room_detail(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        current_user=user,
    )


@router.get("/links/{room_key}")
def get_meeting_room_link(
    room_key: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return get_meeting_room_by_key(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_key=room_key,
        current_user=user,
    )


@router.post("/rooms/{room_id}/participants")
def post_meeting_participants(
    room_id: str,
    payload: MeetingParticipantsIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return add_meeting_participants(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        current_user=user,
        participant_user_ids=payload.participant_user_ids,
    )


@router.post("/rooms/{room_id}/chat-links")
def post_meeting_chat_link(
    room_id: str,
    payload: MeetingChatLinkIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return add_meeting_chat_link(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        current_user=user,
        conversation_id=payload.conversation_id,
        link_type=payload.link_type,
    )


@router.post("/rooms/{room_id}/sessions/start")
def post_meeting_session_start(
    room_id: str,
    payload: MeetingSessionStartIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return start_meeting_session(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        current_user=user,
        media_backend=payload.media_backend,
        session_key=payload.session_key,
        meta_json=payload.meta_json,
    )


@router.post("/rooms/{room_id}/sessions/{session_id}/join")
def post_meeting_session_join(
    room_id: str,
    session_id: str,
    payload: MeetingJoinIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return join_meeting_session(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        session_id=session_id,
        current_user=user,
        reconnect=payload.reconnect,
        device_type=payload.device_type,
    )


@router.post("/rooms/{room_id}/sessions/{session_id}/leave")
def post_meeting_session_leave(
    room_id: str,
    session_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return leave_meeting_session(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        session_id=session_id,
        current_user=user,
    )


@router.post("/rooms/{room_id}/sessions/{session_id}/events")
def post_meeting_event(
    room_id: str,
    session_id: str,
    payload: MeetingEventIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return record_meeting_event(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        session_id=session_id,
        current_user=user,
        event_type=payload.event_type,
        payload_json=payload.payload_json,
    )


@router.post("/rooms/{room_id}/sessions/{session_id}/end")
def post_meeting_session_end(
    room_id: str,
    session_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return end_meeting_session(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        room_id=room_id,
        session_id=session_id,
        current_user=user,
    )


@router.get("/rollout/status")
def get_meetings_rollout_status(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return get_meeting_rollout_status(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        current_user=user,
    )


@router.post("/rollout/checks")
def post_meetings_rollout_check(
    payload: MeetingRolloutCheckIn,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = _resolve_tenant(conn, user, x_tenant_id)
    return record_rollout_check(
        conn,
        tenant_id=str(tenant.get("id") or "").strip(),
        current_user=user,
        environment_key=payload.environment_key,
        check_type=payload.check_type,
        status_value=payload.status,
        summary=payload.summary,
        detail_json=payload.detail_json,
    )
