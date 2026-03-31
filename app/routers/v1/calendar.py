from __future__ import annotations

import json
import re

from datetime import date as dt_date, datetime, time as dt_time, timedelta, timezone
from uuid import UUID, uuid4
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...db import ensure_calendar_runtime_shape
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...schemas import (
    CalendarAvailabilityLaneOut,
    CalendarAvailabilityOut,
    CalendarAttendeeIn,
    CalendarAttendeeOut,
    CalendarAttendeeOptionOut,
    CalendarAttachmentOut,
    CalendarActionItemOut,
    CalendarBusySlotOut,
    CalendarBookingLinkCreateIn,
    CalendarBookingLinkOut,
    CalendarBookingLinkPublicOut,
    CalendarBookingQuestionOut,
    CalendarBookingSlotOut,
    CalendarBookingLinkUpdateIn,
    CalendarCapabilityOut,
    CalendarCommentIn,
    CalendarCommentOut,
    CalendarContainerOut,
    CalendarCustomFieldRowOut,
    CalendarEventOut,
    CalendarEventUpsertIn,
    CalendarMiniMonthDayOut,
    CalendarNoteOut,
    CalendarResourceOut,
    CalendarReminderIn,
    CalendarReminderOut,
    CalendarPublicBookingSubmitIn,
    CalendarPublicBookingSubmitOut,
    CalendarSuggestedSlotOut,
    CalendarSyncConnectionUpsertIn,
    CalendarSyncConnectionOut,
    CalendarTemplateOut,
    CalendarWorkspaceOut,
)
from ...utils.permissions import (
    ROLE_DEVELOPER,
    ROLE_HQ_ADMIN,
    ROLE_OFFICER,
    ROLE_SUPERVISOR,
    ROLE_VICE_SUPERVISOR,
    can_create_calendar_event,
    can_manage_calendar_booking_links,
    can_manage_calendar_shared,
    can_manage_calendar_sync,
    can_view_calendar,
    normalize_user_role,
)
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=[Depends(apply_rate_limit)])
KST = timezone(timedelta(hours=9))


def _today_kst() -> dt_date:
    return datetime.now(KST).date()


def _raise_calendar_error(status_code: int, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"message": message})


def _parse_anchor_date(raw: str | None) -> dt_date:
    value = str(raw or "").strip()
    if not value:
        return _today_kst()
    try:
        return dt_date.fromisoformat(value)
    except ValueError:
        return _today_kst()


def _resolve_calendar_audience(user: dict[str, Any]) -> str:
    role = normalize_user_role(user.get("role"))
    if role in {ROLE_DEVELOPER, ROLE_HQ_ADMIN}:
        return "hq"
    if role == ROLE_SUPERVISOR:
        return "supervisor"
    if role == ROLE_VICE_SUPERVISOR:
        return "vice"
    return "officer"


def _role_label(user: dict[str, Any]) -> str:
    role = normalize_user_role(user.get("role"))
    if role == ROLE_DEVELOPER:
        return "Developer"
    if role == ROLE_HQ_ADMIN:
        return "HQ Admin"
    if role == ROLE_SUPERVISOR:
        return "Supervisor"
    if role == ROLE_VICE_SUPERVISOR:
        return "Vice Supervisor"
    return "Officer"


def _site_scope_label(conn, user: dict[str, Any], tenant_id: str) -> str:
    audience = _resolve_calendar_audience(user)
    if audience == "hq":
        return "전체 운영 범위"
    if audience == "officer":
        return "본인 일정 범위"
    site_id = str(user.get("site_id") or "").strip()
    site_code = str(user.get("site_code") or "").strip().upper()
    if not site_id and not site_code:
        return "팀 일정 범위"
    with conn.cursor() as cur:
        if site_id:
            cur.execute(
                """
                SELECT site_name, site_code
                FROM sites
                WHERE tenant_id = %s
                  AND id = %s
                LIMIT 1
                """,
                (tenant_id, site_id),
            )
        else:
            cur.execute(
                """
                SELECT site_name, site_code
                FROM sites
                WHERE tenant_id = %s
                  AND upper(trim(site_code)) = upper(trim(%s))
                LIMIT 1
                """,
                (tenant_id, site_code),
            )
        row = cur.fetchone() or {}
    site_name = str(row.get("site_name") or "").strip()
    site_code_value = str(row.get("site_code") or site_code).strip().upper()
    if site_name and site_code_value:
        return f"{site_name} ({site_code_value})"
    return site_name or site_code_value or "팀 일정 범위"


def _build_calendar_capabilities(user: dict[str, Any]) -> CalendarCapabilityOut:
    role = user.get("role")
    return CalendarCapabilityOut(
        can_view=can_view_calendar(role),
        can_create=can_create_calendar_event(role),
        can_manage_shared=can_manage_calendar_shared(role),
        can_manage_booking_links=can_manage_calendar_booking_links(role),
        can_manage_sync=can_manage_calendar_sync(role),
    )


def _normalize_calendar_permission(permission: str | None) -> str:
    value = str(permission or "").strip().lower()
    if value in {"owner", "edit", "free_busy_only", "view_only"}:
        return value
    return "view_only"


def _can_edit_calendar_container(permission: str | None) -> bool:
    return _normalize_calendar_permission(permission) in {"owner", "edit"}


def _calendar_scope_badge(scope_type: str | None) -> str:
    normalized = str(scope_type or "").strip().lower()
    if normalized == "shared":
        return "공유"
    if normalized == "team":
        return "팀"
    return "개인"


def _calendar_scope_owner_label(scope_type: str | None) -> str:
    normalized = str(scope_type or "").strip().lower()
    if normalized == "shared":
        return "공용 일정"
    if normalized == "team":
        return "팀 운영"
    return "내 일정"


def _to_uuid_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _resolve_calendar_visible_range(view: str, anchor_date: dt_date) -> tuple[datetime, datetime]:
    normalized = str(view or "week").strip().lower()
    if normalized == "month":
        month_start = anchor_date.replace(day=1)
        first_cell = month_start - timedelta(days=(month_start.weekday() + 1) % 7)
        last_cell = first_cell + timedelta(days=42)
        return (
            datetime.combine(first_cell, datetime.min.time(), tzinfo=KST),
            datetime.combine(last_cell, datetime.min.time(), tzinfo=KST),
        )
    if normalized == "agenda":
        start_date = anchor_date
        end_date = anchor_date + timedelta(days=30)
        return (
            datetime.combine(start_date, datetime.min.time(), tzinfo=KST),
            datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=KST),
        )
    if normalized == "booking-links":
        return (
            datetime.combine(anchor_date, datetime.min.time(), tzinfo=KST),
            datetime.combine(anchor_date + timedelta(days=1), datetime.min.time(), tzinfo=KST),
        )
    week_start = anchor_date - timedelta(days=anchor_date.weekday())
    week_end = week_start + timedelta(days=7)
    return (
        datetime.combine(week_start, datetime.min.time(), tzinfo=KST),
        datetime.combine(week_end, datetime.min.time(), tzinfo=KST),
    )


def _build_calendar_container_lookup(conn, *, tenant_id: str, user: dict[str, Any]) -> dict[str, CalendarContainerOut]:
    return {str(row.id): row for row in _fetch_workspace_containers(conn, tenant_id=tenant_id, user=user)}


def _resolve_selected_container(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    audience: str,
    requested_container_id: str | None,
) -> CalendarContainerOut | None:
    containers = _fetch_workspace_containers(conn, tenant_id=tenant_id, user=user)
    if not containers:
        return None
    lookup = {str(row.id): row for row in containers}
    requested_key = _to_uuid_text(requested_container_id)
    if requested_key and requested_key in lookup:
        return lookup[requested_key]
    selected_id = _pick_selected_container_id(containers, audience)
    return lookup.get(str(selected_id or "")) or containers[0]


