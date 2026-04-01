from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from .groupware_foundation import GroupwareAuditService, GroupwareNotificationDispatcher
from ..config import settings
from ..utils.permissions import is_super_admin, normalize_user_role

ROOM_STATE_SCHEDULED = "scheduled"
ROOM_STATE_LIVE = "live"
ROOM_STATE_ENDED = "ended"
ROOM_STATE_CANCELLED = "cancelled"
ALLOWED_ROOM_STATES = {
    ROOM_STATE_SCHEDULED,
    ROOM_STATE_LIVE,
    ROOM_STATE_ENDED,
    ROOM_STATE_CANCELLED,
}

SESSION_STATE_CREATED = "created"
SESSION_STATE_LIVE = "live"
SESSION_STATE_ENDED = "ended"
SESSION_STATE_FAILED = "failed"
ALLOWED_SESSION_STATES = {
    SESSION_STATE_CREATED,
    SESSION_STATE_LIVE,
    SESSION_STATE_ENDED,
    SESSION_STATE_FAILED,
}

MEDIA_BACKEND_PION = "pion"
MEDIA_BACKEND_EXTERNAL = "external"
ALLOWED_MEDIA_BACKENDS = {
    MEDIA_BACKEND_PION,
    MEDIA_BACKEND_EXTERNAL,
}

PARTICIPANT_ROLE_HOST = "host"
PARTICIPANT_ROLE_PRESENTER = "presenter"
PARTICIPANT_ROLE_PARTICIPANT = "participant"
ALLOWED_PARTICIPANT_ROLES = {
    PARTICIPANT_ROLE_HOST,
    PARTICIPANT_ROLE_PRESENTER,
    PARTICIPANT_ROLE_PARTICIPANT,
}

ROLLOUT_STATUS_PENDING = "pending"
ROLLOUT_STATUS_READY = "ready"
ROLLOUT_STATUS_BLOCKED = "blocked"
ROLLOUT_STATUS_PASSED = "passed"
ROLLOUT_STATUS_FAILED = "failed"
ALLOWED_ROLLOUT_STATUSES = {
    ROLLOUT_STATUS_PENDING,
    ROLLOUT_STATUS_READY,
    ROLLOUT_STATUS_BLOCKED,
    ROLLOUT_STATUS_PASSED,
    ROLLOUT_STATUS_FAILED,
}

ALLOWED_EVENT_TYPES = {
    "join",
    "leave",
    "reconnect",
    "mute_on",
    "mute_off",
    "camera_on",
    "camera_off",
    "screen_share_on",
    "screen_share_off",
    "signal_offer",
    "signal_answer",
    "signal_candidate",
    "session_started",
    "session_ended",
}

ROOM_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _http_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": "MEETING_ERROR", "message": message},
    )


