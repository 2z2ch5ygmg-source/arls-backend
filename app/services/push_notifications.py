from __future__ import annotations

import logging
import threading
from typing import Any, Iterable

import requests

from ..config import settings
from ..utils.permissions import (
    ROLE_HQ_ADMIN,
    ROLE_VICE_SUPERVISOR,
    normalize_user_role,
)

logger = logging.getLogger(__name__)

FCM_SEND_URL = "https://fcm.googleapis.com/fcm/send"
_push_schema_ready = False
_push_schema_lock = threading.Lock()


def ensure_push_schema(conn) -> None:
    global _push_schema_ready
    if _push_schema_ready:
        return
    with _push_schema_lock:
        if _push_schema_ready:
            return
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS push_devices (
                    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    user_id uuid NOT NULL REFERENCES arls_users(id) ON DELETE CASCADE,
                    platform text NOT NULL DEFAULT 'web',
                    device_token text NOT NULL,
                    device_id text,
                    is_active boolean NOT NULL DEFAULT TRUE,
                    created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
                    updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
                    last_seen_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
                    UNIQUE (tenant_id, user_id, device_token)
                );
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_push_devices_tenant_active
                    ON push_devices (tenant_id, is_active, updated_at DESC);
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_push_devices_user_active
                    ON push_devices (user_id, is_active, updated_at DESC);
                """
            )
        _push_schema_ready = True


def normalize_push_platform(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"ios", "iphone", "ipad"}:
        return "ios"
    if normalized in {"android"}:
        return "android"
    return "web"


def register_push_device(
    conn,
    *,
    tenant_id: str,
    user_id: str,
    device_token: str,
    platform: str,
    device_id: str | None = None,
) -> dict[str, Any]:
    ensure_push_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO push_devices (
                tenant_id,
                user_id,
                platform,
                device_token,
                device_id,
                is_active,
                created_at,
                updated_at,
                last_seen_at
            )
            VALUES (
                %s, %s, %s, %s, NULLIF(%s, ''), TRUE,
                timezone('utc', now()),
                timezone('utc', now()),
                timezone('utc', now())
            )
            ON CONFLICT (tenant_id, user_id, device_token)
            DO UPDATE SET
                platform = EXCLUDED.platform,
                device_id = EXCLUDED.device_id,
                is_active = TRUE,
                updated_at = timezone('utc', now()),
                last_seen_at = timezone('utc', now())
            RETURNING id, tenant_id, user_id, platform, device_id, last_seen_at
            """,
            (
                tenant_id,
                user_id,
                normalize_push_platform(platform),
                str(device_token).strip(),
                str(device_id or "").strip(),
            ),
        )
        row = cur.fetchone()
    return dict(row) if row else {}


def _build_attendance_message(
    *,
    site_name: str,
    employee_name: str,
    event_type: str,
    auto_checkout: bool = False,
) -> str:
    safe_site_name = str(site_name or "-").strip() or "-"
    safe_employee_name = str(employee_name or "-").strip() or "-"
    if auto_checkout:
        return f"[{safe_site_name}] {safe_employee_name} 퇴근 자동처리(미퇴근)"
    if event_type == "check_out":
        return f"[{safe_site_name}] {safe_employee_name} 퇴근"
    return f"[{safe_site_name}] {safe_employee_name} 출근"


def _eligible_attendance_recipient(role_value: str | None) -> bool:
    normalized = normalize_user_role(role_value)
    return normalized in {ROLE_HQ_ADMIN, ROLE_VICE_SUPERVISOR}


