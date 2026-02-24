from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any


class EventIdempotencyStore:
    def __init__(self, conn):
        self.conn = conn

    def _safe_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=str)

    def _payload_digest(self, payload: dict[str, Any]) -> str:
        normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _extract_value(self, payload: dict[str, Any], *keys: str) -> Any | None:
        nested_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        nested_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
        nested_ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
        nested_template_fields = payload.get("template_fields") if isinstance(payload.get("template_fields"), dict) else {}
        sources = (payload, nested_metadata, nested_payload, nested_ticket, nested_template_fields)
        for key in keys:
            for source in sources:
                if key in source:
                    value = source.get(key)
                    if value not in (None, ""):
                        return value
        return None

    def _extract_site_reference(self, payload: dict[str, Any]) -> str | None:
        value = self._extract_value(payload, "site_id", "siteId", "site_code", "siteCode")
        if value in (None, ""):
            return None
        return str(value).strip() or None

    def _extract_ticket_id(self, payload: dict[str, Any]) -> int | None:
        value = self._extract_value(payload, "ticket_id", "ticketId", "soc_ticket_id", "socTicketId", "id")
        if value in (None, ""):
            return None
        try:
            return int(str(value).strip())
        except Exception:
            return None

    def _extract_occurred_at(self, payload: dict[str, Any]) -> datetime | None:
        value = self._extract_value(payload, "occurred_at", "occurredAt", "decision_at", "decisionAt", "approvedAt")
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except Exception:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def get(self, event_uid: str):
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, event_uid, event_type, tenant_code, status, received_at, processed_at, error_text, applied_changes
                FROM soc_event_ingests
                WHERE event_uid = %s
                LIMIT 1
                """,
                (event_uid,),
            )
            return cur.fetchone()

    def ingest_received(
        self,
        *,
        event_uid: str,
        tenant_code: str,
        event_type: str,
        payload: dict[str, Any],
        signature_valid: bool,
    ) -> tuple[bool, dict[str, Any] | None]:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO soc_event_ingests (
                    id, event_uid, tenant_id, tenant_code, source, event_type, idempotency_key,
                    status, error_text, payload, applied_changes, signature_valid, received_at
                )
                VALUES (
                    %s, %s, NULL, %s, 'soc', %s, %s,
                    'received', NULL, %s::jsonb, '{}'::jsonb, %s, timezone('utc', now())
                )
                ON CONFLICT (event_uid) DO NOTHING
                RETURNING id
                """,
                (
                    uuid.uuid4(),
                    event_uid,
                    tenant_code,
                    event_type,
                    event_uid,
                    self._safe_json(payload),
                    signature_valid,
                ),
            )
            inserted = cur.fetchone()
            if inserted:
                cur.execute(
                    """
                    INSERT INTO integration_event_log (
                        id, source, event_id, event_type, tenant_id, site_id, ticket_id,
                        occurred_at, payload_digest, status, error_message, created_at
                    )
                    VALUES (
                        %s, 'SOC', %s, %s, NULL, %s, %s,
                        %s, %s, 'FAIL', 'processing', timezone('utc', now())
                    )
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    (
                        uuid.uuid4(),
                        event_uid,
                        event_type,
                        self._extract_site_reference(payload),
                        self._extract_ticket_id(payload),
                        self._extract_occurred_at(payload),
                        self._payload_digest(payload),
                    ),
                )
                return False, None

        existing = self.get(event_uid)
        if existing and str(existing.get("status") or "").lower() == "processed":
            return True, existing

        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE soc_event_ingests
                SET status = 'received',
                    error_text = NULL,
                    payload = %s::jsonb,
                    applied_changes = '{}'::jsonb,
                    signature_valid = %s,
                    received_at = timezone('utc', now()),
                    processed_at = NULL
                WHERE event_uid = %s
                """,
                (
                    self._safe_json(payload),
                    signature_valid,
                    event_uid,
                ),
            )
            cur.execute(
                """
                UPDATE integration_event_log
                SET status = 'FAIL',
                    error_message = 'processing'
                WHERE event_id = %s
                """,
                (event_uid,),
            )
        return False, None

    def finalize(
        self,
        *,
        event_uid: str,
        tenant_id,
        tenant_code: str,
        status_text: str,
        error_text: str | None,
        applied_changes: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE soc_event_ingests
                SET tenant_id = %s,
                    tenant_code = %s,
                    status = %s,
                    error_text = %s,
                    applied_changes = %s::jsonb,
                    processed_at = timezone('utc', now())
                WHERE event_uid = %s
                """,
                (
                    tenant_id,
                    tenant_code,
                    status_text,
                    error_text,
                    self._safe_json(applied_changes or {}),
                    event_uid,
                ),
            )
            cur.execute(
                """
                UPDATE integration_event_log
                SET tenant_id = %s,
                    status = %s,
                    error_message = %s
                WHERE event_id = %s
                """,
                (
                    tenant_id,
                    "SUCCESS" if str(status_text).lower() == "processed" else "FAIL",
                    error_text,
                    event_uid,
                ),
            )
        return self.get(event_uid)
