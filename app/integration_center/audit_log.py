from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _serialize_detail(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_serialize_detail(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_detail(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_detail(item) for key, item in value.items()}
    return value


def _sanitize_detail(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if any(token in lowered for token in ("password", "passwd", "pwd", "token", "secret", "authorization", "credential")):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = _sanitize_detail(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_detail(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_detail(item) for item in value]
    if isinstance(value, str) and len(value) > 1000:
        return f"{value[:1000]}...(truncated)"
    return _serialize_detail(value)


def _resolve_actor_type(*, source: str, actor_user_id, actor_role: str | None) -> str:
    normalized_source = str(source or "").strip().lower()
    normalized_role = str(actor_role or "").strip().lower()
    if normalized_source == "soc" or normalized_role in {"soc", "soc_system"}:
        return "SOC"
    if actor_user_id:
        return "HR_USER"
    return "SYSTEM"


def _resolve_entity_type(*, target_type: str | None, action_type: str) -> str:
    combined = f"{target_type or ''} {action_type}".strip().lower()
    if any(key in combined for key in ("schedule", "shift")):
        return "SCHEDULE"
    if any(key in combined for key in ("attendance", "check_in", "check_out", "soc_event", "clock")):
        return "ATTENDANCE"
    if any(key in combined for key in ("overtime", "ot_", "overnight", "closing_ot")):
        return "OVERTIME"
    if "leave" in combined:
        return "LEAVE"
    return "REPORT"


class AuditLogService:
    def __init__(self, conn):
        self.conn = conn

    def write(
        self,
        *,
        tenant_id=None,
        action_type: str,
        source: str = "hr",
        actor_user_id=None,
        actor_role: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        sanitized = _sanitize_detail(detail or {})
        payload = json.dumps(_serialize_detail(sanitized), ensure_ascii=False, default=str)
        before_json_value = sanitized.get("before", {}) if isinstance(sanitized, dict) else {}
        after_json_value = (
            sanitized.get("after", sanitized)
            if isinstance(sanitized, dict)
            else sanitized
        )
        before_payload = json.dumps(_serialize_detail(before_json_value or {}), ensure_ascii=False, default=str)
        after_payload = json.dumps(_serialize_detail(after_json_value or {}), ensure_ascii=False, default=str)
        actor_type = _resolve_actor_type(source=source, actor_user_id=actor_user_id, actor_role=actor_role)
        actor_id = str(actor_user_id) if actor_user_id else (str(actor_role or source or "system"))
        entity_type = _resolve_entity_type(target_type=target_type, action_type=action_type)
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO integration_audit_logs (
                    id, tenant_id, action_type, source, actor_user_id, actor_role, target_type, target_id, detail, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
                """,
                (
                    uuid.uuid4(),
                    tenant_id,
                    action_type,
                    source,
                    actor_user_id,
                    actor_role,
                    target_type,
                    target_id,
                    payload,
                ),
            )
            cur.execute(
                """
                INSERT INTO audit_log (
                    id, tenant_id, actor_type, actor_id, action_type,
                    entity_type, entity_id, before_json, after_json, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, timezone('utc', now()))
                """,
                (
                    uuid.uuid4(),
                    tenant_id,
                    actor_type,
                    actor_id,
                    action_type,
                    entity_type,
                    target_id,
                    before_payload,
                    after_payload,
                ),
            )