def _fetch_push_targets_for_attendance(
    conn,
    *,
    tenant_id: str,
    site_id: str | None = None,
) -> list[dict[str, Any]]:
    ensure_push_schema(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                pd.device_token,
                pd.platform,
                pd.user_id,
                au.role,
                COALESCE(au.site_id, e.site_id) AS scoped_site_id
            FROM push_devices pd
            JOIN arls_users au ON au.id = pd.user_id
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE pd.tenant_id = %s
              AND pd.is_active = TRUE
              AND au.tenant_id = %s
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
            """,
            (tenant_id, tenant_id),
        )
        rows = cur.fetchall()

    targets: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    site_id_value = str(site_id or "").strip()
    for row in rows or []:
        if not _eligible_attendance_recipient(row.get("role")):
            continue
        scoped_site_id = str(row.get("scoped_site_id") or "").strip()
        if site_id_value and scoped_site_id and scoped_site_id != site_id_value:
            continue
        token = str(row.get("device_token") or "").strip()
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        targets.append(dict(row))
    return targets


def _fetch_push_targets_for_users(
    conn,
    *,
    tenant_id: str,
    user_ids: Iterable[str],
) -> list[dict[str, Any]]:
    ensure_push_schema(conn)
    normalized_user_ids = sorted({str(user_id or "").strip() for user_id in user_ids if str(user_id or "").strip()})
    if not normalized_user_ids:
        return []
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pd.device_token,
                   pd.platform,
                   pd.user_id
            FROM push_devices pd
            JOIN arls_users au ON au.id = pd.user_id
            WHERE pd.tenant_id = %s
              AND pd.is_active = TRUE
              AND au.tenant_id = %s
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND pd.user_id::text = ANY(%s)
            ORDER BY pd.updated_at DESC
            """,
            (tenant_id, tenant_id, normalized_user_ids),
        )
        rows = cur.fetchall() or []

    targets: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for row in rows:
        token = str(row.get("device_token") or "").strip()
        if not token or token in seen_tokens:
            continue
        seen_tokens.add(token)
        targets.append(dict(row))
    return targets


def _send_fcm_message(*, token: str, title: str, body: str, data: dict[str, Any]) -> bool:
    fcm_key = str(settings.push_fcm_server_key or "").strip()
    if not fcm_key:
        return False
    payload = {
        "to": token,
        "priority": "high",
        "notification": {"title": title, "body": body},
        "data": data,
    }
    response = requests.post(
        FCM_SEND_URL,
        headers={
            "Authorization": f"key={fcm_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=float(settings.push_request_timeout_seconds),
    )
    if response.status_code >= 400:
        logger.warning(
            "fcm send failed status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
        return False
    return True


def send_attendance_push_notification(
    conn,
    *,
    tenant_id: str,
    site_id: str | None,
    site_name: str,
    employee_id: str,
    employee_name: str,
    event_type: str,
    event_at_iso: str,
    auto_checkout: bool = False,
) -> int:
    if not settings.push_notifications_enabled:
        return 0
    if auto_checkout and not settings.push_attendance_auto_checkout_enabled:
        return 0

    targets = _fetch_push_targets_for_attendance(conn, tenant_id=tenant_id, site_id=site_id)
    if not targets:
        return 0

    body = _build_attendance_message(
        site_name=site_name,
        employee_name=employee_name,
        event_type=event_type,
        auto_checkout=auto_checkout,
    )
    title = str(settings.push_attendance_title or "출퇴근 알림").strip() or "출퇴근 알림"
    payload_data = {
        "type": "ATTENDANCE_CHECK_OUT_AUTO" if auto_checkout else (
            "ATTENDANCE_CHECK_OUT" if event_type == "check_out" else "ATTENDANCE_CHECK_IN"
        ),
        "tenant_id": str(tenant_id),
        "site_id": str(site_id or ""),
        "employee_id": str(employee_id),
        "event_at": str(event_at_iso or ""),
        "auto_checkout": "1" if auto_checkout else "0",
    }

    sent_count = 0
    for target in targets:
        token = str(target.get("device_token") or "").strip()
        if not token:
            continue
        try:
            if _send_fcm_message(token=token, title=title, body=body, data=payload_data):
                sent_count += 1
        except Exception as exc:
            logger.warning("push send failed token=%s err=%s", token[:20], exc)
    return sent_count


def send_push_notification_to_users(
    conn,
    *,
    tenant_id: str,
    user_ids: Iterable[str],
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict[str, int]:
    normalized_title = str(title or "").strip() or "알림"
    normalized_body = str(body or "").strip() or normalized_title
    if not settings.push_notifications_enabled:
        return {
            "target_count": 0,
            "sent_count": 0,
            "failed_count": 0,
        }

    targets = _fetch_push_targets_for_users(conn, tenant_id=tenant_id, user_ids=user_ids)
    if not targets:
        return {
            "target_count": 0,
            "sent_count": 0,
            "failed_count": 0,
        }

    payload_data = dict(data or {})
    sent_count = 0
    failed_count = 0
    for target in targets:
        token = str(target.get("device_token") or "").strip()
        if not token:
            continue
        try:
            if _send_fcm_message(token=token, title=normalized_title, body=normalized_body, data=payload_data):
                sent_count += 1
            else:
                failed_count += 1
        except Exception as exc:
            failed_count += 1
            logger.warning("generic push send failed token=%s err=%s", token[:20], exc)
    return {
        "target_count": len(targets),
        "sent_count": sent_count,
        "failed_count": failed_count,
    }