def _normalize_choice(value: str | None, *, allowed: set[str], field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise _http_error(status.HTTP_400_BAD_REQUEST, f"{field_name} 값이 올바르지 않습니다.")
    return normalized


def _normalize_room_key(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized and not ROOM_KEY_PATTERN.fullmatch(normalized):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "room_key 값이 올바르지 않습니다.")
    return normalized


def _ensure_actor_context(current_user: dict[str, Any]) -> tuple[str, str, str | None]:
    tenant_id = str(current_user.get("tenant_id") or "").strip()
    user_id = str(current_user.get("id") or "").strip()
    employee_id = str(current_user.get("employee_id") or "").strip() or None
    if not tenant_id or not user_id:
        raise _http_error(status.HTTP_401_UNAUTHORIZED, "회의 기능을 사용하려면 로그인 정보가 필요합니다.")
    return tenant_id, user_id, employee_id


def _normalize_uuid_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for raw in values or []:
        item = str(raw or "").strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _can_manage_rollout(actor_role: str | None) -> bool:
    return normalize_user_role(actor_role) in {"hq_admin", "developer"}


def _build_connection_blueprint() -> dict[str, Any]:
    return {
        "rt_gateway_public_url": str(settings.rt_gateway_public_url or "").strip() or None,
        "media_sfu_public_url": str(settings.media_sfu_public_url or "").strip() or None,
        "coturn_server_uris": list(settings.coturn_server_uris or []),
    }


def _generate_room_key() -> str:
    return f"mtg-{str(uuid.uuid4())[:8].lower()}"


def _generate_session_key() -> str:
    return f"sess-{str(uuid.uuid4())[:12].lower()}"


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


def _fetch_room_row(conn, *, tenant_id: str, room_id: str | None = None, room_key: str | None = None) -> dict[str, Any] | None:
    if not room_id and not room_key:
        return None
    with conn.cursor() as cur:
        if room_id:
            cur.execute(
                """
                SELECT mr.id::text AS id,
                       mr.title,
                       mr.host_user_id::text AS host_user_id,
                       mr.room_key,
                       mr.state,
                       mr.scheduled_for,
                       mr.ended_at,
                       mr.settings_json,
                       mr.created_at,
                       mr.updated_at,
                       au.full_name AS host_full_name,
                       au.username AS host_username
                FROM meeting_rooms mr
                LEFT JOIN arls_users au ON au.id = mr.host_user_id
                WHERE mr.tenant_id = %s
                  AND mr.id::text = %s
                LIMIT 1
                """,
                (tenant_id, room_id),
            )
        else:
            cur.execute(
                """
                SELECT mr.id::text AS id,
                       mr.title,
                       mr.host_user_id::text AS host_user_id,
                       mr.room_key,
                       mr.state,
                       mr.scheduled_for,
                       mr.ended_at,
                       mr.settings_json,
                       mr.created_at,
                       mr.updated_at,
                       au.full_name AS host_full_name,
                       au.username AS host_username
                FROM meeting_rooms mr
                LEFT JOIN arls_users au ON au.id = mr.host_user_id
                WHERE mr.tenant_id = %s
                  AND mr.room_key = %s
                LIMIT 1
                """,
                (tenant_id, room_key),
            )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _fetch_room_participants(conn, *, tenant_id: str, room_ids: list[str]) -> list[dict[str, Any]]:
    normalized_room_ids = _normalize_uuid_list(room_ids)
    if not normalized_room_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mp.meeting_room_id::text AS room_id,
                   mp.id::text AS participant_id,
                   mp.user_id::text AS user_id,
                   mp.employee_id::text AS employee_id,
                   mp.participant_role,
                   mp.invited_at,
                   mp.joined_at,
                   mp.left_at,
                   au.username,
                   au.full_name,
                   au.role,
                   COALESCE(au.site_id::text, e.site_id::text) AS site_id,
                   s.site_name
            FROM meeting_participants mp
            LEFT JOIN arls_users au ON au.id = mp.user_id
            LEFT JOIN employees e ON e.id = COALESCE(mp.employee_id, au.employee_id)
            LEFT JOIN sites s ON s.id = COALESCE(au.site_id, e.site_id)
            WHERE mp.tenant_id = %s
              AND mp.meeting_room_id::text = ANY(%s)
            ORDER BY mp.invited_at ASC, mp.id ASC
            """,
            (tenant_id, normalized_room_ids),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_room_sessions(conn, *, tenant_id: str, room_ids: list[str]) -> list[dict[str, Any]]:
    normalized_room_ids = _normalize_uuid_list(room_ids)
    if not normalized_room_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ms.id::text AS session_id,
                   ms.meeting_room_id::text AS room_id,
                   ms.session_key,
                   ms.media_backend,
                   ms.state,
                   ms.started_at,
                   ms.ended_at,
                   ms.meta_json,
                   ms.created_at
            FROM meeting_sessions ms
            WHERE ms.tenant_id = %s
              AND ms.meeting_room_id::text = ANY(%s)
            ORDER BY ms.created_at DESC, ms.id DESC
            """,
            (tenant_id, normalized_room_ids),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_room_chat_links(conn, *, tenant_id: str, room_ids: list[str]) -> list[dict[str, Any]]:
    normalized_room_ids = _normalize_uuid_list(room_ids)
    if not normalized_room_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT mcl.meeting_room_id::text AS room_id,
                   mcl.id::text AS link_id,
                   mcl.conversation_id::text AS conversation_id,
                   mcl.link_type,
                   mcl.created_at,
                   c.title AS conversation_title,
                   c.conversation_type
            FROM meeting_chat_links mcl
            JOIN chat_conversations c ON c.id = mcl.conversation_id
            WHERE mcl.tenant_id = %s
              AND mcl.meeting_room_id::text = ANY(%s)
            ORDER BY mcl.created_at ASC, mcl.id ASC
            """,
            (tenant_id, normalized_room_ids),
        )
        return [dict(row) for row in (cur.fetchall() or [])]


def _fetch_recent_room_events(conn, *, tenant_id: str, room_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT me.id::text AS id,
                   me.meeting_room_id::text AS room_id,
                   me.session_id::text AS session_id,
                   me.actor_user_id::text AS actor_user_id,
                   me.event_type,
                   me.payload_json,
                   me.created_at,
                   au.full_name AS actor_full_name,
                   au.username AS actor_username
            FROM meeting_events me
            LEFT JOIN arls_users au ON au.id = me.actor_user_id
            WHERE me.tenant_id = %s
              AND me.meeting_room_id::text = %s
            ORDER BY me.created_at DESC, me.id DESC
            LIMIT %s
            """,
            (tenant_id, room_id, int(limit)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    rows.reverse()
    return [
        {
            "id": str(row.get("id") or "").strip() or None,
            "room_id": str(row.get("room_id") or "").strip() or None,
            "session_id": str(row.get("session_id") or "").strip() or None,
            "actor_user_id": str(row.get("actor_user_id") or "").strip() or None,
            "actor_name": str(row.get("actor_full_name") or "").strip()
            or str(row.get("actor_username") or "").strip()
            or None,
            "event_type": str(row.get("event_type") or "").strip() or None,
            "payload_json": dict(row.get("payload_json") or {}),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def _fetch_rollout_checks(conn, *, tenant_id: str, module_key: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id,
                   module_key,
                   environment_key,
                   check_type,
                   status,
                   summary,
                   detail_json,
                   checked_by::text AS checked_by,
                   checked_at,
                   created_at
            FROM groupware_rollout_checks
            WHERE tenant_id = %s
              AND module_key = %s
            ORDER BY checked_at DESC, created_at DESC, id DESC
            """,
            (tenant_id, module_key),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return [
        {
            "id": str(row.get("id") or "").strip() or None,
            "module_key": str(row.get("module_key") or "").strip() or None,
            "environment_key": str(row.get("environment_key") or "").strip() or None,
            "check_type": str(row.get("check_type") or "").strip() or None,
            "status": str(row.get("status") or "").strip() or None,
            "summary": str(row.get("summary") or "").strip() or None,
            "detail_json": dict(row.get("detail_json") or {}),
            "checked_by": str(row.get("checked_by") or "").strip() or None,
            "checked_at": row.get("checked_at"),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


def _find_participant_row(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    user_id: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS participant_id,
                   meeting_room_id::text AS room_id,
                   user_id::text AS user_id,
                   employee_id::text AS employee_id,
                   participant_role,
                   invited_at,
                   joined_at,
                   left_at
            FROM meeting_participants
            WHERE tenant_id = %s
              AND meeting_room_id::text = %s
              AND user_id::text = %s
            LIMIT 1
            """,
            (tenant_id, room_id, user_id),
        )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _ensure_room_access(conn, *, tenant_id: str, room_id: str, current_user: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    room = _fetch_room_row(conn, tenant_id=tenant_id, room_id=room_id)
    if not room:
        raise _http_error(status.HTTP_404_NOT_FOUND, "회의실을 찾을 수 없습니다.")
    participant = _find_participant_row(conn, tenant_id=tenant_id, room_id=room_id, user_id=actor_user_id)
    actor_role = str(current_user.get("role") or "").strip() or None
    if not participant and not is_super_admin(actor_role) and str(room.get("host_user_id") or "").strip() != actor_user_id:
        raise _http_error(status.HTTP_403_FORBIDDEN, "회의 접근 권한이 없습니다.")
    return room, participant


def _ensure_host_access(conn, *, tenant_id: str, room_id: str, current_user: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    room, participant = _ensure_room_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    participant_role = str((participant or {}).get("participant_role") or "").strip()
    if is_super_admin(actor_role) or str(room.get("host_user_id") or "").strip() == actor_user_id:
        return room, participant
    if participant_role in {PARTICIPANT_ROLE_HOST, PARTICIPANT_ROLE_PRESENTER}:
        return room, participant
    raise _http_error(status.HTTP_403_FORBIDDEN, "회의 관리 권한이 없습니다.")


def _fetch_session_row(conn, *, tenant_id: str, room_id: str, session_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS session_id,
                   meeting_room_id::text AS room_id,
                   session_key,
                   media_backend,
                   state,
                   started_at,
                   ended_at,
                   meta_json,
                   created_at
            FROM meeting_sessions
            WHERE tenant_id = %s
              AND meeting_room_id::text = %s
              AND id::text = %s
            LIMIT 1
            """,
            (tenant_id, room_id, session_id),
        )
        row = cur.fetchone() or {}
    return dict(row) if row else None


def _ensure_session_access(conn, *, tenant_id: str, room_id: str, session_id: str, current_user: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any]]:
    room, participant = _ensure_room_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    session_row = _fetch_session_row(conn, tenant_id=tenant_id, room_id=room_id, session_id=session_id)
    if not session_row:
        raise _http_error(status.HTTP_404_NOT_FOUND, "회의 세션을 찾을 수 없습니다.")
    return room, participant, session_row


def _validate_linked_conversation(conn, *, tenant_id: str, conversation_id: str | None) -> str | None:
    normalized = str(conversation_id or "").strip()
    if not normalized:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text AS id
            FROM chat_conversations
            WHERE tenant_id = %s
              AND id::text = %s
            LIMIT 1
            """,
            (tenant_id, normalized),
        )
        row = cur.fetchone() or {}
    resolved = str(row.get("id") or "").strip() or None
    if not resolved:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "연결할 메신저 대화를 찾을 수 없습니다.")
    return resolved


def _insert_meeting_participant_row(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    user_id: str,
    employee_id: str | None,
    participant_role: str,
    joined_at: datetime | None = None,
) -> None:
    participant_id = str(uuid.uuid4())
    insert_sql = """
        INSERT INTO meeting_participants (
            id,
            tenant_id,
            meeting_room_id,
            user_id,
            employee_id,
            participant_role,
            invited_at,
            joined_at
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, timezone('utc', now()), %s
        )
    """

    with conn.cursor() as cur:
        cur.execute("SAVEPOINT meeting_participant_insert_sp")
        try:
            cur.execute(
                insert_sql,
                (
                    participant_id,
                    tenant_id,
                    room_id,
                    user_id,
                    employee_id,
                    participant_role,
                    joined_at,
                ),
            )
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT meeting_participant_insert_sp")
            cur.execute(
                insert_sql,
                (
                    participant_id,
                    tenant_id,
                    room_id,
                    user_id,
                    None,
                    participant_role,
                    joined_at,
                ),
            )
        finally:
            cur.execute("RELEASE SAVEPOINT meeting_participant_insert_sp")


def _run_meetings_best_effort(conn, callback):
    savepoint_name = f"meetings_side_effect_{uuid.uuid4().hex[:12]}"
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {savepoint_name}")
    try:
        result = callback()
    except Exception:
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        return None
    with conn.cursor() as cur:
        cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    return result


def _build_room_payload(
    *,
    room: dict[str, Any],
    participants: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    chat_links: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    live_session = next((session for session in sessions if str(session.get("state") or "") == SESSION_STATE_LIVE), None)
    return {
        "id": str(room.get("id") or "").strip() or None,
        "title": str(room.get("title") or "").strip() or "회의",
        "host_user_id": str(room.get("host_user_id") or "").strip() or None,
        "host_name": str(room.get("host_full_name") or "").strip()
        or str(room.get("host_username") or "").strip()
        or None,
        "room_key": str(room.get("room_key") or "").strip() or None,
        "join_ref": str(room.get("room_key") or "").strip() or None,
        "state": str(room.get("state") or "").strip() or ROOM_STATE_SCHEDULED,
        "scheduled_for": room.get("scheduled_for"),
        "ended_at": room.get("ended_at"),
        "settings_json": dict(room.get("settings_json") or {}),
        "created_at": room.get("created_at"),
        "updated_at": room.get("updated_at"),
        "participant_count": len(participants),
        "participants": participants,
        "sessions": sessions,
        "active_session": live_session,
        "chat_links": chat_links,
        "events": events or [],
    }


def list_meeting_rooms(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    limit: int = 100,
    state_filter: str | None = None,
) -> list[dict[str, Any]]:
    _, actor_user_id, _ = _ensure_actor_context(current_user)
    normalized_state = None
    if str(state_filter or "").strip():
        normalized_state = _normalize_choice(state_filter, allowed=ALLOWED_ROOM_STATES, field_name="room state")
    sql = """
        SELECT mr.id::text AS id,
               mr.title,
               mr.host_user_id::text AS host_user_id,
               mr.room_key,
               mr.state,
               mr.scheduled_for,
               mr.ended_at,
               mr.settings_json,
               mr.created_at,
               mr.updated_at,
               au.full_name AS host_full_name,
               au.username AS host_username
        FROM meeting_rooms mr
        LEFT JOIN arls_users au ON au.id = mr.host_user_id
        WHERE mr.tenant_id = %s
          AND (
                mr.host_user_id::text = %s
             OR EXISTS (
                   SELECT 1
                   FROM meeting_participants mp
                   WHERE mp.tenant_id = mr.tenant_id
                     AND mp.meeting_room_id = mr.id
                     AND mp.user_id::text = %s
               )
          )
    """
    params: list[Any] = [tenant_id, actor_user_id, actor_user_id]
    if normalized_state:
        sql += " AND mr.state = %s"
        params.append(normalized_state)
    sql += " ORDER BY CASE WHEN mr.state = 'live' THEN 0 WHEN mr.state = 'scheduled' THEN 1 ELSE 9 END, mr.updated_at DESC, mr.created_at DESC LIMIT %s"
    params.append(int(limit))
    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        rows = [dict(row) for row in (cur.fetchall() or [])]
    room_ids = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
    participant_rows = _fetch_room_participants(conn, tenant_id=tenant_id, room_ids=room_ids)
    session_rows = _fetch_room_sessions(conn, tenant_id=tenant_id, room_ids=room_ids)
    chat_link_rows = _fetch_room_chat_links(conn, tenant_id=tenant_id, room_ids=room_ids)
    participants_by_room: dict[str, list[dict[str, Any]]] = {room_id: [] for room_id in room_ids}
    sessions_by_room: dict[str, list[dict[str, Any]]] = {room_id: [] for room_id in room_ids}
    links_by_room: dict[str, list[dict[str, Any]]] = {room_id: [] for room_id in room_ids}
    for row in participant_rows:
        room_id = str(row.get("room_id") or "").strip()
        participants_by_room.setdefault(room_id, []).append(
            {
                "participant_id": str(row.get("participant_id") or "").strip() or None,
                "user_id": str(row.get("user_id") or "").strip() or None,
                "employee_id": str(row.get("employee_id") or "").strip() or None,
                "participant_role": str(row.get("participant_role") or "").strip() or PARTICIPANT_ROLE_PARTICIPANT,
                "full_name": str(row.get("full_name") or "").strip() or str(row.get("username") or "").strip() or "-",
                "username": str(row.get("username") or "").strip() or None,
                "role": str(row.get("role") or "").strip() or None,
                "site_id": str(row.get("site_id") or "").strip() or None,
                "site_name": str(row.get("site_name") or "").strip() or None,
                "invited_at": row.get("invited_at"),
                "joined_at": row.get("joined_at"),
                "left_at": row.get("left_at"),
            }
        )
    for row in session_rows:
        room_id = str(row.get("room_id") or "").strip()
        sessions_by_room.setdefault(room_id, []).append(
            {
                "id": str(row.get("session_id") or "").strip() or None,
                "session_key": str(row.get("session_key") or "").strip() or None,
                "media_backend": str(row.get("media_backend") or "").strip() or MEDIA_BACKEND_PION,
                "state": str(row.get("state") or "").strip() or SESSION_STATE_CREATED,
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "meta_json": dict(row.get("meta_json") or {}),
                "created_at": row.get("created_at"),
            }
        )
    for row in chat_link_rows:
        room_id = str(row.get("room_id") or "").strip()
        links_by_room.setdefault(room_id, []).append(
            {
                "id": str(row.get("link_id") or "").strip() or None,
                "conversation_id": str(row.get("conversation_id") or "").strip() or None,
                "conversation_title": str(row.get("conversation_title") or "").strip() or None,
                "conversation_type": str(row.get("conversation_type") or "").strip() or None,
                "link_type": str(row.get("link_type") or "").strip() or None,
                "created_at": row.get("created_at"),
            }
        )
    return [
        _build_room_payload(
            room=row,
            participants=participants_by_room.get(str(row.get("id") or "").strip(), []),
            sessions=sessions_by_room.get(str(row.get("id") or "").strip(), []),
            chat_links=links_by_room.get(str(row.get("id") or "").strip(), []),
        )
        for row in rows
    ]


def get_meeting_room_detail(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    room, _ = _ensure_room_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    participants = list_meeting_rooms(
        conn,
        tenant_id=tenant_id,
        current_user=current_user,
        limit=300,
    )
    room_payload = next((item for item in participants if str(item.get("id") or "").strip() == room_id), None)
    if not room_payload:
        # Fallback when room exists but list scope filtered unexpectedly.
        participant_rows = _fetch_room_participants(conn, tenant_id=tenant_id, room_ids=[room_id])
        session_rows = _fetch_room_sessions(conn, tenant_id=tenant_id, room_ids=[room_id])
        chat_link_rows = _fetch_room_chat_links(conn, tenant_id=tenant_id, room_ids=[room_id])
        room_payload = _build_room_payload(
            room=room,
            participants=[
                {
                    "participant_id": str(row.get("participant_id") or "").strip() or None,
                    "user_id": str(row.get("user_id") or "").strip() or None,
                    "employee_id": str(row.get("employee_id") or "").strip() or None,
                    "participant_role": str(row.get("participant_role") or "").strip() or PARTICIPANT_ROLE_PARTICIPANT,
                    "full_name": str(row.get("full_name") or "").strip() or str(row.get("username") or "").strip() or "-",
                    "username": str(row.get("username") or "").strip() or None,
                    "role": str(row.get("role") or "").strip() or None,
                    "site_id": str(row.get("site_id") or "").strip() or None,
                    "site_name": str(row.get("site_name") or "").strip() or None,
                    "invited_at": row.get("invited_at"),
                    "joined_at": row.get("joined_at"),
                    "left_at": row.get("left_at"),
                }
                for row in participant_rows
            ],
            sessions=[
                {
                    "id": str(row.get("session_id") or "").strip() or None,
                    "session_key": str(row.get("session_key") or "").strip() or None,
                    "media_backend": str(row.get("media_backend") or "").strip() or MEDIA_BACKEND_PION,
                    "state": str(row.get("state") or "").strip() or SESSION_STATE_CREATED,
                    "started_at": row.get("started_at"),
                    "ended_at": row.get("ended_at"),
                    "meta_json": dict(row.get("meta_json") or {}),
                    "created_at": row.get("created_at"),
                }
                for row in session_rows
            ],
            chat_links=[
                {
                    "id": str(row.get("link_id") or "").strip() or None,
                    "conversation_id": str(row.get("conversation_id") or "").strip() or None,
                    "conversation_title": str(row.get("conversation_title") or "").strip() or None,
                    "conversation_type": str(row.get("conversation_type") or "").strip() or None,
                    "link_type": str(row.get("link_type") or "").strip() or None,
                    "created_at": row.get("created_at"),
                }
                for row in chat_link_rows
            ],
        )
    room_payload["events"] = _fetch_recent_room_events(conn, tenant_id=tenant_id, room_id=room_id, limit=80)
    room_payload["connection_blueprint"] = _build_connection_blueprint()
    return room_payload


def create_meeting_room(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    title: str,
    participant_user_ids: list[str] | None = None,
    scheduled_for: datetime | None = None,
    room_key: str | None = None,
    settings_json: dict[str, Any] | None = None,
    linked_conversation_id: str | None = None,
    start_now: bool = False,
) -> dict[str, Any]:
    _, actor_user_id, actor_employee_id = _ensure_actor_context(current_user)
    actor_role = str(current_user.get("role") or "").strip() or None
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "회의 제목이 필요합니다.")
    normalized_room_key = _normalize_room_key(room_key) or _generate_room_key()
    all_participant_ids = _normalize_uuid_list([actor_user_id, *list(participant_user_ids or [])])
    directory = _fetch_user_directory_map(conn, tenant_id=tenant_id, user_ids=all_participant_ids)
    if len(directory) != len(all_participant_ids):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "유효하지 않은 참가자가 포함되어 있습니다.")
    linked_conversation = _validate_linked_conversation(conn, tenant_id=tenant_id, conversation_id=linked_conversation_id)
    room_id = str(uuid.uuid4())
    room_state = ROOM_STATE_LIVE if start_now else ROOM_STATE_SCHEDULED
    now = _utc_now()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meeting_rooms (
                id,
                tenant_id,
                title,
                host_user_id,
                room_key,
                state,
                scheduled_for,
                settings_json,
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
                room_id,
                tenant_id,
                normalized_title,
                actor_user_id,
                normalized_room_key,
                room_state,
                scheduled_for,
                _json_dumps(settings_json),
            ),
        )
        for user_id in all_participant_ids:
            participant_role = PARTICIPANT_ROLE_HOST if user_id == actor_user_id else PARTICIPANT_ROLE_PARTICIPANT
            directory_row = directory.get(user_id) or {}
            _insert_meeting_participant_row(
                conn,
                tenant_id=tenant_id,
                room_id=room_id,
                user_id=user_id,
                employee_id=str(directory_row.get("employee_id") or "").strip() or None,
                participant_role=participant_role,
                joined_at=now if start_now and user_id == actor_user_id else None,
            )
        if linked_conversation:
            cur.execute(
                """
                INSERT INTO meeting_chat_links (
                    id,
                    tenant_id,
                    meeting_room_id,
                    conversation_id,
                    link_type,
                    created_at
                )
                VALUES (%s, %s, %s, %s, 'primary', timezone('utc', now()))
                ON CONFLICT (meeting_room_id, conversation_id)
                DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    room_id,
                    linked_conversation,
                ),
            )

    host_name = str(current_user.get("full_name") or "").strip() or str(current_user.get("username") or "").strip() or "사용자"
    def _dispatch_room_invites():
        dispatcher = GroupwareNotificationDispatcher(conn)
        for participant_user_id in all_participant_ids:
            if participant_user_id == actor_user_id:
                continue
            dispatcher.dispatch_in_app(
                tenant_id=tenant_id,
                user_id=participant_user_id,
                category="info",
                dedupe_key=f"meeting-room:{room_id}:{participant_user_id}",
                message=f"[{normalized_title}] {host_name}님이 회의에 초대했습니다.",
                payload={
                    "module": "meetings",
                    "meeting_room_id": room_id,
                    "room_key": normalized_room_key,
                    "scheduled_for": scheduled_for.isoformat() if isinstance(scheduled_for, datetime) else None,
                },
            )
    _run_meetings_best_effort(conn, _dispatch_room_invites)

    def _write_room_created_audit():
        GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="room_created",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_room",
            target_id=room_id,
            detail={
                "participant_user_ids": all_participant_ids,
                "room_key": normalized_room_key,
                "start_now": start_now,
                "linked_conversation_id": linked_conversation,
            },
        )
    _run_meetings_best_effort(conn, _write_room_created_audit)

    if start_now:
        start_meeting_session(
            conn,
            tenant_id=tenant_id,
            room_id=room_id,
            current_user=current_user,
            media_backend=MEDIA_BACKEND_PION,
            session_key=None,
            meta_json={"origin": "room_create"},
        )

    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def add_meeting_participants(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    current_user: dict[str, Any],
    participant_user_ids: list[str],
) -> dict[str, Any]:
    room, _ = _ensure_host_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    requested_ids = [user_id for user_id in _normalize_uuid_list(participant_user_ids) if user_id != actor_user_id]
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id::text AS user_id
            FROM meeting_participants
            WHERE tenant_id = %s
              AND meeting_room_id::text = %s
            """,
            (tenant_id, room_id),
        )
        existing_user_ids = {
            str(row.get("user_id") or "").strip()
            for row in (cur.fetchall() or [])
            if str(row.get("user_id") or "").strip()
        }
    normalized_ids = [user_id for user_id in requested_ids if user_id not in existing_user_ids]
    if not normalized_ids:
        return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    directory = _fetch_user_directory_map(conn, tenant_id=tenant_id, user_ids=normalized_ids)
    if len(directory) != len(normalized_ids):
        raise _http_error(status.HTTP_400_BAD_REQUEST, "유효하지 않은 참가자가 포함되어 있습니다.")
    for user_id in normalized_ids:
        directory_row = directory.get(user_id) or {}
        _insert_meeting_participant_row(
            conn,
            tenant_id=tenant_id,
            room_id=room_id,
            user_id=user_id,
            employee_id=str(directory_row.get("employee_id") or "").strip() or None,
            participant_role=PARTICIPANT_ROLE_PARTICIPANT,
            joined_at=None,
        )

    # Participant insertion is the primary action. Notifications and audit writes
    # should not turn a successful invite into a 500 for the caller.
    room_title = str(room.get("title") or "").strip() or "회의"
    inviter_name = str(current_user.get("full_name") or "").strip() or str(current_user.get("username") or "").strip() or "사용자"
    def _dispatch_participant_invites():
        dispatcher = GroupwareNotificationDispatcher(conn)
        for user_id in normalized_ids:
            dispatcher.dispatch_in_app(
                tenant_id=tenant_id,
                user_id=user_id,
                category="info",
                dedupe_key=f"meeting-invite:{room_id}:{user_id}",
                message=f"[{room_title}] {inviter_name}님이 회의 참가자로 추가했습니다.",
                payload={"module": "meetings", "meeting_room_id": room_id, "room_key": room.get("room_key")},
            )
    _run_meetings_best_effort(conn, _dispatch_participant_invites)

    def _write_participants_added_audit():
        GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="participants_added",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_room",
            target_id=room_id,
            detail={"participant_user_ids": normalized_ids},
        )
    _run_meetings_best_effort(conn, _write_participants_added_audit)
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def add_meeting_chat_link(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    current_user: dict[str, Any],
    conversation_id: str,
    link_type: str = "primary",
) -> dict[str, Any]:
    _ensure_host_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    resolved_conversation_id = _validate_linked_conversation(conn, tenant_id=tenant_id, conversation_id=conversation_id)
    normalized_link_type = str(link_type or "").strip().lower() or "primary"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meeting_chat_links (
                id,
                tenant_id,
                meeting_room_id,
                conversation_id,
                link_type,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, timezone('utc', now()))
            ON CONFLICT (meeting_room_id, conversation_id)
            DO UPDATE
            SET link_type = EXCLUDED.link_type
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                room_id,
                resolved_conversation_id,
                normalized_link_type,
            ),
        )
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def start_meeting_session(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    current_user: dict[str, Any],
    media_backend: str = MEDIA_BACKEND_PION,
    session_key: str | None = None,
    meta_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    room, participant = _ensure_host_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    normalized_backend = _normalize_choice(media_backend, allowed=ALLOWED_MEDIA_BACKENDS, field_name="media_backend")
    normalized_session_key = str(session_key or "").strip().lower() or _generate_session_key()
    session_id = str(uuid.uuid4())
    connection_blueprint = _build_connection_blueprint()
    payload = dict(meta_json or {})
    payload.setdefault("connection_blueprint", connection_blueprint)
    payload.setdefault("supports_reconnect", True)
    payload.setdefault("supports_screen_share", True)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meeting_rooms
            SET state = %s,
                ended_at = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id::text = %s
            """,
            (ROOM_STATE_LIVE, tenant_id, room_id),
        )
        cur.execute(
            """
            INSERT INTO meeting_sessions (
                id,
                tenant_id,
                meeting_room_id,
                session_key,
                media_backend,
                state,
                started_at,
                meta_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, timezone('utc', now()), %s::jsonb, timezone('utc', now())
            )
            """,
            (
                session_id,
                tenant_id,
                room_id,
                normalized_session_key,
                normalized_backend,
                SESSION_STATE_LIVE,
                _json_dumps(payload),
            ),
        )
        if participant:
            cur.execute(
                """
                UPDATE meeting_participants
                SET joined_at = COALESCE(joined_at, timezone('utc', now())),
                    left_at = NULL
                WHERE tenant_id = %s
                  AND meeting_room_id::text = %s
                  AND user_id::text = %s
                """,
                (tenant_id, room_id, actor_user_id),
            )
        cur.execute(
            """
            INSERT INTO meeting_events (
                id,
                tenant_id,
                meeting_room_id,
                session_id,
                actor_user_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                room_id,
                session_id,
                actor_user_id,
                "session_started",
                _json_dumps({"media_backend": normalized_backend, "connection_blueprint": connection_blueprint}),
            ),
        )

    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="session_started",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_session",
            target_id=session_id,
            detail={"meeting_room_id": room_id, "media_backend": normalized_backend},
        ),
    )
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def join_meeting_session(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    session_id: str,
    current_user: dict[str, Any],
    reconnect: bool = False,
    device_type: str = "web",
) -> dict[str, Any]:
    room, participant, session_row = _ensure_session_access(
        conn,
        tenant_id=tenant_id,
        room_id=room_id,
        session_id=session_id,
        current_user=current_user,
    )
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    if str(session_row.get("state") or "").strip() != SESSION_STATE_LIVE:
        raise _http_error(status.HTTP_409_CONFLICT, "현재 참여 가능한 회의 세션이 아닙니다.")
    if not participant:
        raise _http_error(status.HTTP_403_FORBIDDEN, "초대된 참가자만 회의에 입장할 수 있습니다.")
    event_type = "reconnect" if reconnect else "join"
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meeting_participants
            SET joined_at = COALESCE(joined_at, timezone('utc', now())),
                left_at = NULL
            WHERE tenant_id = %s
              AND meeting_room_id::text = %s
              AND user_id::text = %s
            """,
            (tenant_id, room_id, actor_user_id),
        )
        cur.execute(
            """
            INSERT INTO meeting_events (
                id,
                tenant_id,
                meeting_room_id,
                session_id,
                actor_user_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                room_id,
                session_id,
                actor_user_id,
                event_type,
                _json_dumps({"device_type": str(device_type or "").strip().lower() or "web"}),
            ),
        )

    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type=event_type,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_session",
            target_id=session_id,
            detail={"meeting_room_id": room_id},
        ),
    )
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def leave_meeting_session(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    session_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _, participant, _ = _ensure_session_access(
        conn,
        tenant_id=tenant_id,
        room_id=room_id,
        session_id=session_id,
        current_user=current_user,
    )
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    if participant:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE meeting_participants
                SET left_at = timezone('utc', now())
                WHERE tenant_id = %s
                  AND meeting_room_id::text = %s
                  AND user_id::text = %s
                """,
                (tenant_id, room_id, actor_user_id),
            )
            cur.execute(
                """
                INSERT INTO meeting_events (
                    id,
                    tenant_id,
                    meeting_room_id,
                    session_id,
                    actor_user_id,
                    event_type,
                    payload_json,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, 'leave', '{}'::jsonb, timezone('utc', now()))
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    room_id,
                    session_id,
                    actor_user_id,
                ),
            )
    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="leave",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_session",
            target_id=session_id,
            detail={"meeting_room_id": room_id},
        ),
    )
    return {"ok": True}