def _fetch_attendee_options(conn, *, tenant_id: str, user: dict[str, Any], audience: str) -> list[CalendarAttendeeOptionOut]:
    clauses = ["e.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    site_id = _to_uuid_text(user.get("site_id"))
    if audience in {"supervisor", "vice"} and site_id:
        clauses.append("e.site_id = %s")
        params.append(site_id)
    elif audience == "officer":
        employee_id = _to_uuid_text(user.get("employee_id"))
        if employee_id:
            clauses.append("e.id = %s")
            params.append(employee_id)
        else:
            return []
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id AS employee_id,
                   e.full_name,
                   e.employee_code,
                   COALESCE(s.site_name, '') AS site_name,
                   u.user_id,
                   u.username
            FROM employees e
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN LATERAL (
                SELECT au.id AS user_id, COALESCE(au.username, '') AS username
                FROM arls_users au
                WHERE au.employee_id = e.id
                ORDER BY au.created_at DESC NULLS LAST, au.id
                LIMIT 1
            ) u ON TRUE
            WHERE {" AND ".join(clauses)}
            ORDER BY e.full_name ASC, e.employee_code ASC
            LIMIT 120
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    options: list[CalendarAttendeeOptionOut] = []
    for row in rows:
        name = str(row.get("full_name") or row.get("employee_code") or "직원").strip() or "직원"
        employee_code = str(row.get("employee_code") or "").strip()
        site_name = str(row.get("site_name") or "").strip()
        subtitle_parts = [part for part in [employee_code, site_name] if part]
        options.append(
            CalendarAttendeeOptionOut(
                user_id=row.get("user_id"),
                employee_id=row.get("employee_id"),
                display_name=name,
                subtitle=" · ".join(subtitle_parts) or None,
                email=str(row.get("username") or "").strip() or None,
            )
        )
    return options


def _fetch_event_relations(
    conn,
    *,
    event_ids: list[str],
    user_id: str | None,
) -> tuple[
    dict[str, list[CalendarAttendeeOut]],
    dict[str, list[CalendarReminderOut]],
    dict[str, list[CalendarNoteOut]],
    dict[str, list[CalendarCommentOut]],
    dict[str, list[CalendarActionItemOut]],
    dict[str, list[CalendarAttachmentOut]],
]:
    if not event_ids:
        return {}, {}, {}, {}, {}, {}
    attendees_by_event: dict[str, list[CalendarAttendeeOut]] = {}
    reminders_by_event: dict[str, list[CalendarReminderOut]] = {}
    notes_by_event: dict[str, list[CalendarNoteOut]] = {}
    comments_by_event: dict[str, list[CalendarCommentOut]] = {}
    action_items_by_event: dict[str, list[CalendarActionItemOut]] = {}
    attachments_by_event: dict[str, list[CalendarAttachmentOut]] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, event_id, user_id, employee_id, email, display_name, is_required, is_organizer, rsvp_status
            FROM calendar_attendees
            WHERE event_id = ANY(%s::uuid[])
            ORDER BY is_organizer DESC, created_at ASC
            """,
            (event_ids,),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            attendees_by_event.setdefault(event_key, []).append(CalendarAttendeeOut(**dict(row)))

        cur.execute(
            """
            SELECT id, event_id, channel, minutes_before, absolute_trigger_at, snoozed_until
            FROM calendar_reminders
            WHERE event_id = ANY(%s::uuid[])
            ORDER BY COALESCE(minutes_before, 999999) ASC, created_at ASC
            """,
            (event_ids,),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            reminders_by_event.setdefault(event_key, []).append(CalendarReminderOut(**dict(row)))

        note_params: list[Any] = [event_ids]
        note_filter = "event_id = ANY(%s::uuid[])"
        if user_id:
            note_filter += " AND (note_type = 'shared' OR author_user_id = %s)"
            note_params.append(user_id)
        else:
            note_filter += " AND note_type = 'shared'"
        cur.execute(
            f"""
            SELECT n.id,
                   n.event_id,
                   n.note_type,
                   n.body,
                   n.updated_at,
                   COALESCE(u.full_name, '') AS author_label
            FROM calendar_notes n
            LEFT JOIN arls_users u ON u.id = n.author_user_id
            WHERE {note_filter}
            ORDER BY n.note_type ASC, n.updated_at DESC
            """,
            tuple(note_params),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            notes_by_event.setdefault(event_key, []).append(CalendarNoteOut(**dict(row)))

        cur.execute(
            """
            SELECT c.id,
                   c.event_id,
                   c.body,
                   c.is_internal,
                   c.created_at,
                   COALESCE(u.full_name, '') AS author_label
            FROM calendar_comments c
            LEFT JOIN arls_users u ON u.id = c.author_user_id
            WHERE c.event_id = ANY(%s::uuid[])
            ORDER BY c.created_at ASC
            """,
            (event_ids,),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            comments_by_event.setdefault(event_key, []).append(CalendarCommentOut(**dict(row)))

        cur.execute(
            """
            SELECT ai.id,
                   ai.event_id,
                   ai.body,
                   ai.state,
                   ai.due_at,
                   COALESCE(u.full_name, '') AS assignee_label
            FROM calendar_action_items ai
            LEFT JOIN arls_users u ON u.id = ai.assignee_user_id
            WHERE ai.event_id = ANY(%s::uuid[])
            ORDER BY ai.created_at ASC
            """,
            (event_ids,),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            action_items_by_event.setdefault(event_key, []).append(CalendarActionItemOut(**dict(row)))

        cur.execute(
            """
            SELECT id, event_id, label, url, mime_type, size_bytes
            FROM calendar_attachments
            WHERE event_id = ANY(%s::uuid[])
            ORDER BY created_at ASC
            """,
            (event_ids,),
        )
        for row in cur.fetchall() or []:
            event_key = str(row.get("event_id") or "")
            attachments_by_event.setdefault(event_key, []).append(CalendarAttachmentOut(**dict(row)))
    return attendees_by_event, reminders_by_event, notes_by_event, comments_by_event, action_items_by_event, attachments_by_event


def _fetch_events(
    conn,
    *,
    tenant_id: str,
    container_id: str,
    range_start: datetime,
    range_end: datetime,
    user_id: str | None,
) -> list[CalendarEventOut]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, container_id, title, starts_at, ends_at, timezone, is_all_day,
                   recurrence_rule, availability_status, visibility, location,
                   conferencing_provider, conferencing_url, description, custom_fields_json,
                   resource_id, COALESCE(cr.resource_name, '') AS resource_label,
                   status
            FROM calendar_events
            LEFT JOIN calendar_resources cr ON cr.id = calendar_events.resource_id
            WHERE tenant_id = %s
              AND container_id = %s
              AND starts_at < %s
              AND ends_at > %s
            ORDER BY starts_at ASC, created_at ASC
            LIMIT 200
            """,
            (tenant_id, container_id, range_end, range_start),
        )
        rows = cur.fetchall() or []
    event_ids = [str(row.get("id") or "") for row in rows if row.get("id")]
    attendees_by_event, reminders_by_event, notes_by_event, comments_by_event, action_items_by_event, attachments_by_event = _fetch_event_relations(
        conn,
        event_ids=event_ids,
        user_id=user_id,
    )
    events: list[CalendarEventOut] = []
    for row in rows:
        event_key = str(row.get("id") or "")
        payload = dict(row)
        payload["attendees"] = attendees_by_event.get(event_key, [])
        payload["reminders"] = reminders_by_event.get(event_key, [])
        payload["notes"] = notes_by_event.get(event_key, [])
        payload["comments"] = comments_by_event.get(event_key, [])
        payload["action_items"] = action_items_by_event.get(event_key, [])
        payload["attachments"] = attachments_by_event.get(event_key, [])
        payload["custom_fields"] = _normalize_calendar_custom_field_rows(payload.get("custom_fields_json"))
        events.append(CalendarEventOut(**payload))
    return events


def _pick_selected_event(events: list[CalendarEventOut], *, selected_date: dt_date, requested_event_id: str | None) -> CalendarEventOut | None:
    if not events:
        return None
    requested_key = _to_uuid_text(requested_event_id)
    if requested_key:
        for event in events:
            if str(event.id) == requested_key:
                return event
    selected_key = selected_date.isoformat()
    for event in events:
        try:
            if event.starts_at.astimezone(KST).date().isoformat() == selected_key:
                return event
        except Exception:
            continue
    return events[0]


def _validate_calendar_event_payload(payload: CalendarEventUpsertIn) -> None:
    if payload.ends_at <= payload.starts_at:
        _raise_calendar_error(status.HTTP_400_BAD_REQUEST, "종료 시간은 시작 시간보다 뒤여야 합니다.")
    if not str(payload.title or "").strip():
        _raise_calendar_error(status.HTTP_400_BAD_REQUEST, "일정 제목을 입력해 주세요.")


def _collect_calendar_schedule_keys(
    *,
    user: dict[str, Any],
    attendees: list[CalendarAttendeeIn],
) -> tuple[list[str], list[str], list[str]]:
    user_ids: set[str] = set()
    employee_ids: set[str] = set()
    emails: set[str] = set()
    organizer_user_id = _to_uuid_text(user.get("id"))
    organizer_employee_id = _to_uuid_text(user.get("employee_id"))
    organizer_email = str(user.get("email") or user.get("username") or "").strip().lower()
    if organizer_user_id:
        user_ids.add(organizer_user_id)
    if organizer_employee_id:
        employee_ids.add(organizer_employee_id)
    if organizer_email:
        emails.add(organizer_email)
    for row in attendees:
        user_id = _to_uuid_text(row.user_id)
        employee_id = _to_uuid_text(row.employee_id)
        email = str(row.email or "").strip().lower()
        if user_id:
            user_ids.add(user_id)
        if employee_id:
            employee_ids.add(employee_id)
        if email:
            emails.add(email)
    return sorted(user_ids), sorted(employee_ids), sorted(emails)


def _fetch_calendar_conflict_rows(
    conn,
    *,
    tenant_id: str,
    starts_at: datetime,
    ends_at: datetime,
    exclude_event_id: str | None,
    attendee_user_ids: list[str],
    attendee_employee_ids: list[str],
    attendee_emails: list[str],
    resource_id: str | None,
) -> list[dict[str, Any]]:
    filters = [
        "e.tenant_id = %s",
        "e.starts_at < %s",
        "e.ends_at > %s",
        "e.status <> 'cancelled'",
    ]
    params: list[Any] = [tenant_id, ends_at, starts_at]
    exclude_key = _to_uuid_text(exclude_event_id)
    if exclude_key:
        filters.append("e.id <> %s")
        params.append(exclude_key)

    overlap_groups: list[str] = []
    if attendee_user_ids:
        overlap_groups.append(
            """
            EXISTS (
                SELECT 1
                FROM calendar_attendees cau
                WHERE cau.event_id = e.id
                  AND cau.user_id = ANY(%s::uuid[])
            )
            """
        )
        params.append(attendee_user_ids)
    if attendee_employee_ids:
        overlap_groups.append(
            """
            EXISTS (
                SELECT 1
                FROM calendar_attendees cae
                WHERE cae.event_id = e.id
                  AND cae.employee_id = ANY(%s::uuid[])
            )
            """
        )
        params.append(attendee_employee_ids)
    if attendee_emails:
        overlap_groups.append(
            """
            EXISTS (
                SELECT 1
                FROM calendar_attendees cam
                WHERE cam.event_id = e.id
                  AND lower(trim(COALESCE(cam.email, ''))) = ANY(%s::text[])
            )
            """
        )
        params.append(attendee_emails)
    if resource_id:
        overlap_groups.append("e.resource_id = %s")
        params.append(resource_id)
    if not overlap_groups:
        return []
    filters.append(f"({' OR '.join(overlap_groups)})")

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id,
                   e.title,
                   e.starts_at,
                   e.ends_at,
                   e.resource_id,
                   COALESCE(cr.resource_name, '') AS resource_label
            FROM calendar_events e
            LEFT JOIN calendar_resources cr ON cr.id = e.resource_id
            WHERE {' AND '.join(filters)}
            ORDER BY e.starts_at ASC
            LIMIT 20
            """,
            tuple(params),
        )
        return cur.fetchall() or []


def _validate_calendar_schedule_guards(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    payload: CalendarEventUpsertIn,
    exclude_event_id: str | None = None,
) -> None:
    attendee_user_ids, attendee_employee_ids, attendee_emails = _collect_calendar_schedule_keys(
        user=user,
        attendees=payload.attendees,
    )
    overlaps = _fetch_calendar_conflict_rows(
        conn,
        tenant_id=tenant_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        exclude_event_id=exclude_event_id,
        attendee_user_ids=attendee_user_ids,
        attendee_employee_ids=attendee_employee_ids,
        attendee_emails=attendee_emails,
        resource_id=_to_uuid_text(payload.resource_id),
    )
    if not overlaps:
        return
    first_row = overlaps[0]
    resource_key = _to_uuid_text(payload.resource_id)
    if resource_key and _to_uuid_text(first_row.get("resource_id")) == resource_key:
        resource_label = str(first_row.get("resource_label") or "선택한 회의실").strip() or "선택한 회의실"
        _raise_calendar_error(status.HTTP_409_CONFLICT, f"{resource_label}에 이미 다른 일정이 배정되어 있습니다.")
    _raise_calendar_error(status.HTTP_409_CONFLICT, "선택한 참석자 중 이미 같은 시간에 다른 일정이 있습니다.")


def _pick_calendar_site_scope_id(selected_container: CalendarContainerOut | None, user: dict[str, Any]) -> str | None:
    if selected_container and str(selected_container.scope_type or "").strip().lower() == "team":
        with_site = getattr(selected_container, "owner_label", None)
    return _to_uuid_text(user.get("site_id"))


def _fetch_available_resources(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    selected_container: CalendarContainerOut | None,
) -> list[CalendarResourceOut]:
    audience = _resolve_calendar_audience(user)
    filters = ["r.tenant_id = %s", "r.is_active = TRUE"]
    params: list[Any] = [tenant_id]
    site_id = _to_uuid_text(user.get("site_id"))
    if audience in {"supervisor", "vice"} and site_id:
        filters.append("(r.site_id = %s OR r.site_id IS NULL)")
        params.append(site_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT r.id,
                   r.resource_code,
                   r.resource_name,
                   r.resource_type,
                   r.capacity,
                   COALESCE(s.site_name, '') AS site_label
            FROM calendar_resources r
            LEFT JOIN sites s ON s.id = r.site_id
            WHERE {' AND '.join(filters)}
            ORDER BY COALESCE(s.site_name, ''), r.resource_name
            LIMIT 40
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    return [CalendarResourceOut(**dict(row)) for row in rows]


def _fetch_busy_rows_for_lane(
    conn,
    *,
    tenant_id: str,
    range_start: datetime,
    range_end: datetime,
    lane_type: str,
    lane_value: str,
    exclude_event_id: str | None = None,
) -> list[dict[str, Any]]:
    if lane_type not in {"user", "employee", "email", "resource"}:
        return []
    filters = [
        "e.tenant_id = %s",
        "e.starts_at < %s",
        "e.ends_at > %s",
        "e.status <> 'cancelled'",
    ]
    params: list[Any] = [tenant_id, range_end, range_start]
    exclude_key = _to_uuid_text(exclude_event_id)
    if exclude_key:
        filters.append("e.id <> %s")
        params.append(exclude_key)
    if lane_type == "resource":
        filters.append("e.resource_id = %s")
        params.append(lane_value)
    elif lane_type == "user":
        filters.append(
            """
            EXISTS (
                SELECT 1 FROM calendar_attendees ca
                WHERE ca.event_id = e.id
                  AND ca.user_id = %s
            )
            """
        )
        params.append(lane_value)
    elif lane_type == "employee":
        filters.append(
            """
            EXISTS (
                SELECT 1 FROM calendar_attendees ca
                WHERE ca.event_id = e.id
                  AND ca.employee_id = %s
            )
            """
        )
        params.append(lane_value)
    else:
        filters.append(
            """
            EXISTS (
                SELECT 1 FROM calendar_attendees ca
                WHERE ca.event_id = e.id
                  AND lower(trim(COALESCE(ca.email, ''))) = lower(trim(%s))
            )
            """
        )
        params.append(lane_value)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT e.id,
                   e.title,
                   e.starts_at,
                   e.ends_at,
                   e.status
            FROM calendar_events e
            WHERE {' AND '.join(filters)}
            ORDER BY e.starts_at ASC
            LIMIT 40
            """,
            tuple(params),
        )
        return cur.fetchall() or []


