from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status

from .groupware_foundation import GroupwareAuditService, GroupwareNotificationDispatcher
from ..utils.permissions import is_super_admin, normalize_user_role

CONVERSATION_TYPE_DM = "dm"
CONVERSATION_TYPE_GROUP = "group"
CONVERSATION_TYPE_ANNOUNCEMENT = "announcement"
ALLOWED_CONVERSATION_TYPES = {
    CONVERSATION_TYPE_DM,
    CONVERSATION_TYPE_GROUP,
    CONVERSATION_TYPE_ANNOUNCEMENT,
}

ANNOUNCEMENT_SCOPE_TENANT = "tenant"
ANNOUNCEMENT_SCOPE_SITE = "site"
ALLOWED_ANNOUNCEMENT_SCOPES = {
    ANNOUNCEMENT_SCOPE_TENANT,
    ANNOUNCEMENT_SCOPE_SITE,
}

MESSAGE_TYPE_TEXT = "text"
MESSAGE_TYPE_FILE = "file"
MESSAGE_TYPE_POLL = "poll"
ALLOWED_MESSAGE_TYPES = {
    MESSAGE_TYPE_TEXT,
    MESSAGE_TYPE_FILE,
    MESSAGE_TYPE_POLL,
}

MEMBERSHIP_ROLE_OWNER = "owner"
MEMBERSHIP_ROLE_ADMIN = "admin"
MEMBERSHIP_ROLE_MEMBER = "member"
ALLOWED_MEMBERSHIP_ROLES = {
    MEMBERSHIP_ROLE_OWNER,
    MEMBERSHIP_ROLE_ADMIN,
    MEMBERSHIP_ROLE_MEMBER,
}

PRESENCE_STATUS_ONLINE = "online"
PRESENCE_STATUS_AWAY = "away"
PRESENCE_STATUS_BUSY = "busy"
PRESENCE_STATUS_OFFLINE = "offline"
ALLOWED_PRESENCE_STATUSES = {
    PRESENCE_STATUS_ONLINE,
    PRESENCE_STATUS_AWAY,
    PRESENCE_STATUS_BUSY,
    PRESENCE_STATUS_OFFLINE,
}

PRESENCE_ACTIVE_WINDOW = timedelta(minutes=3)

REACTION_PATTERN = re.compile(r"^.{1,16}$", re.UNICODE)
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _json_dumps_list(value: list[Any] | None) -> str:
    return json.dumps(value or [], ensure_ascii=False, default=str)


def _coerce_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
        except Exception:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _run_noncritical_db_step(
    conn,
    *,
    step_name: str,
    callback,
    fallback=None,
):
    savepoint = f"messenger_sp_{uuid.uuid4().hex}"
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {savepoint}")
    try:
        result = callback()
    except Exception:
        logger.exception("[MESSENGER] non-critical step failed step=%s", step_name)
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        return fallback
    with conn.cursor() as cur:
        cur.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result


def _http_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": "MESSENGER_ERROR", "message": message},
    )


def _normalize_choice(value: str | None, *, allowed: set[str], field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise _http_error(status.HTTP_400_BAD_REQUEST, f"{field_name} 값이 올바르지 않습니다.")
    return normalized


def _normalize_reaction(value: str | None) -> str:
    normalized = str(value or "").strip()
    if not REACTION_PATTERN.fullmatch(normalized):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "reaction 값이 올바르지 않습니다.")
    return normalized