def record_meeting_event(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    session_id: str,
    current_user: dict[str, Any],
    event_type: str,
    payload_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _, _, session_row = _ensure_session_access(
        conn,
        tenant_id=tenant_id,
        room_id=room_id,
        session_id=session_id,
        current_user=current_user,
    )
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    normalized_event_type = str(event_type or "").strip().lower()
    if normalized_event_type not in ALLOWED_EVENT_TYPES:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "meeting event_type 값이 올바르지 않습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO meeting_events (
                id,
                tenant_id,
                meeting_room_id,
                session_id,
                actor_user_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
            RETURNING id::text AS id, created_at
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                room_id,
                session_id,
                actor_user_id,
                normalized_event_type,
                _json_dumps(payload_json),
            ),
        )
        event_row = cur.fetchone() or {}
    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type=normalized_event_type,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_session",
            target_id=session_id,
            detail={"meeting_room_id": room_id, "session_state": session_row.get("state")},
        ),
    )
    return {
        "id": str(event_row.get("id") or "").strip() or None,
        "room_id": room_id,
        "session_id": session_id,
        "event_type": normalized_event_type,
        "payload_json": dict(payload_json or {}),
        "created_at": event_row.get("created_at"),
    }


def end_meeting_session(
    conn,
    *,
    tenant_id: str,
    room_id: str,
    session_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _ensure_host_access(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)
    _, _, session_row = _ensure_session_access(
        conn,
        tenant_id=tenant_id,
        room_id=room_id,
        session_id=session_id,
        current_user=current_user,
    )
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE meeting_sessions
            SET state = %s,
                ended_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND meeting_room_id::text = %s
              AND id::text = %s
            """,
            (SESSION_STATE_ENDED, tenant_id, room_id, session_id),
        )
        cur.execute(
            """
            UPDATE meeting_rooms
            SET state = %s,
                ended_at = timezone('utc', now()),
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id::text = %s
            """,
            (ROOM_STATE_ENDED, tenant_id, room_id),
        )
        cur.execute(
            """
            INSERT INTO meeting_events (
                id,
                tenant_id,
                meeting_room_id,
                session_id,
                actor_user_id,
                event_type,
                payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, 'session_ended', '{}'::jsonb, timezone('utc', now()))
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                room_id,
                session_id,
                actor_user_id,
            ),
        )

    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="session_ended",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="meeting_session",
            target_id=session_id,
            detail={"meeting_room_id": room_id, "previous_state": session_row.get("state")},
        ),
    )
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=room_id, current_user=current_user)