def _build_suggested_slots(
    *,
    anchor_date: dt_date,
    duration_minutes: int,
    lanes: list[CalendarAvailabilityLaneOut],
) -> list[CalendarSuggestedSlotOut]:
    busy_ranges = [
        (slot.starts_at, slot.ends_at)
        for lane in lanes
        for slot in lane.slots
    ]
    suggestions: list[CalendarSuggestedSlotOut] = []
    candidate_days = [anchor_date + timedelta(days=index) for index in range(3)]
    for day in candidate_days:
        if day.weekday() >= 5:
            continue
        slot_start = datetime.combine(day, datetime.min.time(), tzinfo=KST).replace(hour=9, minute=0)
        last_start = datetime.combine(day, datetime.min.time(), tzinfo=KST).replace(hour=17, minute=30)
        while slot_start <= last_start and len(suggestions) < 6:
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            has_overlap = any(slot_start < busy_end and slot_end > busy_start for busy_start, busy_end in busy_ranges)
            if not has_overlap:
                suggestions.append(
                    CalendarSuggestedSlotOut(
                        starts_at=slot_start,
                        ends_at=slot_end,
                        label=f"{slot_start.strftime('%m.%d (%a) %H:%M')} · {duration_minutes}분",
                        attendee_match_count=len([lane for lane in lanes if lane.lane_type == "attendee"]),
                        attendee_total_count=len([lane for lane in lanes if lane.lane_type == "attendee"]),
                        resource_ready=True,
                    )
                )
            slot_start += timedelta(minutes=30)
        if len(suggestions) >= 6:
            break
    return suggestions


def _upsert_calendar_event_relations(
    conn,
    *,
    event_id: str,
    user: dict[str, Any],
    attendees: list[CalendarAttendeeIn],
    reminders: list[CalendarReminderIn],
    shared_note: str | None,
    private_memo: str | None,
    action_items: list[str],
) -> None:
    organizer_user_id = _to_uuid_text(user.get("id"))
    organizer_employee_id = _to_uuid_text(user.get("employee_id"))
    organizer_label = str(user.get("full_name") or user.get("username") or "주최자").strip() or "주최자"
    organizer_email = str(user.get("email") or user.get("username") or "").strip() or None
    normalized_attendees: list[CalendarAttendeeIn] = []
    seen_keys: set[str] = set()
    for row in attendees:
        user_key = _to_uuid_text(row.user_id)
        employee_key = _to_uuid_text(row.employee_id)
        email_key = str(row.email or "").strip().lower()
        dedupe_key = user_key or employee_key or email_key
        if not dedupe_key or dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        normalized_attendees.append(row)
    organizer_key = organizer_user_id or organizer_employee_id or organizer_email or organizer_label
    if organizer_key and organizer_key not in seen_keys:
        normalized_attendees.insert(
            0,
            CalendarAttendeeIn(
                user_id=UUID(organizer_user_id) if organizer_user_id else None,
                employee_id=UUID(organizer_employee_id) if organizer_employee_id else None,
                email=organizer_email,
                display_name=organizer_label,
                is_required=True,
            ),
        )

    with conn.cursor() as cur:
        cur.execute("DELETE FROM calendar_attendees WHERE event_id = %s", (event_id,))
        for row in normalized_attendees:
            cur.execute(
                """
                INSERT INTO calendar_attendees (
                    id, event_id, user_id, employee_id, email, display_name, is_required, is_organizer, rsvp_status
                )
                VALUES (
                    arls_random_uuid(), %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    event_id,
                    _to_uuid_text(row.user_id),
                    _to_uuid_text(row.employee_id),
                    str(row.email or "").strip() or None,
                    str(row.display_name or "").strip() or organizer_label,
                    bool(row.is_required),
                    bool(
                        (organizer_user_id and _to_uuid_text(row.user_id) == organizer_user_id)
                        or (organizer_employee_id and _to_uuid_text(row.employee_id) == organizer_employee_id)
                    ),
                    "accepted"
                    if (
                        (organizer_user_id and _to_uuid_text(row.user_id) == organizer_user_id)
                        or (organizer_employee_id and _to_uuid_text(row.employee_id) == organizer_employee_id)
                    )
                    else "needs_action",
                ),
            )

        cur.execute("DELETE FROM calendar_reminders WHERE event_id = %s", (event_id,))
        for row in reminders:
            channel = str(row.channel or "in_app").strip() or "in_app"
            if row.minutes_before is None and row.absolute_trigger_at is None:
                continue
            cur.execute(
                """
                INSERT INTO calendar_reminders (
                    id, event_id, channel, minutes_before, absolute_trigger_at
                )
                VALUES (arls_random_uuid(), %s, %s, %s, %s)
                """,
                (
                    event_id,
                    channel,
                    row.minutes_before,
                    row.absolute_trigger_at,
                ),
            )

        cur.execute("DELETE FROM calendar_notes WHERE event_id = %s AND note_type = 'shared'", (event_id,))
        shared_text = str(shared_note or "").strip()
        if shared_text:
            cur.execute(
                """
                INSERT INTO calendar_notes (
                    id, event_id, author_user_id, note_type, body
                )
                VALUES (arls_random_uuid(), %s, %s, 'shared', %s)
                """,
                (event_id, organizer_user_id, shared_text),
            )

        cur.execute(
            "DELETE FROM calendar_notes WHERE event_id = %s AND note_type = 'private' AND author_user_id = %s",
            (event_id, organizer_user_id),
        )
        private_text = str(private_memo or "").strip()
        if private_text:
            cur.execute(
                """
                INSERT INTO calendar_notes (
                    id, event_id, author_user_id, note_type, body
                )
                VALUES (arls_random_uuid(), %s, %s, 'private', %s)
                """,
                (event_id, organizer_user_id, private_text),
            )

        cur.execute("DELETE FROM calendar_action_items WHERE event_id = %s", (event_id,))
        for item in action_items:
            body = str(item or "").strip()
            if not body:
                continue
            cur.execute(
                """
                INSERT INTO calendar_action_items (
                    id, event_id, assignee_user_id, body, state
                )
                VALUES (arls_random_uuid(), %s, NULL, %s, 'open')
                """,
                (event_id, body),
            )


def _fetch_single_event(
    conn,
    *,
    tenant_id: str,
    event_id: str,
    user_id: str | None,
) -> CalendarEventOut:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, container_id, title, starts_at, ends_at, timezone, is_all_day,
                   recurrence_rule, availability_status, visibility, location,
                   conferencing_provider, conferencing_url, description, status
            FROM calendar_events
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, event_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    return _fetch_events(
        conn,
        tenant_id=tenant_id,
        container_id=str(row.get("container_id") or ""),
        range_start=row.get("starts_at"),
        range_end=row.get("ends_at") + timedelta(seconds=1),
        user_id=user_id,
    )[0]


def _resolve_calendar_container_access(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    container_id: str,
) -> CalendarContainerOut:
    containers = _build_calendar_container_lookup(conn, tenant_id=tenant_id, user=user)
    target = containers.get(str(container_id or "").strip())
    if not target:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "캘린더를 찾을 수 없습니다.")
    return target


def _ensure_container_membership(conn, *, container_id: str, user_id: str | None, employee_id: str | None, email: str | None, permission: str) -> None:
    if not user_id:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM calendar_members
            WHERE container_id = %s
              AND user_id = %s
            LIMIT 1
            """,
            (container_id, user_id),
        )
        row = cur.fetchone()
        if row:
            return
        cur.execute(
            """
            INSERT INTO calendar_members (
                id,
                container_id,
                user_id,
                employee_id,
                email,
                permission
            )
            VALUES (arls_random_uuid(), %s, %s, %s, %s, %s)
            """,
            (container_id, user_id, employee_id, email, permission),
        )