def _normalize_uuid_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        item = str(raw or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _normalize_poll_options(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        item = str(raw or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _ensure_actor_context(current_user: dict[str, Any]) -> tuple[str, str, str | None]:
    tenant_id = str(current_user.get("tenant_id") or "").strip()
    user_id = str(current_user.get("id") or "").strip()
    employee_id = str(current_user.get("employee_id") or "").strip() or None
    if not tenant_id or not user_id:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "메신저 사용을 위해 로그인 정보가 필요합니다.")
    return tenant_id, user_id, employee_id


def _can_manage_announcement_room(actor_role: str | None) -> bool:
    return normalize_user_role(actor_role) in {"hq_admin", "developer"}


def _build_member_payload(row: dict[str, Any], *, presence: dict[str, Any] | None = None) -> dict[str, Any]:
    user_id = str(row.get("user_id") or "").strip() or None
    employee_id = str(row.get("employee_id") or "").strip() or None
    return {
        "user_id": user_id,
        "employee_id": employee_id,
        "membership_role": str(row.get("membership_role") or MEMBERSHIP_ROLE_MEMBER).strip() or MEMBERSHIP_ROLE_MEMBER,
        "full_name": str(row.get("full_name") or "").strip() or str(row.get("username") or "").strip() or "-",
        "username": str(row.get("username") or "").strip() or None,
        "role": str(row.get("role") or "").strip() or None,
        "site_id": str(row.get("site_id") or "").strip() or None,
        "site_name": str(row.get("site_name") or "").strip() or None,
        "joined_at": row.get("joined_at"),
        "last_seen_at": row.get("member_last_seen_at"),
        "presence": presence or {
            "status": PRESENCE_STATUS_OFFLINE,
            "last_seen_at": None,
            "device_type": None,
            "session_key": None,
            "meta_json": {},
            "is_active": False,
        },
    }


def _presence_payload_from_row(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "status": PRESENCE_STATUS_OFFLINE,
            "last_seen_at": None,
            "device_type": None,
            "session_key": None,
            "meta_json": {},
            "is_active": False,
        }
    last_seen_at = row.get("last_seen_at")
    status_value = str(row.get("status") or PRESENCE_STATUS_OFFLINE).strip().lower() or PRESENCE_STATUS_OFFLINE
    is_active = False
    if isinstance(last_seen_at, datetime):
        is_active = (_utc_now() - last_seen_at) <= PRESENCE_ACTIVE_WINDOW
    if not is_active:
        status_value = PRESENCE_STATUS_OFFLINE
    return {
        "status": status_value,
        "last_seen_at": last_seen_at,
        "device_type": str(row.get("device_type") or "").strip() or None,
        "session_key": str(row.get("session_key") or "").strip() or None,
        "meta_json": dict(row.get("meta_json") or {}),
        "is_active": is_active,
    }


def _fetch_user_directory_map(conn, *, tenant_id: str, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_user_ids = _normalize_uuid_list(user_ids)
    if not normalized_user_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id::text AS user_id,
                   e.id::text AS employee_id,
                   au.username,
                   au.full_name,
                   au.role,
                   COALESCE(au.site_id::text, e.site_id::text) AS site_id,
                   s.site_name
            FROM arls_users au
            LEFT JOIN employees e ON e.id = au.employee_id
            LEFT JOIN sites s ON s.id = COALESCE(au.site_id, e.site_id)
            WHERE au.tenant_id = %s
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND au.id::text = ANY(%s)
            """,
            (tenant_id, normalized_user_ids),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return {str(row.get("user_id") or "").strip(): row for row in rows}


def _fetch_presence_map(conn, *, tenant_id: str, user_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_user_ids = _normalize_uuid_list(user_ids)
    if not normalized_user_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (ps.user_id)
                   ps.user_id::text AS user_id,
                   ps.session_key,
                   ps.status,
                   ps.device_type,
                   ps.last_seen_at,
                   ps.meta_json
            FROM presence_sessions ps
            WHERE ps.tenant_id = %s
              AND ps.user_id::text = ANY(%s)
            ORDER BY ps.user_id, ps.last_seen_at DESC, ps.created_at DESC
            """,
            (tenant_id, normalized_user_ids),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return {
        str(row.get("user_id") or "").strip(): _presence_payload_from_row(row)
        for row in rows
        if str(row.get("user_id") or "").strip()
    }


def _fetch_member_rows(conn, *, tenant_id: str, conversation_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = _normalize_uuid_list(conversation_ids)
    if not normalized_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cm.conversation_id::text AS conversation_id,
                   cm.user_id::text AS user_id,
                   cm.employee_id::text AS employee_id,
                   cm.membership_role,
                   cm.joined_at,
                   cm.last_seen_at AS member_last_seen_at,
                   au.username,
                   au.full_name,
                   au.role,
                   COALESCE(au.site_id::text, e.site_id::text) AS site_id,
                   s.site_name
            FROM chat_members cm
            LEFT JOIN arls_users au ON au.id = cm.user_id
            LEFT JOIN employees e ON e.id = COALESCE(cm.employee_id, au.employee_id)
            LEFT JOIN sites s ON s.id = COALESCE(au.site_id, e.site_id)
            WHERE cm.tenant_id = %s
              AND cm.conversation_id::text = ANY(%s)
            ORDER BY cm.joined_at ASC, cm.id ASC
            """,
            (tenant_id, normalized_ids),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_announcement_room_map(conn, *, tenant_id: str, conversation_ids: list[str]) -> dict[str, dict[str, Any]]:
    normalized_ids = _normalize_uuid_list(conversation_ids)
    if not normalized_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT conversation_id::text AS conversation_id,
                   id::text AS announcement_room_id,
                   room_key,
                   scope_type,
                   is_active,
                   created_at
            FROM announcement_rooms
            WHERE tenant_id = %s
              AND conversation_id::text = ANY(%s)
            """,
            (tenant_id, normalized_ids),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return {
        str(row.get("conversation_id") or "").strip(): {
            "id": str(row.get("announcement_room_id") or "").strip(),
            "room_key": str(row.get("room_key") or "").strip() or None,
            "scope_type": str(row.get("scope_type") or "").strip() or ANNOUNCEMENT_SCOPE_TENANT,
            "is_active": bool(row.get("is_active", True)),
            "created_at": row.get("created_at"),
        }
        for row in rows
        if str(row.get("conversation_id") or "").strip()
    }


def _fetch_last_message_map(conn, *, tenant_id: str, conversation_ids: list[str], current_user_id: str) -> dict[str, dict[str, Any]]:
    normalized_ids = _normalize_uuid_list(conversation_ids)
    if not normalized_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (m.conversation_id)
                   m.id::text AS message_id,
                   m.conversation_id::text AS conversation_id,
                   m.sender_user_id::text AS sender_user_id,
                   m.message_type,
                   m.body,
                   m.payload_json,
                   m.edited_at,
                   m.deleted_at,
                   m.created_at,
                   au.full_name AS sender_full_name,
                   au.username AS sender_username
            FROM chat_messages m
            LEFT JOIN arls_users au ON au.id = m.sender_user_id
            WHERE m.tenant_id = %s
              AND m.conversation_id::text = ANY(%s)
            ORDER BY m.conversation_id, m.created_at DESC, m.id DESC
            """,
            (tenant_id, normalized_ids),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    payload: dict[str, dict[str, Any]] = {}
    for row in rows:
        conversation_id = str(row.get("conversation_id") or "").strip()
        if not conversation_id:
            continue
        body = str(row.get("body") or "")
        deleted_at = row.get("deleted_at")
        payload[conversation_id] = {
            "id": str(row.get("message_id") or "").strip() or None,
            "sender_user_id": str(row.get("sender_user_id") or "").strip() or None,
            "sender_name": str(row.get("sender_full_name") or "").strip()
            or str(row.get("sender_username") or "").strip()
            or "-",
            "message_type": str(row.get("message_type") or MESSAGE_TYPE_TEXT).strip() or MESSAGE_TYPE_TEXT,
            "body": "삭제된 메시지입니다." if deleted_at else body,
            "payload_json": _coerce_json_object(row.get("payload_json")),
            "created_at": row.get("created_at"),
            "edited_at": row.get("edited_at"),
            "deleted_at": deleted_at,
            "is_mine": str(row.get("sender_user_id") or "").strip() == current_user_id,
        }
    return payload


def _build_message_fallback_payload(
    *,
    message_id: str,
    conversation_id: str,
    current_user: dict[str, Any],
    body: str,
    message_type: str,
    parent_message_id: str | None,
    payload_json: dict[str, Any] | None,
    mentioned_user_ids: list[str] | None,
    attachment_object_ids: list[str] | None,
    poll_question: str | None,
    poll_options: list[str] | None,
    created_at: datetime,
) -> dict[str, Any]:
    sender_name = str(current_user.get("full_name") or "").strip() or str(current_user.get("username") or "").strip() or "-"
    normalized_payload = _coerce_json_object(payload_json)
    normalized_mentions = _normalize_uuid_list(mentioned_user_ids)
    if normalized_mentions:
        normalized_payload["mentioned_user_ids"] = normalized_mentions
    normalized_attachment_ids = _normalize_uuid_list(attachment_object_ids)
    if normalized_attachment_ids:
        normalized_payload["attachment_object_ids"] = normalized_attachment_ids
    normalized_question = str(poll_question or "").strip()
    normalized_poll_options = _normalize_poll_options(poll_options)
    return {
        "id": message_id,
        "conversation_id": conversation_id or None,
        "sender_user_id": str(current_user.get("id") or "").strip() or None,
        "sender_employee_id": str(current_user.get("employee_id") or "").strip() or None,
        "sender_name": sender_name,
        "sender_username": str(current_user.get("username") or "").strip() or None,
        "sender_role": str(current_user.get("role") or "").strip() or None,
        "parent_message_id": str(parent_message_id or "").strip() or None,
        "message_type": str(message_type or MESSAGE_TYPE_TEXT).strip() or MESSAGE_TYPE_TEXT,
        "body": body,
        "payload_json": normalized_payload,
        "mentioned_user_ids": normalized_mentions,
        "attachments": [
            {
                "attachment_object_id": attachment_object_id,
                "file_name": None,
                "file_ext": None,
                "mime_type": None,
                "byte_size": 0,
                "storage_backend": None,
                "storage_key": None,
                "blob_url": None,
                "metadata_json": {},
            }
            for attachment_object_id in normalized_attachment_ids
        ],
        "reactions": [],
        "poll": (
            {
                "question": normalized_question or None,
                "options": normalized_poll_options,
                "state": "open",
                "created_at": created_at,
            }
            if (str(message_type or "").strip() or MESSAGE_TYPE_TEXT) == MESSAGE_TYPE_POLL
            else None
        ),
        "created_at": created_at,
        "edited_at": None,
        "deleted_at": None,
        "is_mine": True,
    }


def _fetch_unread_count_map(conn, *, tenant_id: str, conversation_ids: list[str], current_user_id: str) -> dict[str, int]:
    normalized_ids = _normalize_uuid_list(conversation_ids)
    if not normalized_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.conversation_id::text AS conversation_id,
                   COUNT(*)::int AS unread_count
            FROM chat_messages m
            LEFT JOIN chat_reads r
              ON r.tenant_id = m.tenant_id
             AND r.conversation_id = m.conversation_id
             AND r.user_id::text = %s
            WHERE m.tenant_id = %s
              AND m.conversation_id::text = ANY(%s)
              AND COALESCE(m.deleted_at, NULL) IS NULL
              AND COALESCE(m.sender_user_id::text, '') <> %s
              AND m.created_at > COALESCE(r.last_read_at, timezone('utc', to_timestamp(0)))
            GROUP BY m.conversation_id
            """,
            (current_user_id, tenant_id, normalized_ids, current_user_id),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return {
        str(row.get("conversation_id") or "").strip(): max(int(row.get("unread_count") or 0), 0)
        for row in rows
        if str(row.get("conversation_id") or "").strip()
    }


def _resolve_conversation_display_title(
    *,
    conversation: dict[str, Any],
    members: list[dict[str, Any]],
    current_user_id: str,
) -> str:
    explicit = str(conversation.get("title") or "").strip()
    if explicit:
        return explicit
    conversation_type = str(conversation.get("conversation_type") or CONVERSATION_TYPE_GROUP).strip()
    if conversation_type == CONVERSATION_TYPE_DM:
        for member in members:
            if str(member.get("user_id") or "").strip() != current_user_id:
                return str(member.get("full_name") or "").strip() or str(member.get("username") or "").strip() or "대화"
    visible_names = [
        str(member.get("full_name") or "").strip() or str(member.get("username") or "").strip()
        for member in members
        if (str(member.get("full_name") or "").strip() or str(member.get("username") or "").strip())
    ]
    if visible_names:
        return ", ".join(visible_names[:3])
    return "대화"


def _build_conversation_payload(
    *,
    conversation: dict[str, Any],
    members: list[dict[str, Any]],
    current_user_id: str,
    unread_count: int = 0,
    last_message: dict[str, Any] | None = None,
    announcement_room: dict[str, Any] | None = None,
) -> dict[str, Any]:
    current_membership = next(
        (
            member
            for member in members
            if str(member.get("user_id") or "").strip() == current_user_id
        ),
        {},
    )
    title = _resolve_conversation_display_title(
        conversation=conversation,
        members=members,
        current_user_id=current_user_id,
    )
    return {
        "id": str(conversation.get("id") or "").strip(),
        "conversation_type": str(conversation.get("conversation_type") or CONVERSATION_TYPE_GROUP).strip()
        or CONVERSATION_TYPE_GROUP,
        "title": title,
        "raw_title": str(conversation.get("title") or "").strip() or None,
        "description": str(conversation.get("description") or "").strip() or None,
        "site_id": str(conversation.get("site_id") or "").strip() or None,
        "site_name": str(conversation.get("site_name") or "").strip() or None,
        "created_by": str(conversation.get("created_by") or "").strip() or None,
        "created_at": conversation.get("created_at"),
        "updated_at": conversation.get("updated_at"),
        "meta_json": dict(conversation.get("meta_json") or {}),
        "member_count": len(members),
        "members": members,
        "current_membership_role": str(current_membership.get("membership_role") or MEMBERSHIP_ROLE_MEMBER).strip()
        or MEMBERSHIP_ROLE_MEMBER,
        "unread_count": max(int(unread_count or 0), 0),
        "last_message": last_message,
        "announcement_room": announcement_room,
    }


def _fetch_conversation_row(conn, *, tenant_id: str, conversation_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text AS id,
                   c.conversation_type,
                   c.title,
                   c.description,
                   c.site_id::text AS site_id,
                   s.site_name,
                   c.created_by::text AS created_by,
                   c.meta_json,
                   c.created_at,
                   c.updated_at
            FROM chat_conversations c
            LEFT JOIN sites s ON s.id = c.site_id
            WHERE c.tenant_id = %s
              AND c.id::text = %s
            LIMIT 1
            """,
            (tenant_id, conversation_id),
        )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _fetch_member_access_row(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT cm.id::text AS member_id,
                   cm.membership_role,
                   cm.joined_at,
                   cm.last_seen_at,
                   c.id::text AS conversation_id,
                   c.conversation_type,
                   c.title,
                   c.description,
                   c.site_id::text AS site_id,
                   c.created_by::text AS created_by,
                   c.meta_json,
                   c.created_at,
                   c.updated_at
            FROM chat_members cm
            JOIN chat_conversations c ON c.id = cm.conversation_id
            WHERE cm.tenant_id = %s
              AND c.tenant_id = %s
              AND cm.conversation_id::text = %s
              AND cm.user_id::text = %s
            LIMIT 1
            """,
            (tenant_id, tenant_id, conversation_id, user_id),
        )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _ensure_member_access(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    user_id: str,
) -> dict[str, Any]:
    row = _fetch_member_access_row(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    if not row:
        raise _http_error(status.HTTP_403_FORBIDDEN, "대화 접근 권한이 없습니다.")
    return row


def _list_conversation_member_user_ids(conn, *, tenant_id: str, conversation_id: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id::text AS user_id
            FROM chat_members
            WHERE tenant_id = %s
              AND conversation_id::text = %s
              AND user_id IS NOT NULL
            ORDER BY joined_at ASC, id ASC
            """,
            (tenant_id, conversation_id),
        )
        rows = cur.fetchall() or []
    return [
        str((row or {}).get("user_id") or "").strip()
        for row in rows
        if str((row or {}).get("user_id") or "").strip()
    ]


def _find_existing_dm_conversation(
    conn,
    *,
    tenant_id: str,
    participant_user_ids: list[str],
) -> str | None:
    normalized_ids = _normalize_uuid_list(participant_user_ids)
    if len(normalized_ids) != 2:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text AS id
            FROM chat_conversations c
            JOIN chat_members cm ON cm.conversation_id = c.id
            WHERE c.tenant_id = %s
              AND cm.tenant_id = %s
              AND c.conversation_type = %s
            GROUP BY c.id
            HAVING COUNT(*) = 2
               AND COUNT(*) FILTER (WHERE cm.user_id::text = ANY(%s)) = 2
            ORDER BY MAX(c.updated_at) DESC
            LIMIT 1
            """,
            (tenant_id, tenant_id, CONVERSATION_TYPE_DM, normalized_ids),
        )
        row = cur.fetchone() or {}
    return str(row.get("id") or "").strip() or None


def _validate_attachment_objects(
    conn,
    *,
    tenant_id: str,
    attachment_object_ids: list[str],
) -> list[str]:
    normalized_ids = _normalize_uuid_list(attachment_object_ids)
    if not normalized_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id
            FROM groupware_attachment_objects
            WHERE tenant_id = %s
              AND id::text = ANY(%s)
            """,
            (tenant_id, normalized_ids),
        )
        rows = cur.fetchall() or []
    resolved = [
        str((row or {}).get("id") or "").strip()
        for row in rows
        if str((row or {}).get("id") or "").strip()
    ]
    if len(resolved) != len(normalized_ids):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "유효하지 않은 첨부 파일이 포함되어 있습니다.")
    return resolved


def _fetch_message_rows_by_ids(conn, *, tenant_id: str, message_ids: list[str]) -> list[dict[str, Any]]:
    normalized_ids = _normalize_uuid_list(message_ids)
    if not normalized_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id::text AS id,
                   m.conversation_id::text AS conversation_id,
                   m.sender_user_id::text AS sender_user_id,
                   m.sender_employee_id::text AS sender_employee_id,
                   m.parent_message_id::text AS parent_message_id,
                   m.message_type,
                   m.body,
                   m.payload_json,
                   m.edited_at,
                   m.deleted_at,
                   m.created_at,
                   au.username AS sender_username,
                   au.full_name AS sender_full_name,
                   au.role AS sender_role
            FROM chat_messages m
            LEFT JOIN arls_users au ON au.id = m.sender_user_id
            WHERE m.tenant_id = %s
              AND m.id::text = ANY(%s)
            ORDER BY m.created_at ASC, m.id ASC
            """,
            (tenant_id, normalized_ids),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_message_detail(conn, *, tenant_id: str, message_id: str, current_user_id: str) -> dict[str, Any]:
    rows = _fetch_message_rows_by_ids(conn, tenant_id=tenant_id, message_ids=[message_id])
    if not rows:
        raise _http_error(status.HTTP_404_NOT_FOUND, "메시지를 찾을 수 없습니다.")
    return _hydrate_message_rows(conn, tenant_id=tenant_id, current_user_id=current_user_id, rows=rows)[0]


def _hydrate_message_rows(
    conn,
    *,
    tenant_id: str,
    current_user_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        return []
    message_ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    attachment_map: dict[str, list[dict[str, Any]]] = {message_id: [] for message_id in message_ids}
    reaction_map: dict[str, list[dict[str, Any]]] = {message_id: [] for message_id in message_ids}
    poll_map: dict[str, dict[str, Any]] = {}

    def _load_attachments():
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT ca.message_id::text AS message_id,
                       gao.id::text AS attachment_object_id,
                       gao.file_name,
                       gao.file_ext,
                       gao.mime_type,
                       gao.byte_size,
                       gao.storage_backend,
                       gao.storage_key,
                       gao.blob_url,
                       gao.metadata_json
                FROM chat_attachments ca
                JOIN groupware_attachment_objects gao ON gao.id = ca.attachment_object_id
                WHERE ca.tenant_id = %s
                  AND ca.message_id::text = ANY(%s)
                ORDER BY ca.created_at ASC, ca.id ASC
                """,
                (tenant_id, message_ids),
            )
            for row in cur.fetchall() or []:
                row_payload = dict(row)
                message_id = str(row_payload.get("message_id") or "").strip()
                if not message_id:
                    continue
                attachment_map.setdefault(message_id, []).append(
                    {
                        "attachment_object_id": str(row_payload.get("attachment_object_id") or "").strip() or None,
                        "file_name": str(row_payload.get("file_name") or "").strip() or None,
                        "file_ext": str(row_payload.get("file_ext") or "").strip() or None,
                        "mime_type": str(row_payload.get("mime_type") or "").strip() or None,
                        "byte_size": max(int(row_payload.get("byte_size") or 0), 0),
                        "storage_backend": str(row_payload.get("storage_backend") or "").strip() or None,
                        "storage_key": str(row_payload.get("storage_key") or "").strip() or None,
                        "blob_url": str(row_payload.get("blob_url") or "").strip() or None,
                        "metadata_json": _coerce_json_object(row_payload.get("metadata_json")),
                    }
                )

    def _load_reactions():
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cr.message_id::text AS message_id,
                       cr.reaction,
                       ARRAY_AGG(cr.user_id::text ORDER BY cr.created_at ASC) AS reacted_user_ids,
                       COUNT(*)::int AS reaction_count
                FROM chat_reactions cr
                WHERE cr.tenant_id = %s
                  AND cr.message_id::text = ANY(%s)
                GROUP BY cr.message_id, cr.reaction
                ORDER BY cr.message_id, cr.reaction
                """,
                (tenant_id, message_ids),
            )
            for row in cur.fetchall() or []:
                row_payload = dict(row)
                message_id = str(row_payload.get("message_id") or "").strip()
                reacted_user_ids = [
                    str(value or "").strip()
                    for value in (row_payload.get("reacted_user_ids") or [])
                    if str(value or "").strip()
                ]
                reaction_map.setdefault(message_id, []).append(
                    {
                        "reaction": str(row_payload.get("reaction") or "").strip() or None,
                        "count": max(int(row_payload.get("reaction_count") or 0), 0),
                        "reacted_user_ids": reacted_user_ids,
                        "reacted_by_me": current_user_id in reacted_user_ids,
                    }
                )

    def _load_polls():
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_id::text AS message_id,
                       question,
                       options_json,
                       state,
                       created_at
                FROM chat_polls
                WHERE tenant_id = %s
                  AND message_id::text = ANY(%s)
                """,
                (tenant_id, message_ids),
            )
            for row in cur.fetchall() or []:
                row_payload = dict(row)
                message_id = str(row_payload.get("message_id") or "").strip()
                if not message_id:
                    continue
                poll_options = row_payload.get("options_json") or []
                poll_map[message_id] = {
                    "question": str(row_payload.get("question") or "").strip() or None,
                    "options": list(poll_options) if isinstance(poll_options, list) else [],
                    "state": str(row_payload.get("state") or "").strip() or "open",
                    "created_at": row_payload.get("created_at"),
                }

    _run_noncritical_db_step(conn, step_name=f"hydrate_attachments:{tenant_id}:{len(message_ids)}", callback=_load_attachments)
    _run_noncritical_db_step(conn, step_name=f"hydrate_reactions:{tenant_id}:{len(message_ids)}", callback=_load_reactions)
    _run_noncritical_db_step(conn, step_name=f"hydrate_polls:{tenant_id}:{len(message_ids)}", callback=_load_polls)

    hydrated: list[dict[str, Any]] = []
    for row in rows:
        message_id = str(row.get("id") or "").strip()
        payload_json = _coerce_json_object(row.get("payload_json"))
        deleted_at = row.get("deleted_at")
        body_text = "삭제된 메시지입니다." if deleted_at else str(row.get("body") or "")
        hydrated.append(
            {
                "id": message_id,
                "conversation_id": str(row.get("conversation_id") or "").strip() or None,
                "sender_user_id": str(row.get("sender_user_id") or "").strip() or None,
                "sender_employee_id": str(row.get("sender_employee_id") or "").strip() or None,
                "sender_name": str(row.get("sender_full_name") or "").strip()
                or str(row.get("sender_username") or "").strip()
                or "-",
                "sender_username": str(row.get("sender_username") or "").strip() or None,
                "sender_role": str(row.get("sender_role") or "").strip() or None,
                "parent_message_id": str(row.get("parent_message_id") or "").strip() or None,
                "message_type": str(row.get("message_type") or MESSAGE_TYPE_TEXT).strip() or MESSAGE_TYPE_TEXT,
                "body": body_text,
                "payload_json": payload_json,
                "mentioned_user_ids": _normalize_uuid_list(payload_json.get("mentioned_user_ids") or []),
                "attachments": attachment_map.get(message_id, []),
                "reactions": reaction_map.get(message_id, []),
                "poll": poll_map.get(message_id),
                "created_at": row.get("created_at"),
                "edited_at": row.get("edited_at"),
                "deleted_at": deleted_at,
                "is_mine": str(row.get("sender_user_id") or "").strip() == current_user_id,
            }
        )
    return hydrated


def list_conversations(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    limit: int = 100,
    conversation_type: str | None = None,
) -> list[dict[str, Any]]:
    _, current_user_id, _ = _ensure_actor_context(current_user)
    normalized_type = None
    if str(conversation_type or "").strip():
        normalized_type = _normalize_choice(
            conversation_type,
            allowed=ALLOWED_CONVERSATION_TYPES,
            field_name="conversation_type",
        )

    sql = """
        SELECT c.id::text AS id,
               c.conversation_type,
               c.title,
               c.description,
               c.site_id::text AS site_id,
               s.site_name,
               c.created_by::text AS created_by,
               c.meta_json,
               c.created_at,
               c.updated_at
        FROM chat_conversations c
        JOIN chat_members cm ON cm.conversation_id = c.id
        LEFT JOIN sites s ON s.id = c.site_id
        WHERE c.tenant_id = %s
          AND cm.tenant_id = %s
          AND cm.user_id::text = %s
    """
    params: list[Any] = [tenant_id, tenant_id, current_user_id]
    if normalized_type:
        sql += " AND c.conversation_type = %s"
        params.append(normalized_type)
    sql += " ORDER BY c.updated_at DESC, c.created_at DESC, c.id DESC LIMIT %s"
    params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = [dict(row) for row in (cur.fetchall() or [])]
    if not rows:
        return []

    conversation_ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    member_rows = _fetch_member_rows(conn, tenant_id=tenant_id, conversation_ids=conversation_ids)
    member_user_ids = [str(row.get("user_id") or "").strip() for row in member_rows if str(row.get("user_id") or "").strip()]
    presence_map = _fetch_presence_map(conn, tenant_id=tenant_id, user_ids=member_user_ids)
    members_by_conversation: dict[str, list[dict[str, Any]]] = {conversation_id: [] for conversation_id in conversation_ids}
    for member_row in member_rows:
        conversation_id = str(member_row.get("conversation_id") or "").strip()
        if not conversation_id:
            continue
        member_payload = _build_member_payload(
            member_row,
            presence=presence_map.get(str(member_row.get("user_id") or "").strip()),
        )
        members_by_conversation.setdefault(conversation_id, []).append(member_payload)

    last_message_map = _fetch_last_message_map(
        conn,
        tenant_id=tenant_id,
        conversation_ids=conversation_ids,
        current_user_id=current_user_id,
    )
    unread_map = _fetch_unread_count_map(
        conn,
        tenant_id=tenant_id,
        conversation_ids=conversation_ids,
        current_user_id=current_user_id,
    )
    announcement_map = _fetch_announcement_room_map(conn, tenant_id=tenant_id, conversation_ids=conversation_ids)

    return [
        _build_conversation_payload(
            conversation=row,
            members=members_by_conversation.get(str(row.get("id") or "").strip(), []),
            current_user_id=current_user_id,
            unread_count=unread_map.get(str(row.get("id") or "").strip(), 0),
            last_message=last_message_map.get(str(row.get("id") or "").strip()),
            announcement_room=announcement_map.get(str(row.get("id") or "").strip()),
        )
        for row in rows
    ]


def get_conversation_detail(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _, current_user_id, _ = _ensure_actor_context(current_user)
    _ensure_member_access(conn, tenant_id=tenant_id, conversation_id=conversation_id, user_id=current_user_id)
    conversation = _fetch_conversation_row(conn, tenant_id=tenant_id, conversation_id=conversation_id)
    if not conversation:
        raise _http_error(status.HTTP_404_NOT_FOUND, "대화를 찾을 수 없습니다.")
    member_rows = _fetch_member_rows(conn, tenant_id=tenant_id, conversation_ids=[conversation_id])
    presence_map = _fetch_presence_map(
        conn,
        tenant_id=tenant_id,
        user_ids=[str(row.get("user_id") or "").strip() for row in member_rows],
    )
    members = [
        _build_member_payload(row, presence=presence_map.get(str(row.get("user_id") or "").strip()))
        for row in member_rows
    ]
    last_message_map = _fetch_last_message_map(
        conn,
        tenant_id=tenant_id,
        conversation_ids=[conversation_id],
        current_user_id=current_user_id,
    )
    unread_map = _fetch_unread_count_map(
        conn,
        tenant_id=tenant_id,
        conversation_ids=[conversation_id],
        current_user_id=current_user_id,
    )
    announcement_map = _fetch_announcement_room_map(conn, tenant_id=tenant_id, conversation_ids=[conversation_id])
    return _build_conversation_payload(
        conversation=conversation,
        members=members,
        current_user_id=current_user_id,
        unread_count=unread_map.get(conversation_id, 0),
        last_message=last_message_map.get(conversation_id),
        announcement_room=announcement_map.get(conversation_id),
    )


def create_conversation(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    conversation_type: str,
    member_user_ids: list[str] | None = None,
    title: str | None = None,
    description: str | None = None,
    site_id: str | None = None,
    meta_json: dict[str, Any] | None = None,
    announcement_room_key: str | None = None,
    announcement_scope_type: str | None = None,
) -> dict[str, Any]:
    _, actor_user_id, actor_employee_id = _ensure_actor_context(current_user)
    actor_role = str(current_user.get("role") or "").strip() or None
    normalized_type = _normalize_choice(
        conversation_type,
        allowed=ALLOWED_CONVERSATION_TYPES,
        field_name="conversation_type",
    )
    participant_user_ids = _normalize_uuid_list([actor_user_id, *list(member_user_ids or [])])
    if normalized_type == CONVERSATION_TYPE_DM and len(participant_user_ids) != 2:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "DM 대화는 참여자 2명만 선택할 수 있습니다.")
    if normalized_type in {CONVERSATION_TYPE_GROUP, CONVERSATION_TYPE_ANNOUNCEMENT} and len(participant_user_ids) < 2:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "그룹 대화는 참여자 2명 이상이 필요합니다.")

    directory = _fetch_user_directory_map(conn, tenant_id=tenant_id, user_ids=participant_user_ids)
    if len(directory) != len(participant_user_ids):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "유효하지 않은 참여자가 포함되어 있습니다.")

    if normalized_type == CONVERSATION_TYPE_ANNOUNCEMENT:
        if not _can_manage_announcement_room(actor_role):
            raise _http_error(status.HTTP_403_FORBIDDEN, "공지방은 관리자만 생성할 수 있습니다.")
        room_key = str(announcement_room_key or "").strip().lower()
        if not room_key:
            raise _http_error(status.HTTP_400_BAD_REQUEST, "공지방 room_key가 필요합니다.")
        scope_type = _normalize_choice(
            announcement_scope_type or ANNOUNCEMENT_SCOPE_TENANT,
            allowed=ALLOWED_ANNOUNCEMENT_SCOPES,
            field_name="announcement_scope_type",
        )
    else:
        room_key = ""
        scope_type = ANNOUNCEMENT_SCOPE_TENANT

    if normalized_type == CONVERSATION_TYPE_DM:
        existing_conversation_id = _find_existing_dm_conversation(
            conn,
            tenant_id=tenant_id,
            participant_user_ids=participant_user_ids,
        )
        if existing_conversation_id:
            return get_conversation_detail(
                conn,
                tenant_id=tenant_id,
                conversation_id=existing_conversation_id,
                current_user=current_user,
            )

    conversation_id = str(uuid.uuid4())
    normalized_title = str(title or "").strip()
    normalized_description = str(description or "").strip()
    if normalized_type == CONVERSATION_TYPE_ANNOUNCEMENT and not normalized_title:
        normalized_title = room_key

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_conversations (
                id,
                tenant_id,
                conversation_type,
                title,
                description,
                site_id,
                created_by,
                meta_json,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb,
                timezone('utc', now()),
                timezone('utc', now())
            )
            """,
            (
                conversation_id,
                tenant_id,
                normalized_type,
                normalized_title,
                normalized_description,
                site_id,
                actor_user_id,
                _json_dumps(meta_json),
            ),
        )
        for user_id in participant_user_ids:
            member_row = directory.get(user_id) or {}
            membership_role = MEMBERSHIP_ROLE_MEMBER
            if user_id == actor_user_id:
                membership_role = MEMBERSHIP_ROLE_OWNER if normalized_type != CONVERSATION_TYPE_DM else MEMBERSHIP_ROLE_MEMBER
            cur.execute(
                """
                INSERT INTO chat_members (
                    id,
                    tenant_id,
                    conversation_id,
                    user_id,
                    employee_id,
                    membership_role,
                    joined_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    timezone('utc', now())
                )
                ON CONFLICT (conversation_id, user_id)
                DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    conversation_id,
                    user_id,
                    member_row.get("employee_id"),
                    membership_role,
                ),
            )
        if normalized_type == CONVERSATION_TYPE_ANNOUNCEMENT:
            cur.execute(
                """
                INSERT INTO announcement_rooms (
                    id,
                    tenant_id,
                    conversation_id,
                    room_key,
                    scope_type,
                    is_active,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, TRUE, timezone('utc', now()))
                ON CONFLICT (tenant_id, room_key)
                DO UPDATE
                SET conversation_id = EXCLUDED.conversation_id,
                    scope_type = EXCLUDED.scope_type,
                    is_active = TRUE
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    conversation_id,
                    room_key,
                    scope_type,
                ),
            )

    GroupwareAuditService(conn).write_event(
        tenant_id=tenant_id,
        module_key="messenger",
        action_type="conversation_created",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type="chat_conversation",
        target_id=conversation_id,
        detail={
            "conversation_type": normalized_type,
            "member_user_ids": participant_user_ids,
            "announcement_room_key": room_key or None,
            "announcement_scope_type": scope_type if room_key else None,
        },
    )
    return get_conversation_detail(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        current_user=current_user,
    )


def list_messages(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    current_user: dict[str, Any],
    limit: int = 100,
) -> list[dict[str, Any]]:
    _, current_user_id, _ = _ensure_actor_context(current_user)
    _ensure_member_access(conn, tenant_id=tenant_id, conversation_id=conversation_id, user_id=current_user_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id::text AS id,
                   m.conversation_id::text AS conversation_id,
                   m.sender_user_id::text AS sender_user_id,
                   m.sender_employee_id::text AS sender_employee_id,
                   m.parent_message_id::text AS parent_message_id,
                   m.message_type,
                   m.body,
                   m.payload_json,
                   m.edited_at,
                   m.deleted_at,
                   m.created_at,
                   au.username AS sender_username,
                   au.full_name AS sender_full_name,
                   au.role AS sender_role
            FROM chat_messages m
            LEFT JOIN arls_users au ON au.id = m.sender_user_id
            WHERE m.tenant_id = %s
              AND m.conversation_id::text = %s
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT %s
            """,
            (tenant_id, conversation_id, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    rows.reverse()
    return _hydrate_message_rows(conn, tenant_id=tenant_id, current_user_id=current_user_id, rows=rows)


def _fetch_message_owner_row(conn, *, tenant_id: str, message_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id::text AS id,
                   m.conversation_id::text AS conversation_id,
                   m.sender_user_id::text AS sender_user_id,
                   m.sender_employee_id::text AS sender_employee_id,
                   m.parent_message_id::text AS parent_message_id,
                   m.message_type,
                   m.body,
                   m.payload_json,
                   m.edited_at,
                   m.deleted_at,
                   m.created_at
            FROM chat_messages m
            WHERE m.tenant_id = %s
              AND m.id::text = %s
            LIMIT 1
            """,
            (tenant_id, message_id),
        )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _ensure_message_access(
    conn,
    *,
    tenant_id: str,
    message_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _, current_user_id, _ = _ensure_actor_context(current_user)
    row = _fetch_message_owner_row(conn, tenant_id=tenant_id, message_id=message_id)
    if not row:
        raise _http_error(status.HTTP_404_NOT_FOUND, "메시지를 찾을 수 없습니다.")
    _ensure_member_access(
        conn,
        tenant_id=tenant_id,
        conversation_id=str(row.get("conversation_id") or "").strip(),
        user_id=current_user_id,
    )
    return row


def create_message(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    current_user: dict[str, Any],
    body: str | None = None,
    message_type: str = MESSAGE_TYPE_TEXT,
    parent_message_id: str | None = None,
    payload_json: dict[str, Any] | None = None,
    mentioned_user_ids: list[str] | None = None,
    attachment_object_ids: list[str] | None = None,
    poll_question: str | None = None,
    poll_options: list[str] | None = None,
) -> dict[str, Any]:
    _, actor_user_id, actor_employee_id = _ensure_actor_context(current_user)
    actor_role = str(current_user.get("role") or "").strip() or None
    conversation_access = _ensure_member_access(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        user_id=actor_user_id,
    )
    normalized_type = _normalize_choice(
        message_type,
        allowed=ALLOWED_MESSAGE_TYPES,
        field_name="message_type",
    )
    normalized_body = str(body or "").strip()
    attachment_ids = _validate_attachment_objects(
        conn,
        tenant_id=tenant_id,
        attachment_object_ids=_normalize_uuid_list(attachment_object_ids),
    )
    member_user_ids = _list_conversation_member_user_ids(conn, tenant_id=tenant_id, conversation_id=conversation_id)
    mentioned_ids = [
        user_id
        for user_id in _normalize_uuid_list(mentioned_user_ids)
        if user_id in member_user_ids and user_id != actor_user_id
    ]
    poll_question_value = str(poll_question or "").strip()
    poll_option_values = _normalize_poll_options(poll_options)

    if parent_message_id:
        parent_row = _fetch_message_owner_row(conn, tenant_id=tenant_id, message_id=parent_message_id)
        if not parent_row or str(parent_row.get("conversation_id") or "").strip() != conversation_id:
            raise _http_error(status.HTTP_400_BAD_REQUEST, "답글 대상 메시지를 찾을 수 없습니다.")

    if normalized_type == MESSAGE_TYPE_POLL:
        if not poll_question_value or len(poll_option_values) < 2:
            raise _http_error(status.HTTP_400_BAD_REQUEST, "투표는 질문과 2개 이상의 선택지가 필요합니다.")
    elif not normalized_body and not attachment_ids:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "메시지 본문 또는 첨부 파일이 필요합니다.")

    message_payload = dict(payload_json or {})
    if mentioned_ids:
        message_payload["mentioned_user_ids"] = mentioned_ids
    if attachment_ids:
        message_payload["attachment_object_ids"] = attachment_ids

    message_id = str(uuid.uuid4())
    now = _utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_messages (
                id,
                tenant_id,
                conversation_id,
                sender_user_id,
                sender_employee_id,
                parent_message_id,
                message_type,
                body,
                payload_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s
            )
            """,
            (
                message_id,
                tenant_id,
                conversation_id,
                actor_user_id,
                actor_employee_id,
                parent_message_id,
                normalized_type,
                normalized_body,
                _json_dumps(message_payload),
                now,
            ),
        )
        for attachment_object_id in attachment_ids:
            cur.execute(
                """
                INSERT INTO chat_attachments (
                    id,
                    tenant_id,
                    message_id,
                    attachment_object_id,
                    created_at
                )
                VALUES (%s, %s, %s, %s, timezone('utc', now()))
                ON CONFLICT (message_id, attachment_object_id)
                DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    message_id,
                    attachment_object_id,
                ),
            )
        if normalized_type == MESSAGE_TYPE_POLL:
            cur.execute(
                """
                INSERT INTO chat_polls (
                    id,
                    tenant_id,
                    message_id,
                    question,
                    options_json,
                    state,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s::jsonb, 'open', timezone('utc', now()))
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    message_id,
                    poll_question_value,
                    _json_dumps_list(poll_option_values),
                ),
            )
        cur.execute(
            """
            UPDATE chat_conversations
            SET updated_at = %s
            WHERE tenant_id = %s
              AND id::text = %s
            """,
            (now, tenant_id, conversation_id),
        )
    conn.commit()

    dispatcher = GroupwareNotificationDispatcher(conn)
    sender_name = str(current_user.get("full_name") or "").strip() or str(current_user.get("username") or "").strip() or "사용자"
    conversation_title = str(conversation_access.get("title") or "").strip() or "메신저"
    if normalized_type == MESSAGE_TYPE_POLL:
        preview = f"투표: {poll_question_value}"
    elif attachment_ids and not normalized_body:
        preview = "파일을 보냈습니다."
    else:
        preview = normalized_body[:80]
    for member_user_id in member_user_ids:
        if member_user_id == actor_user_id:
            continue
        is_mention = member_user_id in mentioned_ids
        _run_noncritical_db_step(
            conn,
            step_name=f"dispatch_notification:{message_id}:{member_user_id}",
            callback=lambda member_user_id=member_user_id, is_mention=is_mention: dispatcher.dispatch_in_app(
                tenant_id=tenant_id,
                user_id=member_user_id,
                category="warn" if is_mention else "info",
                dedupe_key=f"chat-message:{message_id}:{member_user_id}",
                message=(
                    f"[{conversation_title}] {sender_name}님이 회원님을 언급했습니다."
                    if is_mention
                    else f"[{conversation_title}] {sender_name}: {preview or '새 메시지'}"
                ),
                payload={
                    "module": "messenger",
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "message_type": normalized_type,
                    "mentioned": is_mention,
                },
            ),
        )

    _run_noncritical_db_step(
        conn,
        step_name=f"audit_message_created:{message_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="messenger",
            action_type="message_created",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="chat_message",
            target_id=message_id,
            detail={
                "conversation_id": conversation_id,
                "message_type": normalized_type,
                "mentioned_user_ids": mentioned_ids,
                "attachment_count": len(attachment_ids),
                "has_poll": normalized_type == MESSAGE_TYPE_POLL,
            },
        ),
    )

    fetched_message = _run_noncritical_db_step(
        conn,
        step_name=f"fetch_message_detail:{message_id}",
        callback=lambda: _fetch_message_detail(conn, tenant_id=tenant_id, message_id=message_id, current_user_id=actor_user_id),
    )
    if fetched_message:
        return fetched_message
    logger.warning("[MESSENGER] returning fallback payload message=%s conversation=%s", message_id, conversation_id)
    return _build_message_fallback_payload(
        message_id=message_id,
        conversation_id=conversation_id,
        current_user=current_user,
        body=normalized_body,
        message_type=normalized_type,
        parent_message_id=parent_message_id,
        payload_json=message_payload,
        mentioned_user_ids=mentioned_ids,
        attachment_object_ids=attachment_ids,
        poll_question=poll_question_value,
        poll_options=poll_option_values,
        created_at=now,
    )


def update_message(
    conn,
    *,
    tenant_id: str,
    message_id: str,
    current_user: dict[str, Any],
    body: str,
    mentioned_user_ids: list[str] | None = None,
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    actor_role = str(current_user.get("role") or "").strip() or None
    message_row = _ensure_message_access(conn, tenant_id=tenant_id, message_id=message_id, current_user=current_user)
    if message_row.get("deleted_at"):
        raise _http_error(status.HTTP_409_CONFLICT, "삭제된 메시지는 수정할 수 없습니다.")
    if not is_super_admin(actor_role) and str(message_row.get("sender_user_id") or "").strip() != actor_user_id:
        raise _http_error(status.HTTP_403_FORBIDDEN, "본인 메시지만 수정할 수 있습니다.")
    if str(message_row.get("message_type") or "").strip() == MESSAGE_TYPE_POLL:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "투표 메시지는 수정할 수 없습니다.")
    normalized_body = str(body or "").strip()
    if not normalized_body:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "메시지 본문이 필요합니다.")

    member_user_ids = _list_conversation_member_user_ids(
        conn,
        tenant_id=tenant_id,
        conversation_id=str(message_row.get("conversation_id") or "").strip(),
    )
    payload_json = dict(message_row.get("payload_json") or {})
    payload_json["mentioned_user_ids"] = [
        user_id
        for user_id in _normalize_uuid_list(mentioned_user_ids)
        if user_id in member_user_ids and user_id != actor_user_id
    ]
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE chat_messages
            SET body = %s,
                payload_json = %s::jsonb,
                edited_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id::text = %s
            """,
            (
                normalized_body,
                _json_dumps(payload_json),
                tenant_id,
                message_id,
            ),
        )

    GroupwareAuditService(conn).write_event(
        tenant_id=tenant_id,
        module_key="messenger",
        action_type="message_updated",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type="chat_message",
        target_id=message_id,
        detail={"conversation_id": str(message_row.get("conversation_id") or "").strip()},
    )
    return _fetch_message_detail(conn, tenant_id=tenant_id, message_id=message_id, current_user_id=actor_user_id)


def delete_message(
    conn,
    *,
    tenant_id: str,
    message_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    actor_role = str(current_user.get("role") or "").strip() or None
    message_row = _ensure_message_access(conn, tenant_id=tenant_id, message_id=message_id, current_user=current_user)
    if message_row.get("deleted_at"):
        return {"ok": True, "already_deleted": True}
    if not is_super_admin(actor_role) and str(message_row.get("sender_user_id") or "").strip() != actor_user_id:
        raise _http_error(status.HTTP_403_FORBIDDEN, "본인 메시지만 삭제할 수 있습니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE chat_messages
            SET body = '',
                deleted_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id::text = %s
            """,
            (tenant_id, message_id),
        )

    GroupwareAuditService(conn).write_event(
        tenant_id=tenant_id,
        module_key="messenger",
        action_type="message_deleted",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        target_type="chat_message",
        target_id=message_id,
        detail={"conversation_id": str(message_row.get("conversation_id") or "").strip()},
    )
    return {"ok": True, "already_deleted": False}


def mark_conversation_read(
    conn,
    *,
    tenant_id: str,
    conversation_id: str,
    current_user: dict[str, Any],
    message_id: str | None = None,
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    _ensure_member_access(conn, tenant_id=tenant_id, conversation_id=conversation_id, user_id=actor_user_id)

    target_message_id = str(message_id or "").strip()
    if not target_message_id:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id::text AS id
                FROM chat_messages
                WHERE tenant_id = %s
                  AND conversation_id::text = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (tenant_id, conversation_id),
            )
            row = cur.fetchone() or {}
        target_message_id = str(row.get("id") or "").strip() or None
    elif str((_fetch_message_owner_row(conn, tenant_id=tenant_id, message_id=target_message_id) or {}).get("conversation_id") or "").strip() != conversation_id:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "선택한 메시지는 해당 대화에 속하지 않습니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_reads (
                id,
                tenant_id,
                conversation_id,
                user_id,
                last_read_message_id,
                last_read_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (conversation_id, user_id)
            DO UPDATE
            SET last_read_message_id = EXCLUDED.last_read_message_id,
                last_read_at = timezone('utc', now())
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                conversation_id,
                actor_user_id,
                target_message_id,
            ),
        )
        cur.execute(
            """
            UPDATE chat_members
            SET last_seen_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND conversation_id::text = %s
              AND user_id::text = %s
            """,
            (tenant_id, conversation_id, actor_user_id),
        )
    return {
        "ok": True,
        "conversation_id": conversation_id,
        "last_read_message_id": target_message_id,
    }


def add_message_reaction(
    conn,
    *,
    tenant_id: str,
    message_id: str,
    current_user: dict[str, Any],
    reaction: str,
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    message_row = _ensure_message_access(conn, tenant_id=tenant_id, message_id=message_id, current_user=current_user)
    normalized_reaction = _normalize_reaction(reaction)

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chat_reactions (
                id,
                tenant_id,
                message_id,
                user_id,
                reaction,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (message_id, user_id, reaction)
            DO NOTHING
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                message_id,
                actor_user_id,
                normalized_reaction,
            ),
        )
    return _fetch_message_detail(conn, tenant_id=tenant_id, message_id=message_id, current_user_id=actor_user_id)


def remove_message_reaction(
    conn,
    *,
    tenant_id: str,
    message_id: str,
    current_user: dict[str, Any],
    reaction: str,
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    _ensure_message_access(conn, tenant_id=tenant_id, message_id=message_id, current_user=current_user)
    normalized_reaction = _normalize_reaction(reaction)
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM chat_reactions
            WHERE tenant_id = %s
              AND message_id::text = %s
              AND user_id::text = %s
              AND reaction = %s
            """,
            (tenant_id, message_id, actor_user_id, normalized_reaction),
        )
    return _fetch_message_detail(conn, tenant_id=tenant_id, message_id=message_id, current_user_id=actor_user_id)


def upsert_presence_session(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    session_key: str,
    status_value: str,
    device_type: str = "web",
    meta_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    normalized_session_key = str(session_key or "").strip()
    if not normalized_session_key:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "session_key가 필요합니다.")
    normalized_status = _normalize_choice(
        status_value,
        allowed=ALLOWED_PRESENCE_STATUSES,
        field_name="presence status",
    )
    normalized_device_type = str(device_type or "").strip().lower() or "web"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO presence_sessions (
                id,
                tenant_id,
                user_id,
                session_key,
                status,
                device_type,
                last_seen_at,
                meta_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s,
                timezone('utc', now()), %s::jsonb, timezone('utc', now())
            )
            ON CONFLICT (tenant_id, session_key)
            DO UPDATE
            SET user_id = EXCLUDED.user_id,
                status = EXCLUDED.status,
                device_type = EXCLUDED.device_type,
                last_seen_at = timezone('utc', now()),
                meta_json = EXCLUDED.meta_json
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                actor_user_id,
                normalized_session_key,
                normalized_status,
                normalized_device_type,
                _json_dumps(meta_json),
            ),
        )
    presence_map = _fetch_presence_map(conn, tenant_id=tenant_id, user_ids=[actor_user_id])
    return {
        "user_id": actor_user_id,
        "session_key": normalized_session_key,
        "presence": presence_map.get(actor_user_id, _presence_payload_from_row(None)),
    }