def get_meeting_room_by_key(
    conn,
    *,
    tenant_id: str,
    room_key: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    room = _fetch_room_row(conn, tenant_id=tenant_id, room_key=_normalize_room_key(room_key))
    if not room:
        raise _http_error(status.HTTP_404_NOT_FOUND, "회의 링크를 찾을 수 없습니다.")
    return get_meeting_room_detail(conn, tenant_id=tenant_id, room_id=str(room.get("id") or "").strip(), current_user=current_user)


def record_rollout_check(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
    environment_key: str,
    check_type: str,
    status_value: str,
    summary: str,
    detail_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    actor_user_id = str(current_user.get("id") or "").strip()
    actor_role = str(current_user.get("role") or "").strip() or None
    if not _can_manage_rollout(actor_role):
        raise _http_error(status.HTTP_403_FORBIDDEN, "rollout 체크는 관리자만 기록할 수 있습니다.")
    normalized_status = _normalize_choice(status_value, allowed=ALLOWED_ROLLOUT_STATUSES, field_name="rollout status")
    normalized_environment = str(environment_key or "").strip().lower() or "default"
    normalized_check_type = str(check_type or "").strip().lower()
    normalized_summary = str(summary or "").strip()
    if not normalized_check_type or not normalized_summary:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "check_type과 summary가 필요합니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO groupware_rollout_checks (
                id,
                tenant_id,
                module_key,
                environment_key,
                check_type,
                status,
                summary,
                detail_json,
                checked_by,
                checked_at,
                created_at
            )
            VALUES (
                %s, %s, 'meetings', %s, %s, %s, %s, %s::jsonb, %s,
                timezone('utc', now()),
                timezone('utc', now())
            )
            RETURNING id::text AS id, checked_at, created_at
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                normalized_environment,
                normalized_check_type,
                normalized_status,
                normalized_summary,
                _json_dumps(detail_json),
                actor_user_id,
            ),
        )
        row = cur.fetchone() or {}
    _run_meetings_best_effort(
        conn,
        lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="meetings",
            action_type="rollout_check_recorded",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="groupware_rollout_check",
            target_id=str(row.get("id") or "").strip() or None,
            detail={
                "environment_key": normalized_environment,
                "check_type": normalized_check_type,
                "status": normalized_status,
            },
        ),
    )
    return {
        "id": str(row.get("id") or "").strip() or None,
        "module_key": "meetings",
        "environment_key": normalized_environment,
        "check_type": normalized_check_type,
        "status": normalized_status,
        "summary": normalized_summary,
        "detail_json": dict(detail_json or {}),
        "checked_by": actor_user_id,
        "checked_at": row.get("checked_at"),
        "created_at": row.get("created_at"),
    }