def _ensure_personal_container(conn, *, tenant_id: str, user: dict[str, Any]) -> str | None:
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM calendar_containers
            WHERE tenant_id = %s
              AND scope_type = 'personal'
              AND owner_user_id = %s
            LIMIT 1
            """,
            (tenant_id, user_id),
        )
        row = cur.fetchone()
        if row:
            container_id = str(row.get("id"))
        else:
            container_name = f"{str(user.get('full_name') or user.get('username') or '내 캘린더').strip() or '내 캘린더'}"
            cur.execute(
                """
                INSERT INTO calendar_containers (
                    id,
                    tenant_id,
                    owner_user_id,
                    owner_employee_id,
                    site_id,
                    scope_type,
                    name,
                    color,
                    provider,
                    is_default,
                    is_system
                )
                VALUES (
                    arls_random_uuid(),
                    %s,
                    %s,
                    %s,
                    %s,
                    'personal',
                    %s,
                    '#ff7a1a',
                    'arls',
                    TRUE,
                    FALSE
                )
                RETURNING id
                """,
                (
                    tenant_id,
                    user_id,
                    str(user.get("employee_id") or "").strip() or None,
                    str(user.get("site_id") or "").strip() or None,
                    container_name,
                ),
            )
            created = cur.fetchone() or {}
            container_id = str(created.get("id") or "")
    if container_id:
        _ensure_container_membership(
            conn,
            container_id=container_id,
            user_id=user_id,
            employee_id=str(user.get("employee_id") or "").strip() or None,
            email=str(user.get("email") or user.get("username") or "").strip() or None,
            permission="owner",
        )
    return container_id or None


def _ensure_team_container(conn, *, tenant_id: str, user: dict[str, Any]) -> str | None:
    site_id = str(user.get("site_id") or "").strip()
    if not site_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name
            FROM calendar_containers
            WHERE tenant_id = %s
              AND scope_type = 'team'
              AND site_id = %s
            LIMIT 1
            """,
            (tenant_id, site_id),
        )
        row = cur.fetchone()
        if row:
            container_id = str(row.get("id"))
        else:
            cur.execute(
                """
                SELECT site_name, site_code
                FROM sites
                WHERE tenant_id = %s
                  AND id = %s
                LIMIT 1
                """,
                (tenant_id, site_id),
            )
            site_row = cur.fetchone() or {}
            site_name = str(site_row.get("site_name") or "").strip()
            site_code = str(site_row.get("site_code") or "").strip().upper()
            name = site_name or f"현장 {site_code or site_id[:8]}"
            cur.execute(
                """
                INSERT INTO calendar_containers (
                    id,
                    tenant_id,
                    owner_user_id,
                    owner_employee_id,
                    site_id,
                    scope_type,
                    name,
                    color,
                    provider,
                    is_default,
                    is_system
                )
                VALUES (
                    arls_random_uuid(),
                    %s,
                    %s,
                    %s,
                    %s,
                    'team',
                    %s,
                    '#1c66ff',
                    'arls',
                    FALSE,
                    FALSE
                )
                RETURNING id
                """,
                (
                    tenant_id,
                    str(user.get("id") or "").strip() or None,
                    str(user.get("employee_id") or "").strip() or None,
                    site_id,
                    name,
                ),
            )
            created = cur.fetchone() or {}
            container_id = str(created.get("id") or "")
    if container_id:
        _ensure_container_membership(
            conn,
            container_id=container_id,
            user_id=str(user.get("id") or "").strip() or None,
            employee_id=str(user.get("employee_id") or "").strip() or None,
            email=str(user.get("email") or user.get("username") or "").strip() or None,
            permission="edit",
        )
    return container_id or None


def _ensure_shared_container(conn, *, tenant_id: str, user: dict[str, Any]) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM calendar_containers
            WHERE tenant_id = %s
              AND scope_type = 'shared'
              AND is_system = TRUE
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone()
        if row:
            container_id = str(row.get("id"))
        else:
            cur.execute(
                """
                INSERT INTO calendar_containers (
                    id,
                    tenant_id,
                    owner_user_id,
                    owner_employee_id,
                    site_id,
                    scope_type,
                    name,
                    color,
                    provider,
                    is_default,
                    is_system
                )
                VALUES (
                    arls_random_uuid(),
                    %s,
                    %s,
                    %s,
                    NULL,
                    'shared',
                    '공유 캘린더',
                    '#111827',
                    'arls',
                    FALSE,
                    TRUE
                )
                RETURNING id
                """,
                (
                    tenant_id,
                    str(user.get("id") or "").strip() or None,
                    str(user.get("employee_id") or "").strip() or None,
                ),
            )
            created = cur.fetchone() or {}
            container_id = str(created.get("id") or "")
    if container_id:
        _ensure_container_membership(
            conn,
            container_id=container_id,
            user_id=str(user.get("id") or "").strip() or None,
            employee_id=str(user.get("employee_id") or "").strip() or None,
            email=str(user.get("email") or user.get("username") or "").strip() or None,
            permission="owner",
        )
    return container_id or None


def _fetch_workspace_containers(conn, *, tenant_id: str, user: dict[str, Any]) -> list[CalendarContainerOut]:
    user_id = str(user.get("id") or "").strip() or None
    site_id = str(user.get("site_id") or "").strip() or None
    has_site_scope = bool(site_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT
                   c.id,
                   c.scope_type,
                   c.name,
                   c.color,
                   c.provider,
                   c.is_default,
                   c.is_system,
                   CASE
                     WHEN c.scope_type = 'shared' THEN 0
                     WHEN c.scope_type = 'team' THEN 1
                     ELSE 2
                   END AS scope_sort,
                   COALESCE(s.site_name, '') AS site_name,
                   COALESCE(u.full_name, '') AS owner_name,
                   COALESCE(m.permission,
                     CASE
                       WHEN c.owner_user_id = %s THEN 'owner'
                       WHEN c.scope_type = 'shared' THEN 'view_only'
                       WHEN c.scope_type = 'team' THEN 'edit'
                       ELSE 'view_only'
                     END
                   ) AS permission
            FROM calendar_containers c
            LEFT JOIN calendar_members m
              ON m.container_id = c.id
             AND m.user_id = %s
            LEFT JOIN sites s ON s.id = c.site_id
            LEFT JOIN arls_users u ON u.id = c.owner_user_id
            WHERE c.tenant_id = %s
              AND c.is_active = TRUE
              AND (
                c.owner_user_id = %s
                OR c.scope_type = 'shared'
                OR (%s AND c.scope_type = 'team' AND c.site_id = %s)
                OR m.user_id = %s
              )
            ORDER BY
              scope_sort,
              c.is_default DESC,
              c.name ASC
            """,
            (user_id, user_id, tenant_id, user_id, has_site_scope, site_id, user_id),
        )
        rows = cur.fetchall() or []
    containers: list[CalendarContainerOut] = []
    for row in rows:
        payload = dict(row)
        scope_type = str(payload.get("scope_type") or "").strip().lower()
        permission = _normalize_calendar_permission(payload.get("permission"))
        owner_label = _calendar_scope_owner_label(scope_type)
        if scope_type == "team":
            owner_label = str(payload.get("site_name") or owner_label).strip() or owner_label
        elif scope_type == "personal":
            owner_label = str(payload.get("owner_name") or owner_label).strip() or owner_label
        containers.append(
            CalendarContainerOut(
                id=payload.get("id"),
                scope_type=scope_type,
                name=str(payload.get("name") or "캘린더").strip() or "캘린더",
                color=str(payload.get("color") or "#ff7a1a").strip() or "#ff7a1a",
                provider=str(payload.get("provider") or "arls").strip() or "arls",
                permission=permission,
                is_default=bool(payload.get("is_default")),
                is_system=bool(payload.get("is_system")),
                badge_label=_calendar_scope_badge(scope_type),
                owner_label=owner_label,
            )
        )
    return containers


def _fetch_booking_links(conn, *, tenant_id: str, user: dict[str, Any]) -> list[CalendarBookingLinkOut]:
    if not can_manage_calendar_booking_links(user.get("role")):
        return []
    user_id = str(user.get("id") or "").strip() or None
    site_id = str(user.get("site_id") or "").strip() or None
    params: list[Any] = [tenant_id]
    filters = ["tenant_id = %s"]
    if _resolve_calendar_audience(user) == "hq":
        pass
    elif user_id:
        filters.append("(owner_user_id = %s OR EXISTS (SELECT 1 FROM calendar_containers cc WHERE cc.id = container_id AND cc.site_id = %s))")
        params.extend([user_id, site_id])
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT bl.id,
                   bl.container_id,
                   bl.slug,
                   bl.title,
                   bl.description,
                   bl.approval_required,
                   bl.approval_policy,
                   bl.assignment_mode,
                   bl.is_public,
                   bl.booking_window_days,
                   bl.buffer_before_minutes,
                   bl.buffer_after_minutes,
                   bl.duration_minutes,
                   bl.availability_start_time,
                   bl.availability_end_time,
                   bl.expires_at,
                   bl.host_notes,
                   bl.intake_questions_json,
                   COALESCE(u.full_name, '') AS owner_label
            FROM calendar_booking_links bl
            LEFT JOIN arls_users u ON u.id = bl.owner_user_id
            WHERE {" AND ".join(filters)}
            ORDER BY bl.created_at DESC
            LIMIT 20
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    return [_build_booking_link_out(row) for row in rows]


def _format_booking_time_value(value: Any, fallback: str) -> str:
    if isinstance(value, dt_time):
        return value.strftime("%H:%M")
    text = str(value or "").strip()
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
        return text
    return fallback


def _normalize_booking_question_rows(raw_value: Any) -> list[CalendarBookingQuestionOut]:
    payload = raw_value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = []
    if not isinstance(payload, list):
        return []
    rows: list[CalendarBookingQuestionOut] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        key = str(item.get("key") or "").strip().lower()
        key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_") or f"question_{index + 1}"
        answer_type = str(item.get("answer_type") or "short_text").strip().lower()
        if answer_type not in {"short_text", "long_text", "select"}:
            answer_type = "short_text"
        options = item.get("options")
        normalized_options = []
        if isinstance(options, list):
            seen: set[str] = set()
            for option in options:
                option_text = str(option or "").strip()
                if not option_text or option_text in seen:
                    continue
                seen.add(option_text)
                normalized_options.append(option_text)
        rows.append(
            CalendarBookingQuestionOut(
                key=key,
                label=label,
                answer_type=answer_type,
                required=bool(item.get("required", True)),
                options=normalized_options[:12],
            )
        )
    return rows[:8]


def _serialize_booking_question_rows(rows: list[Any]) -> str:
    normalized = [row.model_dump() if hasattr(row, "model_dump") else dict(row or {}) for row in (rows or [])]
    return json.dumps(normalized, ensure_ascii=False)


def _normalize_calendar_custom_field_rows(raw_value: Any) -> list[CalendarCustomFieldRowOut]:
    payload = raw_value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = []
    if not isinstance(payload, list):
        return []
    rows: list[CalendarCustomFieldRowOut] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label and not value:
            continue
        key = str(item.get("key") or "").strip().lower()
        key = re.sub(r"[^a-z0-9_]+", "_", key).strip("_") or f"field_{index + 1}"
        field_type = str(item.get("field_type") or "text").strip().lower()
        if field_type not in {"text", "number", "select"}:
            field_type = "text"
        rows.append(
            CalendarCustomFieldRowOut(
                key=key,
                label=label or f"필드 {index + 1}",
                value=value,
                field_type=field_type,
            )
        )
    return rows[:12]


def _serialize_calendar_custom_field_rows(rows: list[Any]) -> str:
    normalized = [row.model_dump() if hasattr(row, "model_dump") else dict(row or {}) for row in (rows or [])]
    return json.dumps(normalized, ensure_ascii=False)


def _build_booking_link_out(row: Any) -> CalendarBookingLinkOut:
    payload = dict(row or {})
    approval_policy = str(payload.get("approval_policy") or "").strip().lower() or ("manual" if payload.get("approval_required") else "instant")
    assignment_mode = str(payload.get("assignment_mode") or "single_host").strip().lower() or "single_host"
    return CalendarBookingLinkOut(
        id=payload.get("id"),
        container_id=payload.get("container_id"),
        slug=str(payload.get("slug") or "").strip(),
        title=str(payload.get("title") or "예약 링크").strip() or "예약 링크",
        description=str(payload.get("description") or "").strip() or None,
        approval_required=approval_policy == "manual",
        approval_policy=approval_policy,
        assignment_mode=assignment_mode,
        is_public=bool(payload.get("is_public", True)),
        booking_window_days=max(1, int(payload.get("booking_window_days") or 14)),
        buffer_before_minutes=max(0, int(payload.get("buffer_before_minutes") or 0)),
        buffer_after_minutes=max(0, int(payload.get("buffer_after_minutes") or 0)),
        duration_minutes=max(15, int(payload.get("duration_minutes") or 30)),
        availability_start_time=_format_booking_time_value(payload.get("availability_start_time"), "09:00"),
        availability_end_time=_format_booking_time_value(payload.get("availability_end_time"), "18:00"),
        expires_at=payload.get("expires_at"),
        host_notes=str(payload.get("host_notes") or "").strip() or None,
        intake_questions=_normalize_booking_question_rows(payload.get("intake_questions_json") or payload.get("intake_questions")),
        owner_label=str(payload.get("owner_label") or "").strip() or None,
    )


def _build_booking_link_filters(*, tenant_id: str, user: dict[str, Any], include_id: str | None = None) -> tuple[list[str], list[Any]]:
    user_id = str(user.get("id") or "").strip() or None
    site_id = str(user.get("site_id") or "").strip() or None
    params: list[Any] = [tenant_id]
    filters = ["bl.tenant_id = %s"]
    if include_id:
        filters.append("bl.id = %s")
        params.append(include_id)
    if _resolve_calendar_audience(user) == "hq":
        return filters, params
    if not user_id:
        filters.append("1 = 0")
        return filters, params
    filters.append(
        """
        (
          bl.owner_user_id = %s
          OR EXISTS (
            SELECT 1
            FROM calendar_containers cc
            WHERE cc.id = bl.container_id
              AND cc.site_id = %s
          )
        )
        """
    )
    params.extend([user_id, site_id])
    return filters, params


def _fetch_booking_link_for_manager(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    booking_link_id: str,
) -> CalendarBookingLinkOut | None:
    filters, params = _build_booking_link_filters(tenant_id=tenant_id, user=user, include_id=booking_link_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT bl.id,
                   bl.container_id,
                   bl.slug,
                   bl.title,
                   bl.description,
                   bl.approval_required,
                   bl.approval_policy,
                   bl.assignment_mode,
                   bl.is_public,
                   bl.booking_window_days,
                   bl.buffer_before_minutes,
                   bl.buffer_after_minutes,
                   bl.duration_minutes,
                   bl.availability_start_time,
                   bl.availability_end_time,
                   bl.expires_at,
                   bl.host_notes,
                   bl.intake_questions_json,
                   COALESCE(u.full_name, '') AS owner_label
            FROM calendar_booking_links bl
            LEFT JOIN arls_users u ON u.id = bl.owner_user_id
            WHERE {" AND ".join(filters)}
            LIMIT 1
            """,
            tuple(params),
        )
        row = cur.fetchone() or None
    return _build_booking_link_out(row) if row else None