def list_presence(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    conversation_id: str | None = None,
    user_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    resolved_user_ids = _normalize_uuid_list(user_ids)
    if conversation_id:
        _ensure_member_access(conn, tenant_id=tenant_id, conversation_id=conversation_id, user_id=actor_user_id)
        resolved_user_ids = _list_conversation_member_user_ids(conn, tenant_id=tenant_id, conversation_id=conversation_id)
    directory = _fetch_user_directory_map(conn, tenant_id=tenant_id, user_ids=resolved_user_ids)
    presence_map = _fetch_presence_map(conn, tenant_id=tenant_id, user_ids=resolved_user_ids)
    payload: list[dict[str, Any]] = []
    for user_id in resolved_user_ids:
        directory_row = directory.get(user_id) or {}
        payload.append(
            {
                "user_id": user_id,
                "full_name": str(directory_row.get("full_name") or "").strip()
                or str(directory_row.get("username") or "").strip()
                or "-",
                "username": str(directory_row.get("username") or "").strip() or None,
                "role": str(directory_row.get("role") or "").strip() or None,
                "site_id": str(directory_row.get("site_id") or "").strip() or None,
                "site_name": str(directory_row.get("site_name") or "").strip() or None,
                "presence": presence_map.get(user_id, _presence_payload_from_row(None)),
            }
        )
    return payload


def search_messages(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    query: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    normalized_query = str(query or "").strip()
    if len(normalized_query) < 2:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "검색어는 2자 이상 입력해 주세요.")
    like = f"%{normalized_query}%"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id::text AS id,
                   m.conversation_id::text AS conversation_id,
                   m.sender_user_id::text AS sender_user_id,
                   m.sender_employee_id::text AS sender_employee_id,
                   m.parent_message_id::text AS parent_message_id,
                   m.message_type,
                   m.body,
                   m.payload_json,
                   m.edited_at,
                   m.deleted_at,
                   m.created_at,
                   au.username AS sender_username,
                   au.full_name AS sender_full_name,
                   au.role AS sender_role
            FROM chat_messages m
            JOIN chat_members cm
              ON cm.conversation_id = m.conversation_id
             AND cm.tenant_id = m.tenant_id
             AND cm.user_id::text = %s
            LEFT JOIN arls_users au ON au.id = m.sender_user_id
            WHERE m.tenant_id = %s
              AND COALESCE(m.deleted_at, NULL) IS NULL
              AND (
                    COALESCE(m.body, '') ILIKE %s
                 OR COALESCE(au.full_name, '') ILIKE %s
                 OR COALESCE(au.username, '') ILIKE %s
              )
            ORDER BY m.created_at DESC, m.id DESC
            LIMIT %s
            """,
            (actor_user_id, tenant_id, like, like, like, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    hydrated = _hydrate_message_rows(conn, tenant_id=tenant_id, current_user_id=actor_user_id, rows=rows)
    conversation_ids = _normalize_uuid_list([str(row.get("conversation_id") or "").strip() for row in hydrated])
    conversation_rows = {
        str(row.get("id") or "").strip(): row
        for row in [
            _fetch_conversation_row(conn, tenant_id=tenant_id, conversation_id=conversation_id) or {}
            for conversation_id in conversation_ids
        ]
        if str(row.get("id") or "").strip()
    }
    member_rows = _fetch_member_rows(conn, tenant_id=tenant_id, conversation_ids=conversation_ids)
    member_user_ids = _normalize_uuid_list([str(row.get("user_id") or "").strip() for row in member_rows])
    presence_map = _fetch_presence_map(conn, tenant_id=tenant_id, user_ids=member_user_ids)
    members_by_conversation: dict[str, list[dict[str, Any]]] = {conversation_id: [] for conversation_id in conversation_ids}
    for row in member_rows:
        conversation_id = str(row.get("conversation_id") or "").strip()
        members_by_conversation.setdefault(conversation_id, []).append(
            _build_member_payload(row, presence=presence_map.get(str(row.get("user_id") or "").strip()))
        )
    payload: list[dict[str, Any]] = []
    for message in hydrated:
        conversation_id = str(message.get("conversation_id") or "").strip()
        conversation = conversation_rows.get(conversation_id) or {}
        members = members_by_conversation.get(conversation_id, [])
        payload.append(
            {
                "message": message,
                "conversation": _build_conversation_payload(
                    conversation=conversation,
                    members=members,
                    current_user_id=actor_user_id,
                    unread_count=0,
                    last_message=None,
                    announcement_room=None,
                )
                if conversation
                else None,
            }
        )
    return payload


def list_announcement_rooms(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    active_only: bool = True,
) -> list[dict[str, Any]]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    sql = """
        SELECT ar.id::text AS announcement_room_id,
               ar.room_key,
               ar.scope_type,
               ar.is_active,
               ar.created_at,
               c.id::text AS conversation_id
        FROM announcement_rooms ar
        JOIN chat_conversations c ON c.id = ar.conversation_id
        JOIN chat_members cm ON cm.conversation_id = c.id
        WHERE ar.tenant_id = %s
          AND c.tenant_id = %s
          AND cm.tenant_id = %s
          AND cm.user_id::text = %s
    """
    params: list[Any] = [tenant_id, tenant_id, tenant_id, actor_user_id]
    if active_only:
        sql += " AND ar.is_active = TRUE"
    sql += " ORDER BY ar.created_at DESC, ar.id DESC"
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = [dict(row) for row in (cur.fetchall() or [])]
    conversations = {
        str(row.get("conversation_id") or "").strip(): get_conversation_detail(
            conn,
            tenant_id=tenant_id,
            conversation_id=str(row.get("conversation_id") or "").strip(),
            current_user=current_user,
        )
        for row in rows
        if str(row.get("conversation_id") or "").strip()
    }
    return [
        {
            "id": str(row.get("announcement_room_id") or "").strip() or None,
            "room_key": str(row.get("room_key") or "").strip() or None,
            "scope_type": str(row.get("scope_type") or "").strip() or ANNOUNCEMENT_SCOPE_TENANT,
            "is_active": bool(row.get("is_active", True)),
            "created_at": row.get("created_at"),
            "conversation": conversations.get(str(row.get("conversation_id") or "").strip()),
        }
        for row in rows
    ]