def get_meeting_rollout_status(
    conn,
    *,
    tenant_id: str,
    current_user: dict[str, Any],
) -> dict[str, Any]:
    _ensure_actor_context(current_user)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::int AS cnt
            FROM meeting_rooms
            WHERE tenant_id = %s
            """,
            (tenant_id,),
        )
        total_rooms = int((cur.fetchone() or {}).get("cnt") or 0)
        cur.execute(
            """
            SELECT COUNT(*)::int AS cnt
            FROM meeting_rooms
            WHERE tenant_id = %s
              AND state = %s
            """,
            (tenant_id, ROOM_STATE_LIVE),
        )
        live_rooms = int((cur.fetchone() or {}).get("cnt") or 0)
        cur.execute(
            """
            SELECT COUNT(*)::int AS cnt
            FROM meeting_sessions
            WHERE tenant_id = %s
              AND state = %s
            """,
            (tenant_id, SESSION_STATE_LIVE),
        )
        live_sessions = int((cur.fetchone() or {}).get("cnt") or 0)
    rollout_checks = _fetch_rollout_checks(conn, tenant_id=tenant_id, module_key="meetings")
    failing_checks = [item for item in rollout_checks if item.get("status") in {ROLLOUT_STATUS_BLOCKED, ROLLOUT_STATUS_FAILED}]
    passing_checks = [item for item in rollout_checks if item.get("status") in {ROLLOUT_STATUS_READY, ROLLOUT_STATUS_PASSED}]
    connection_blueprint = _build_connection_blueprint()
    return {
        "module_key": "meetings",
        "deployment_topology": {
            "core_api": {"status": "active"},
            "rt_gateway": {
                "status": "configured" if connection_blueprint.get("rt_gateway_public_url") else "planned",
                "public_url": connection_blueprint.get("rt_gateway_public_url"),
            },
            "media_sfu": {
                "status": "configured" if connection_blueprint.get("media_sfu_public_url") else "planned",
                "public_url": connection_blueprint.get("media_sfu_public_url"),
            },
            "coturn": {
                "status": "configured" if connection_blueprint.get("coturn_server_uris") else "planned",
                "uris": connection_blueprint.get("coturn_server_uris") or [],
            },
        },
        "connection_blueprint": connection_blueprint,
        "lifecycle": {
            "supports_instant_meeting": True,
            "supports_scheduled_meeting": True,
            "supports_meeting_links": True,
            "supports_reconnect": True,
            "supports_screen_share": True,
            "supports_mobile_clients": True,
        },
        "runtime": {
            "room_count": total_rooms,
            "live_room_count": live_rooms,
            "live_session_count": live_sessions,
        },
        "rollout_checks": rollout_checks,
        "readiness": {
            "status": (
                ROLLOUT_STATUS_BLOCKED
                if failing_checks
                else (ROLLOUT_STATUS_READY if passing_checks else ROLLOUT_STATUS_PENDING)
            ),
            "passing_check_count": len(passing_checks),
            "failing_check_count": len(failing_checks),
            "load_test_recorded": any(item.get("check_type") == "load_test" and item.get("status") in {ROLLOUT_STATUS_READY, ROLLOUT_STATUS_PASSED} for item in rollout_checks),
            "tenant_isolation_recorded": any(item.get("check_type") == "tenant_isolation" and item.get("status") in {ROLLOUT_STATUS_READY, ROLLOUT_STATUS_PASSED} for item in rollout_checks),
        },
    }