def _generate_booking_slug(conn, *, title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", str(title or "").strip().lower()).strip("-") or "booking"
    for _ in range(6):
        candidate = f"{base}-{uuid4().hex[:6]}"
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM calendar_booking_links WHERE slug = %s LIMIT 1",
                (candidate,),
            )
            if not cur.fetchone():
                return candidate
    return f"booking-{uuid4().hex[:8]}"


def _parse_booking_time_text(value: str, fallback: str) -> dt_time:
    text = str(value or fallback).strip() or fallback
    try:
        return dt_time.fromisoformat(text)
    except ValueError:
        return dt_time.fromisoformat(fallback)


def _serialize_calendar_sync_selected_calendars(rows: list[str] | None) -> str:
    normalized = [str(item or "").strip() for item in (rows or []) if str(item or "").strip()]
    return json.dumps(normalized[:16], ensure_ascii=False)


def _normalize_calendar_sync_selected_calendars(raw_value: Any) -> list[str]:
    payload = raw_value
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = []
    if not isinstance(payload, list):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for item in payload:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        rows.append(normalized)
    return rows[:16]


def _build_calendar_sync_connection_out(row: Any) -> CalendarSyncConnectionOut:
    payload = dict(row or {})
    return CalendarSyncConnectionOut(
        id=payload.get("id"),
        provider=str(payload.get("provider") or "google").strip().lower() or "google",
        account_email=str(payload.get("account_email") or "").strip() or None,
        account_label=str(payload.get("account_label") or "").strip() or None,
        access_scope=str(payload.get("access_scope") or "read_write").strip().lower() or "read_write",
        sync_state=str(payload.get("sync_state") or "pending").strip().lower() or "pending",
        last_synced_at=payload.get("last_synced_at"),
        default_container_id=payload.get("default_container_id"),
        default_container_label=str(payload.get("default_container_label") or "").strip() or None,
        selected_external_calendars=_normalize_calendar_sync_selected_calendars(payload.get("selected_external_calendars_json") or payload.get("selected_external_calendars")),
        last_sync_error=str(payload.get("last_sync_error") or "").strip() or None,
    )


def _fetch_public_booking_link_row(conn, *, slug: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT bl.id,
                   bl.tenant_id,
                   bl.owner_user_id,
                   bl.container_id,
                   bl.slug,
                   bl.title,
                   bl.description,
                   bl.approval_required,
                   bl.approval_policy,
                   bl.assignment_mode,
                   bl.is_public,
                   bl.booking_window_days,
                   bl.buffer_before_minutes,
                   bl.buffer_after_minutes,
                   bl.duration_minutes,
                   bl.availability_start_time,
                   bl.availability_end_time,
                   bl.expires_at,
                   bl.host_notes,
                   bl.intake_questions_json,
                   COALESCE(u.full_name, '') AS owner_label
            FROM calendar_booking_links bl
            LEFT JOIN arls_users u ON u.id = bl.owner_user_id
            WHERE bl.slug = %s
              AND bl.is_public = TRUE
            LIMIT 1
            """,
            (slug,),
        )
        return cur.fetchone() or None


def _fetch_container_busy_ranges(
    conn,
    *,
    container_id: str,
    range_start: datetime,
    range_end: datetime,
) -> list[tuple[datetime, datetime]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT starts_at, ends_at
            FROM calendar_events
            WHERE container_id = %s
              AND status <> 'cancelled'
              AND starts_at < %s
              AND ends_at > %s
            ORDER BY starts_at ASC
            """,
            (container_id, range_end, range_start),
        )
        rows = cur.fetchall() or []
    return [
        (row.get("starts_at"), row.get("ends_at"))
        for row in rows
        if row.get("starts_at") and row.get("ends_at")
    ]


def _ranges_overlap(left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start < right_end and left_end > right_start


def _build_public_booking_slots(conn, row: dict[str, Any]) -> list[CalendarBookingSlotOut]:
    now = datetime.now(KST)
    expires_at = row.get("expires_at")
    booking_window_days = max(1, int(row.get("booking_window_days") or 14))
    start_date = now.date()
    end_date = start_date + timedelta(days=booking_window_days - 1)
    if expires_at:
        end_date = min(end_date, expires_at.astimezone(KST).date())
    if end_date < start_date:
        return []
    start_time = _parse_booking_time_text(_format_booking_time_value(row.get("availability_start_time"), "09:00"), "09:00")
    end_time = _parse_booking_time_text(_format_booking_time_value(row.get("availability_end_time"), "18:00"), "18:00")
    duration_minutes = max(15, int(row.get("duration_minutes") or 30))
    step_minutes = 30 if duration_minutes >= 30 else duration_minutes
    range_start = datetime.combine(start_date, dt_time.min, tzinfo=KST)
    range_end = datetime.combine(end_date + timedelta(days=1), dt_time.min, tzinfo=KST)
    busy_ranges = _fetch_container_busy_ranges(
        conn,
        container_id=str(row.get("container_id") or ""),
        range_start=range_start,
        range_end=range_end,
    )
    slots: list[CalendarBookingSlotOut] = []
    current_date = start_date
    while current_date <= end_date and len(slots) < 24:
        slot_cursor = datetime.combine(current_date, start_time, tzinfo=KST)
        slot_end_boundary = datetime.combine(current_date, end_time, tzinfo=KST)
        while slot_cursor + timedelta(minutes=duration_minutes) <= slot_end_boundary:
            proposed_start = slot_cursor
            proposed_end = slot_cursor + timedelta(minutes=duration_minutes)
            if proposed_start >= now:
                blocked = any(
                    _ranges_overlap(proposed_start, proposed_end, busy_start, busy_end)
                    for busy_start, busy_end in busy_ranges
                )
                if not blocked:
                    slots.append(
                        CalendarBookingSlotOut(
                            starts_at=proposed_start,
                            ends_at=proposed_end,
                            label=f"{proposed_start.strftime('%m.%d')} {proposed_start.strftime('%H:%M')} - {proposed_end.strftime('%H:%M')}",
                            date_label=proposed_start.strftime("%Y년 %m월 %d일"),
                        )
                    )
            slot_cursor += timedelta(minutes=step_minutes)
        current_date += timedelta(days=1)
    return slots


def _fetch_sync_connections(conn, *, tenant_id: str, user: dict[str, Any]) -> list[CalendarSyncConnectionOut]:
    if not can_manage_calendar_sync(user.get("role")):
        return []
    user_id = str(user.get("id") or "").strip() or None
    params: list[Any] = [tenant_id]
    filters = ["tenant_id = %s"]
    if _resolve_calendar_audience(user) != "hq" and user_id:
        filters.append("owner_user_id = %s")
        params.append(user_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT sc.id,
                   sc.provider,
                   sc.access_scope,
                   sc.account_email,
                   sc.account_label,
                   sc.sync_state,
                   sc.last_synced_at,
                   sc.default_container_id,
                   sc.selected_external_calendars_json,
                   sc.last_sync_error,
                   COALESCE(cc.name, '') AS default_container_label
            FROM calendar_sync_connections sc
            LEFT JOIN calendar_containers cc ON cc.id = sc.default_container_id
            WHERE {" AND ".join(filters)}
            ORDER BY sc.created_at DESC
            LIMIT 20
            """,
            tuple(params),
        )
        rows = cur.fetchall() or []
    return [_build_calendar_sync_connection_out(row) for row in rows]


def _fetch_sync_connection_for_manager(
    conn,
    *,
    tenant_id: str,
    user: dict[str, Any],
    sync_connection_id: str,
) -> CalendarSyncConnectionOut | None:
    if not can_manage_calendar_sync(user.get("role")):
        return None
    user_id = str(user.get("id") or "").strip() or None
    params: list[Any] = [tenant_id, sync_connection_id]
    filters = ["sc.tenant_id = %s", "sc.id = %s"]
    if _resolve_calendar_audience(user) != "hq" and user_id:
        filters.append("sc.owner_user_id = %s")
        params.append(user_id)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT sc.id,
                   sc.provider,
                   sc.access_scope,
                   sc.account_email,
                   sc.account_label,
                   sc.sync_state,
                   sc.last_synced_at,
                   sc.default_container_id,
                   sc.selected_external_calendars_json,
                   sc.last_sync_error,
                   COALESCE(cc.name, '') AS default_container_label
            FROM calendar_sync_connections sc
            LEFT JOIN calendar_containers cc ON cc.id = sc.default_container_id
            WHERE {" AND ".join(filters)}
            LIMIT 1
            """,
            tuple(params),
        )
        row = cur.fetchone() or None
    return _build_calendar_sync_connection_out(row) if row else None


def _build_mini_month_days(anchor_date: dt_date, selected_date: dt_date) -> list[CalendarMiniMonthDayOut]:
    month_start = anchor_date.replace(day=1)
    cursor = month_start - timedelta(days=(month_start.weekday() + 1) % 7)
    today = _today_kst()
    rows: list[CalendarMiniMonthDayOut] = []
    for _ in range(42):
        rows.append(
            CalendarMiniMonthDayOut(
                date=cursor.isoformat(),
                day=cursor.day,
                in_month=cursor.month == anchor_date.month,
                is_today=cursor == today,
                is_selected=cursor == selected_date,
            )
        )
        cursor += timedelta(days=1)
    return rows


def _format_range_label(view: str, anchor_date: dt_date) -> str:
    if view == "month":
        return f"{anchor_date.year}년 {anchor_date.month}월"
    if view == "agenda":
        return f"{anchor_date.year}년 {anchor_date.month}월 {anchor_date.day}일 이후"
    if view == "booking-links":
        return "예약 링크"
    week_start = anchor_date - timedelta(days=anchor_date.weekday())
    return f"{week_start.year}년 {week_start.month}월 {week_start.day}일 주간"


def _build_templates() -> list[CalendarTemplateOut]:
    return [
        CalendarTemplateOut(
            code="one-on-one",
            label="1:1",
            description="짧은 개별 미팅을 빠르게 생성합니다.",
            duration_minutes=30,
            reminder_minutes=[10],
            conferencing_provider="Google Meet",
            visibility="private",
            recurrence_preset="none",
            title_template="1:1 미팅",
        ),
        CalendarTemplateOut(
            code="standup",
            label="스탠드업",
            description="팀 공유용 짧은 반복 미팅 템플릿입니다.",
            duration_minutes=15,
            reminder_minutes=[10],
            conferencing_provider="Google Meet",
            visibility="team",
            recurrence_preset="weekly",
            title_template="팀 스탠드업",
        ),
        CalendarTemplateOut(
            code="interview",
            label="인터뷰",
            description="면접용 참석자와 메모 구조를 미리 채웁니다.",
            duration_minutes=60,
            reminder_minutes=[30, 10],
            conferencing_provider="Teams",
            visibility="shared",
            recurrence_preset="none",
            title_template="인터뷰",
        ),
    ]


def _pick_selected_container_id(containers: list[CalendarContainerOut], audience: str) -> str | None:
    if not containers:
        return None
    if audience == "hq":
        shared = next((row for row in containers if row.scope_type == "shared"), None)
        if shared:
            return str(shared.id)
    if audience in {"supervisor", "vice"}:
        team = next((row for row in containers if row.scope_type == "team"), None)
        if team:
            return str(team.id)
    return str(containers[0].id)


@router.get("/workspace", response_model=CalendarWorkspaceOut)
def get_calendar_workspace(
    view: str = Query(default="week"),
    date: str | None = Query(default=None),
    container_id: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_view_calendar(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "캘린더를 볼 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    audience = _resolve_calendar_audience(user)
    anchor_date = _parse_anchor_date(date)
    selected_date = anchor_date
    normalized_view = str(view or "week").strip().lower()
    if normalized_view not in {"week", "month", "agenda", "booking-links"}:
        normalized_view = "week"

    _ensure_personal_container(conn, tenant_id=tenant_id, user=user)
    if audience == "hq":
        _ensure_shared_container(conn, tenant_id=tenant_id, user=user)
    if audience in {"supervisor", "vice"}:
        _ensure_team_container(conn, tenant_id=tenant_id, user=user)
    conn.commit()

    containers = _fetch_workspace_containers(conn, tenant_id=tenant_id, user=user)
    selected_container = _resolve_selected_container(
        conn,
        tenant_id=tenant_id,
        user=user,
        audience=audience,
        requested_container_id=container_id,
    )
    selected_container_id = str(selected_container.id) if selected_container else None
    range_start, range_end = _resolve_calendar_visible_range(normalized_view, anchor_date)
    events = (
        _fetch_events(
            conn,
            tenant_id=tenant_id,
            container_id=selected_container_id,
            range_start=range_start,
            range_end=range_end,
            user_id=_to_uuid_text(user.get("id")),
        )
        if selected_container_id and normalized_view != "booking-links"
        else []
    )
    selected_event = _pick_selected_event(
        events,
        selected_date=selected_date,
        requested_event_id=event_id,
    )
    return CalendarWorkspaceOut(
        audience=audience,
        view=normalized_view,
        date=anchor_date.isoformat(),
        anchor_date=anchor_date.isoformat(),
        selected_date=selected_date.isoformat(),
        range_label=_format_range_label(normalized_view, anchor_date),
        role_label=_role_label(user),
        scope_label=_site_scope_label(conn, user, tenant_id),
        capabilities=_build_calendar_capabilities(user),
        mini_month_days=_build_mini_month_days(anchor_date, selected_date),
        containers=containers,
        selected_container_id=selected_container_id,
        booking_links=_fetch_booking_links(conn, tenant_id=tenant_id, user=user),
        templates=_build_templates(),
        sync_connections=_fetch_sync_connections(conn, tenant_id=tenant_id, user=user),
        attendee_options=_fetch_attendee_options(conn, tenant_id=tenant_id, user=user, audience=audience),
        resources=_fetch_available_resources(conn, tenant_id=tenant_id, user=user, selected_container=selected_container),
        events=events,
        selected_event=selected_event,
    )


@router.post("/booking-links", response_model=CalendarBookingLinkOut)
def create_calendar_booking_link(
    payload: CalendarBookingLinkCreateIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_booking_links(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "예약 링크를 생성할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(payload.container_id),
    )
    if not _can_edit_calendar_container(container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 캘린더에서는 예약 링크를 만들 수 없습니다.")
    slug = _generate_booking_slug(conn, title=payload.title)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calendar_booking_links (
                id, tenant_id, owner_user_id, container_id, slug, title, description,
                is_public, approval_required, approval_policy, assignment_mode, booking_window_days, buffer_before_minutes,
                buffer_after_minutes, duration_minutes, availability_start_time,
                availability_end_time, expires_at, host_notes, intake_questions_json
            )
            VALUES (
                arls_random_uuid(), %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s::jsonb
            )
            RETURNING id
            """,
            (
                tenant_id,
                _to_uuid_text(user.get("id")),
                str(payload.container_id),
                slug,
                str(payload.title or "").strip(),
                str(payload.description or "").strip() or None,
                bool(payload.is_public),
                bool(payload.approval_policy == "manual"),
                str(payload.approval_policy or "instant"),
                str(payload.assignment_mode or "single_host"),
                int(payload.booking_window_days),
                int(payload.buffer_before_minutes),
                int(payload.buffer_after_minutes),
                int(payload.duration_minutes),
                str(payload.availability_start_time),
                str(payload.availability_end_time),
                payload.expires_at,
                str(payload.host_notes or "").strip() or None,
                _serialize_booking_question_rows(payload.intake_questions),
            ),
        )
        row = cur.fetchone() or {}
    conn.commit()
    return _fetch_booking_link_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        booking_link_id=str(row.get("id") or ""),
    )


@router.patch("/booking-links/{booking_link_id}", response_model=CalendarBookingLinkOut)
def update_calendar_booking_link(
    booking_link_id: str,
    payload: CalendarBookingLinkUpdateIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_booking_links(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "예약 링크를 수정할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    existing = _fetch_booking_link_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        booking_link_id=booking_link_id,
    )
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "예약 링크를 찾을 수 없습니다.")
    container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(payload.container_id),
    )
    if not _can_edit_calendar_container(container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 캘린더에서는 예약 링크를 수정할 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE calendar_booking_links
            SET container_id = %s,
                title = %s,
                description = %s,
                is_public = %s,
                approval_required = %s,
                approval_policy = %s,
                assignment_mode = %s,
                booking_window_days = %s,
                buffer_before_minutes = %s,
                buffer_after_minutes = %s,
                duration_minutes = %s,
                availability_start_time = %s,
                availability_end_time = %s,
                expires_at = %s,
                host_notes = %s,
                intake_questions_json = %s::jsonb,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                str(payload.container_id),
                str(payload.title or "").strip(),
                str(payload.description or "").strip() or None,
                bool(payload.is_public),
                bool(payload.approval_policy == "manual"),
                str(payload.approval_policy or "instant"),
                str(payload.assignment_mode or "single_host"),
                int(payload.booking_window_days),
                int(payload.buffer_before_minutes),
                int(payload.buffer_after_minutes),
                int(payload.duration_minutes),
                str(payload.availability_start_time),
                str(payload.availability_end_time),
                payload.expires_at,
                str(payload.host_notes or "").strip() or None,
                _serialize_booking_question_rows(payload.intake_questions),
                tenant_id,
                booking_link_id,
            ),
        )
    conn.commit()
    return _fetch_booking_link_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        booking_link_id=booking_link_id,
    )


@router.delete("/booking-links/{booking_link_id}")
def delete_calendar_booking_link(
    booking_link_id: str,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_booking_links(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "예약 링크를 삭제할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    existing = _fetch_booking_link_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        booking_link_id=booking_link_id,
    )
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "예약 링크를 찾을 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM calendar_booking_links
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, booking_link_id),
        )
    conn.commit()
    return {"deleted": True, "id": booking_link_id}


@router.post("/sync-connections", response_model=CalendarSyncConnectionOut)
def create_calendar_sync_connection(
    payload: CalendarSyncConnectionUpsertIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_sync(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "외부 연동을 생성할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    default_container_id = str(payload.default_container_id or "").strip() or None
    if default_container_id:
        container = _resolve_calendar_container_access(
            conn,
            tenant_id=tenant_id,
            user=user,
            container_id=default_container_id,
        )
        if not _can_edit_calendar_container(container.permission):
            _raise_calendar_error(status.HTTP_403_FORBIDDEN, "기본 캘린더로 사용할 수 없는 일정 범위입니다.")
    initial_sync_state = "connected" if (payload.account_email or payload.account_label) else "pending"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calendar_sync_connections (
                id,
                tenant_id,
                owner_user_id,
                provider,
                access_scope,
                account_email,
                account_label,
                sync_state,
                last_synced_at,
                default_container_id,
                selected_external_calendars_json,
                last_sync_error
            )
            VALUES (
                arls_random_uuid(),
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                NULL,
                %s,
                %s::jsonb,
                NULL
            )
            RETURNING id
            """,
            (
                tenant_id,
                _to_uuid_text(user.get("id")),
                str(payload.provider),
                str(payload.access_scope),
                str(payload.account_email or "").strip() or None,
                str(payload.account_label or "").strip() or None,
                initial_sync_state,
                default_container_id,
                _serialize_calendar_sync_selected_calendars(payload.selected_external_calendars),
            ),
        )
        row = cur.fetchone() or {}
    conn.commit()
    return _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=str(row.get("id") or ""),
    )


@router.patch("/sync-connections/{sync_connection_id}", response_model=CalendarSyncConnectionOut)
def update_calendar_sync_connection(
    sync_connection_id: str,
    payload: CalendarSyncConnectionUpsertIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_sync(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "외부 연동을 수정할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    existing = _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=sync_connection_id,
    )
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "외부 연동을 찾을 수 없습니다.")
    default_container_id = str(payload.default_container_id or "").strip() or None
    if default_container_id:
        container = _resolve_calendar_container_access(
            conn,
            tenant_id=tenant_id,
            user=user,
            container_id=default_container_id,
        )
        if not _can_edit_calendar_container(container.permission):
            _raise_calendar_error(status.HTTP_403_FORBIDDEN, "기본 캘린더로 사용할 수 없는 일정 범위입니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE calendar_sync_connections
            SET provider = %s,
                access_scope = %s,
                account_email = %s,
                account_label = %s,
                default_container_id = %s,
                selected_external_calendars_json = %s::jsonb,
                last_sync_error = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                str(payload.provider),
                str(payload.access_scope),
                str(payload.account_email or "").strip() or None,
                str(payload.account_label or "").strip() or None,
                default_container_id,
                _serialize_calendar_sync_selected_calendars(payload.selected_external_calendars),
                tenant_id,
                sync_connection_id,
            ),
        )
    conn.commit()
    return _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=sync_connection_id,
    )


@router.delete("/sync-connections/{sync_connection_id}")
def delete_calendar_sync_connection(
    sync_connection_id: str,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_sync(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "외부 연동을 삭제할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    existing = _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=sync_connection_id,
    )
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "외부 연동을 찾을 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM calendar_sync_connections
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, sync_connection_id),
        )
    conn.commit()
    return {"deleted": True, "id": sync_connection_id}


@router.post("/sync-connections/{sync_connection_id}/sync", response_model=CalendarSyncConnectionOut)
def run_calendar_sync_connection(
    sync_connection_id: str,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_manage_calendar_sync(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "외부 연동을 실행할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    existing = _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=sync_connection_id,
    )
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "외부 연동을 찾을 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE calendar_sync_connections
            SET sync_state = 'connected',
                last_synced_at = timezone('utc', now()),
                last_sync_error = NULL,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, sync_connection_id),
        )
    conn.commit()
    return _fetch_sync_connection_for_manager(
        conn,
        tenant_id=tenant_id,
        user=user,
        sync_connection_id=sync_connection_id,
    )


@router.get("/booking-links/{slug}/public", response_model=CalendarBookingLinkPublicOut)
def get_public_calendar_booking_link(
    slug: str,
    conn=Depends(get_db_conn),
):
    ensure_calendar_runtime_shape(conn)
    row = _fetch_public_booking_link_row(conn, slug=str(slug or "").strip())
    if not row:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "예약 링크를 찾을 수 없습니다.")
    if row.get("expires_at") and row.get("expires_at") < datetime.now(timezone.utc):
        _raise_calendar_error(status.HTTP_410_GONE, "만료된 예약 링크입니다.")
    booking_link = _build_booking_link_out(row)
    return CalendarBookingLinkPublicOut(
        slug=booking_link.slug,
        title=booking_link.title,
        description=booking_link.description,
        owner_label=booking_link.owner_label,
        approval_required=booking_link.approval_required,
        approval_policy=booking_link.approval_policy,
        assignment_mode=booking_link.assignment_mode,
        booking_window_days=booking_link.booking_window_days,
        buffer_before_minutes=booking_link.buffer_before_minutes,
        buffer_after_minutes=booking_link.buffer_after_minutes,
        duration_minutes=booking_link.duration_minutes,
        availability_start_time=booking_link.availability_start_time,
        availability_end_time=booking_link.availability_end_time,
        expires_at=booking_link.expires_at,
        intake_questions=booking_link.intake_questions,
        slots=_build_public_booking_slots(conn, row),
    )


@router.post("/booking-links/{slug}/book", response_model=CalendarPublicBookingSubmitOut)
def submit_public_calendar_booking(
    slug: str,
    payload: CalendarPublicBookingSubmitIn,
    conn=Depends(get_db_conn),
):
    ensure_calendar_runtime_shape(conn)
    row = _fetch_public_booking_link_row(conn, slug=str(slug or "").strip())
    if not row:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "예약 링크를 찾을 수 없습니다.")
    if row.get("expires_at") and row.get("expires_at") < datetime.now(timezone.utc):
        _raise_calendar_error(status.HTTP_410_GONE, "만료된 예약 링크입니다.")
    slots = _build_public_booking_slots(conn, row)
    requested_start = payload.starts_at.astimezone(KST)
    duration_minutes = max(15, int(row.get("duration_minutes") or 30))
    requested_end = requested_start + timedelta(minutes=duration_minutes)
    slot_allowed = any(
        slot.starts_at == requested_start and slot.ends_at == requested_end
        for slot in slots
    )
    if not slot_allowed:
        _raise_calendar_error(status.HTTP_409_CONFLICT, "선택한 시간에는 예약할 수 없습니다.")

    event_title = str(payload.title or row.get("title") or "예약 미팅").strip() or "예약 미팅"
    description_parts = [str(row.get("description") or "").strip()]
    if payload.note:
        description_parts.append(f"Guest note: {payload.note}")
    for key, value in (payload.answers or {}).items():
        question_key = str(key or "").strip()
        answer_text = str(value or "").strip()
        if question_key and answer_text:
            description_parts.append(f"{question_key}: {answer_text}")
    description = "\n".join(part for part in description_parts if part)
    approval_policy = str(row.get("approval_policy") or "").strip().lower() or ("manual" if row.get("approval_required") else "instant")
    event_status = "pending" if approval_policy == "manual" else "confirmed"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calendar_events (
                id, tenant_id, container_id, created_by_user_id, title, starts_at, ends_at,
                timezone, is_all_day, recurrence_rule, availability_status, visibility,
                location, conferencing_provider, conferencing_url, description, resource_id, status
            )
            VALUES (
                arls_random_uuid(), %s, %s, %s, %s, %s, %s,
                'Asia/Seoul', FALSE, NULL, 'busy', 'shared',
                NULL, NULL, NULL, %s, NULL, %s
            )
            RETURNING id
            """,
            (
                str(row.get("tenant_id") or ""),
                str(row.get("container_id") or ""),
                _to_uuid_text(row.get("owner_user_id")),
                event_title,
                requested_start,
                requested_end,
                description or None,
                event_status,
            ),
        )
        created = cur.fetchone() or {}
        created_event_id = str(created.get("id") or "")
        cur.execute(
            """
            INSERT INTO calendar_attendees (
                id, event_id, user_id, employee_id, email, display_name, is_required, is_organizer, rsvp_status
            )
            VALUES (
                arls_random_uuid(), %s, %s, NULL, %s, %s, TRUE, TRUE, %s
            )
            """,
            (
                created_event_id,
                _to_uuid_text(row.get("owner_user_id")),
                str(payload.guest_email or "").strip(),
                str(payload.guest_name or "").strip(),
                "needs_action" if event_status == "pending" else "accepted",
            ),
        )
        cur.execute(
            """
            INSERT INTO calendar_attendees (
                id, event_id, user_id, employee_id, email, display_name, is_required, is_organizer, rsvp_status
            )
            VALUES (
                arls_random_uuid(), %s, NULL, NULL, %s, %s, TRUE, FALSE, 'accepted'
            )
            """,
            (
                created_event_id,
                str(payload.guest_email or "").strip(),
                str(payload.guest_name or "").strip(),
            ),
        )
    conn.commit()
    return CalendarPublicBookingSubmitOut(
        event_id=created_event_id,
        status=event_status,
        starts_at=requested_start,
        ends_at=requested_end,
        approval_required=approval_policy == "manual",
        approval_policy=approval_policy,
    )


@router.get("/availability", response_model=CalendarAvailabilityOut)
def get_calendar_availability(
    date: str = Query(...),
    starts_at: datetime | None = Query(default=None),
    ends_at: datetime | None = Query(default=None),
    attendee_user_ids: list[str] = Query(default=[]),
    attendee_employee_ids: list[str] = Query(default=[]),
    attendee_emails: list[str] = Query(default=[]),
    resource_id: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_view_calendar(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "캘린더를 볼 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)

    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    anchor_date = _parse_anchor_date(date)
    range_start = starts_at or datetime.combine(anchor_date, datetime.min.time(), tzinfo=KST).replace(hour=9, minute=0)
    range_end = ends_at or (range_start + timedelta(hours=8))

    attendee_lookup = {
        "user": {str(option.user_id): option for option in _fetch_attendee_options(conn, tenant_id=tenant_id, user=user, audience=_resolve_calendar_audience(user)) if option.user_id},
        "employee": {str(option.employee_id): option for option in _fetch_attendee_options(conn, tenant_id=tenant_id, user=user, audience=_resolve_calendar_audience(user)) if option.employee_id},
    }

    lanes: list[CalendarAvailabilityLaneOut] = []
    for user_id in attendee_user_ids:
        key = _to_uuid_text(user_id)
        if not key:
            continue
        option = attendee_lookup["user"].get(key)
        slots = [
            CalendarBusySlotOut(
                starts_at=row.get("starts_at"),
                ends_at=row.get("ends_at"),
                title=str(row.get("title") or "").strip() or None,
                status=str(row.get("status") or "busy").strip() or "busy",
            )
            for row in _fetch_busy_rows_for_lane(
                conn,
                tenant_id=tenant_id,
                range_start=range_start,
                range_end=range_end,
                lane_type="user",
                lane_value=key,
                exclude_event_id=event_id,
            )
        ]
        lanes.append(
            CalendarAvailabilityLaneOut(
                lane_key=key,
                lane_label=str(option.display_name if option else "참석자").strip() or "참석자",
                lane_type="attendee",
                slots=slots,
            )
        )

    for employee_id in attendee_employee_ids:
        key = _to_uuid_text(employee_id)
        if not key or any(lane.lane_key == key for lane in lanes):
            continue
        option = attendee_lookup["employee"].get(key)
        slots = [
            CalendarBusySlotOut(
                starts_at=row.get("starts_at"),
                ends_at=row.get("ends_at"),
                title=str(row.get("title") or "").strip() or None,
                status=str(row.get("status") or "busy").strip() or "busy",
            )
            for row in _fetch_busy_rows_for_lane(
                conn,
                tenant_id=tenant_id,
                range_start=range_start,
                range_end=range_end,
                lane_type="employee",
                lane_value=key,
                exclude_event_id=event_id,
            )
        ]
        lanes.append(
            CalendarAvailabilityLaneOut(
                lane_key=key,
                lane_label=str(option.display_name if option else "참석자").strip() or "참석자",
                lane_type="attendee",
                slots=slots,
            )
        )

    for email in attendee_emails:
        key = str(email or "").strip().lower()
        if not key:
            continue
        slots = [
            CalendarBusySlotOut(
                starts_at=row.get("starts_at"),
                ends_at=row.get("ends_at"),
                title=str(row.get("title") or "").strip() or None,
                status=str(row.get("status") or "busy").strip() or "busy",
            )
            for row in _fetch_busy_rows_for_lane(
                conn,
                tenant_id=tenant_id,
                range_start=range_start,
                range_end=range_end,
                lane_type="email",
                lane_value=key,
                exclude_event_id=event_id,
            )
        ]
        lanes.append(
            CalendarAvailabilityLaneOut(
                lane_key=key,
                lane_label=key,
                lane_type="attendee",
                slots=slots,
            )
        )

    resource_key = _to_uuid_text(resource_id)
    if resource_key:
        resources = {str(item.id): item for item in _fetch_available_resources(conn, tenant_id=tenant_id, user=user, selected_container=None)}
        resource = resources.get(resource_key)
        slots = [
            CalendarBusySlotOut(
                starts_at=row.get("starts_at"),
                ends_at=row.get("ends_at"),
                title=str(row.get("title") or "").strip() or None,
                status=str(row.get("status") or "busy").strip() or "busy",
            )
            for row in _fetch_busy_rows_for_lane(
                conn,
                tenant_id=tenant_id,
                range_start=range_start,
                range_end=range_end,
                lane_type="resource",
                lane_value=resource_key,
                exclude_event_id=event_id,
            )
        ]
        lanes.append(
            CalendarAvailabilityLaneOut(
                lane_key=resource_key,
                lane_label=str(resource.resource_name if resource else "회의실").strip() or "회의실",
                lane_type="resource",
                slots=slots,
            )
        )

    duration_minutes = max(15, int((range_end - range_start).total_seconds() // 60) or 30)
    return CalendarAvailabilityOut(
        timezone="Asia/Seoul",
        working_hours_label="09:00-18:00",
        range_start=range_start,
        range_end=range_end,
        lanes=lanes,
        suggested_slots=_build_suggested_slots(anchor_date=anchor_date, duration_minutes=duration_minutes, lanes=lanes),
    )


@router.post("/events", response_model=CalendarEventOut)
def create_calendar_event(
    payload: CalendarEventUpsertIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_create_calendar_event(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "일정을 생성할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    _validate_calendar_event_payload(payload)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(payload.container_id),
    )
    if not _can_edit_calendar_container(container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 캘린더에는 일정을 추가할 수 없습니다.")
    _validate_calendar_schedule_guards(
        conn,
        tenant_id=tenant_id,
        user=user,
        payload=payload,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calendar_events (
                id, tenant_id, container_id, created_by_user_id,
                title, starts_at, ends_at, timezone, is_all_day, recurrence_rule,
                availability_status, visibility, location, conferencing_provider,
                conferencing_url, description, custom_fields_json, resource_id, status
            )
            VALUES (
                arls_random_uuid(), %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s::jsonb, %s, 'confirmed'
            )
            RETURNING id
            """,
            (
                tenant_id,
                str(payload.container_id),
                _to_uuid_text(user.get("id")),
                str(payload.title or "").strip(),
                payload.starts_at,
                payload.ends_at,
                str(payload.timezone or "Asia/Seoul").strip() or "Asia/Seoul",
                bool(payload.is_all_day),
                str(payload.recurrence_rule or "").strip() or None,
                str(payload.availability_status or "busy").strip() or "busy",
                str(payload.visibility or "private").strip() or "private",
                str(payload.location or "").strip() or None,
                str(payload.conferencing_provider or "").strip() or None,
                str(payload.conferencing_url or "").strip() or None,
                str(payload.description or "").strip() or None,
                _serialize_calendar_custom_field_rows(payload.custom_fields),
                _to_uuid_text(payload.resource_id),
            ),
        )
        row = cur.fetchone() or {}
        created_event_id = str(row.get("id") or "").strip()
    _upsert_calendar_event_relations(
        conn,
        event_id=created_event_id,
        user=user,
        attendees=payload.attendees,
        reminders=payload.reminders,
        shared_note=payload.shared_note,
        private_memo=payload.private_memo,
        action_items=payload.action_items,
    )
    conn.commit()
    return _fetch_single_event(
        conn,
        tenant_id=tenant_id,
        event_id=created_event_id,
        user_id=_to_uuid_text(user.get("id")),
    )


@router.patch("/events/{event_id}", response_model=CalendarEventOut)
def update_calendar_event(
    event_id: str,
    payload: CalendarEventUpsertIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_create_calendar_event(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "일정을 수정할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    _validate_calendar_event_payload(payload)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT container_id
            FROM calendar_events
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, event_id),
        )
        existing = cur.fetchone() or {}
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    current_container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(existing.get("container_id") or ""),
    )
    target_container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(payload.container_id),
    )
    if not _can_edit_calendar_container(current_container.permission) or not _can_edit_calendar_container(target_container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 일정을 수정할 수 없습니다.")
    _validate_calendar_schedule_guards(
        conn,
        tenant_id=tenant_id,
        user=user,
        payload=payload,
        exclude_event_id=event_id,
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE calendar_events
            SET container_id = %s,
                title = %s,
                starts_at = %s,
                ends_at = %s,
                timezone = %s,
                is_all_day = %s,
                recurrence_rule = %s,
                availability_status = %s,
                visibility = %s,
                location = %s,
                conferencing_provider = %s,
                conferencing_url = %s,
                description = %s,
                custom_fields_json = %s::jsonb,
                resource_id = %s,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND id = %s
            """,
            (
                str(payload.container_id),
                str(payload.title or "").strip(),
                payload.starts_at,
                payload.ends_at,
                str(payload.timezone or "Asia/Seoul").strip() or "Asia/Seoul",
                bool(payload.is_all_day),
                str(payload.recurrence_rule or "").strip() or None,
                str(payload.availability_status or "busy").strip() or "busy",
                str(payload.visibility or "private").strip() or "private",
                str(payload.location or "").strip() or None,
                str(payload.conferencing_provider or "").strip() or None,
                str(payload.conferencing_url or "").strip() or None,
                str(payload.description or "").strip() or None,
                _serialize_calendar_custom_field_rows(payload.custom_fields),
                _to_uuid_text(payload.resource_id),
                tenant_id,
                event_id,
            ),
        )
    _upsert_calendar_event_relations(
        conn,
        event_id=event_id,
        user=user,
        attendees=payload.attendees,
        reminders=payload.reminders,
        shared_note=payload.shared_note,
        private_memo=payload.private_memo,
        action_items=payload.action_items,
    )
    conn.commit()
    return _fetch_single_event(
        conn,
        tenant_id=tenant_id,
        event_id=event_id,
        user_id=_to_uuid_text(user.get("id")),
    )


@router.delete("/events/{event_id}")
def delete_calendar_event(
    event_id: str,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_create_calendar_event(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "일정을 삭제할 수 있는 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT container_id
            FROM calendar_events
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, event_id),
        )
        existing = cur.fetchone() or {}
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(existing.get("container_id") or ""),
    )
    if not _can_edit_calendar_container(container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 일정을 삭제할 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM calendar_events
            WHERE tenant_id = %s
              AND id = %s
            """,
            (tenant_id, event_id),
        )
    conn.commit()
    return {"deleted": True, "id": event_id}


@router.post("/events/{event_id}/comments", response_model=CalendarEventOut)
def create_calendar_event_comment(
    event_id: str,
    payload: CalendarCommentIn,
    tenant_code: str | None = Query(default=None),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    if not can_create_calendar_event(user.get("role")):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "일정 코멘트를 작성할 권한이 없습니다.")
    ensure_calendar_runtime_shape(conn)
    scoped_tenant = resolve_scoped_tenant(
        conn,
        user,
        query_tenant_code=tenant_code,
        require_dev_context=False,
    )
    tenant_id = str(scoped_tenant.get("id") or "").strip()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT container_id
            FROM calendar_events
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, event_id),
        )
        existing = cur.fetchone() or {}
    if not existing:
        _raise_calendar_error(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    container = _resolve_calendar_container_access(
        conn,
        tenant_id=tenant_id,
        user=user,
        container_id=str(existing.get("container_id") or ""),
    )
    if not _can_edit_calendar_container(container.permission):
        _raise_calendar_error(status.HTTP_403_FORBIDDEN, "이 일정에 코멘트를 작성할 수 없습니다.")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO calendar_comments (
                id, tenant_id, event_id, author_user_id, body, is_internal
            )
            VALUES (
                arls_random_uuid(), %s, %s, %s, %s, %s
            )
            """,
            (
                tenant_id,
                event_id,
                _to_uuid_text(user.get("id")),
                str(payload.body or "").strip(),
                bool(payload.is_internal),
            ),
        )
    conn.commit()
    return _fetch_single_event(
        conn,
        tenant_id=tenant_id,
        event_id=event_id,
        user_id=_to_uuid_text(user.get("id")),
    )
