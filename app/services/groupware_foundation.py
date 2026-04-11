from __future__ import annotations

import json
import uuid
from typing import Any

from ..config import settings
from ..integration_center.audit_log import AuditLogService

GROUPWARE_FOUNDATION_TABLE_GROUPS: dict[str, list[str]] = {
    "attachments": ["groupware_attachment_objects"],
    "approvals": [
        "approval_forms",
        "approval_form_versions",
        "approval_line_rules",
        "approval_documents",
        "approval_steps",
        "approval_actions",
        "approval_comments",
        "approval_attachments",
        "approval_watchers",
        "approval_notifications",
    ],
    "leave": [
        "leave_policies",
        "leave_grants",
        "leave_ledger",
        "leave_balance_snapshots",
        "leave_blackout_rules",
        "holiday_calendar",
    ],
    "certificates": [
        "certificate_types",
        "certificate_templates",
        "certificate_requests",
        "certificate_issue_jobs",
    ],
    "mail": [
        "mail_accounts",
        "mail_sender_profiles",
        "mail_templates",
        "outbound_mail_jobs",
        "mail_delivery_events",
    ],
}

GROUPWARE_COMPATIBILITY_ROUTES: list[dict[str, Any]] = [
    {
        "legacy_prefix": "/api/v1/leaves",
        "future_module": "approvals.leave",
        "future_tables": ["approval_documents", "leave_ledger"],
        "adapter_strategy": "legacy-router-writes-approval-document",
        "cutover_phase": 2,
        "notes": "휴가 요청은 기존 /leaves API를 유지한 채 approval_documents + leave_ledger로 전환됩니다.",
    },
    {
        "legacy_prefix": "/api/v1/attendance/requests",
        "future_module": "approvals.attendance",
        "future_tables": ["approval_documents"],
        "adapter_strategy": "legacy-router-writes-approval-document",
        "cutover_phase": 2,
        "notes": "출퇴근 예외/정정 요청은 기존 라우트를 유지하면서 approval_documents로 미러링됩니다.",
    },
    {
        "legacy_prefix": "/api/v1/hr/documents/employment-certificate/requests",
        "future_module": "certificates.requests",
        "future_tables": ["certificate_requests", "certificate_issue_jobs", "outbound_mail_jobs"],
        "adapter_strategy": "legacy-router-writes-certificate-request",
        "cutover_phase": 4,
        "notes": "재직증명서 요청은 certificate_requests와 메일 잡 큐를 통해 점진 전환됩니다.",
    },
]

GROUPWARE_SERVICE_BOUNDARIES: list[dict[str, Any]] = [
    {
        "service": "core-api",
        "runtime": "fastapi",
        "responsibilities": [
            "auth",
            "tenant-and-org",
            "approvals",
            "leave-ledger",
            "certificates",
            "mail-orchestration",
            "audit-log",
        ],
        "status": "active",
    },
]

GROUPWARE_ROLLOUT_PHASES: list[dict[str, Any]] = [
    {
        "phase": 1,
        "name": "foundation-and-compatibility",
        "outcomes": [
            "foundational schema",
            "shared services",
            "status visibility",
            "legacy cutover plan",
        ],
    },
    {
        "phase": 2,
        "name": "approval-engine",
        "outcomes": ["approval documents", "steps", "legacy approval adapters"],
    },
    {
        "phase": 3,
        "name": "leave-ledger",
        "outcomes": ["leave policies", "ledger", "balance snapshots"],
    },
    {
        "phase": 4,
        "name": "certificates-and-mail",
        "outcomes": ["certificate requests", "mail accounts", "delivery jobs"],
    },
]

def _normalize_json_payload(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)

def _query_existing_tables(conn, table_names: list[str]) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            """,
            (table_names,),
        )
        rows = cur.fetchall() or []
    return {str((row or {}).get("table_name") or "").strip() for row in rows}

class GroupwareAuditService:
    """Shared write interface for future groupware modules."""

    def __init__(self, conn):
        self.conn = conn
        self._delegate = AuditLogService(conn)

    def write_event(
        self,
        *,
        tenant_id: str | None,
        module_key: str,
        action_type: str,
        actor_user_id: str | None = None,
        actor_role: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        payload = dict(detail or {})
        payload.setdefault("module_key", module_key)
        self._delegate.write(
            tenant_id=tenant_id,
            action_type=f"groupware.{module_key}.{action_type}",
            source="hr",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type=target_type or module_key,
            target_id=target_id,
            detail=payload,
        )

    @staticmethod
    def describe() -> dict[str, Any]:
        return {
            "interface": "GroupwareAuditService.write_event",
            "backed_by": ["integration_audit_logs", "audit_log"],
            "status": "active",
        }

class GroupwareNotificationDispatcher:
    """Shared notification write interface for approval/mail/certificate flows."""

    def __init__(self, conn):
        self.conn = conn

    def dispatch_in_app(
        self,
        *,
        tenant_id: str,
        user_id: str,
        message: str,
        category: str = "info",
        dedupe_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> str:
        notification_id = str(uuid.uuid4())
        normalized_message = str(message or "").strip() or "-"
        normalized_category = str(category or "info").strip() or "info"
        normalized_dedupe_key = str(dedupe_key or "").strip() or None
        normalized_payload = _normalize_json_payload(payload)
        with self.conn.cursor() as cur:
            if normalized_dedupe_key:
                cur.execute(
                    """
                    SELECT id
                    FROM in_app_notifications
                    WHERE tenant_id = %s
                      AND user_id = %s
                      AND dedupe_key = %s
                    LIMIT 1
                    """,
                    (tenant_id, user_id, normalized_dedupe_key),
                )
                existing = cur.fetchone() or {}
                existing_id = str(existing.get("id") or "").strip()
                if existing_id:
                    cur.execute(
                        """
                        UPDATE in_app_notifications
                        SET message = %s,
                            category = %s,
                            payload_json = %s::jsonb,
                            created_at = timezone('utc', now())
                        WHERE id = %s
                        """,
                        (
                            normalized_message,
                            normalized_category,
                            normalized_payload,
                            existing_id,
                        ),
                    )
                    return existing_id

            cur.execute(
                """
                INSERT INTO in_app_notifications (
                    id,
                    tenant_id,
                    user_id,
                    message,
                    category,
                    dedupe_key,
                    payload_json,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
                """,
                (
                    notification_id,
                    tenant_id,
                    user_id,
                    normalized_message,
                    normalized_category,
                    normalized_dedupe_key,
                    normalized_payload,
                ),
            )
        return notification_id

    @staticmethod
    def describe() -> dict[str, Any]:
        return {
            "interface": "GroupwareNotificationDispatcher.dispatch_in_app",
            "backed_by": ["in_app_notifications"],
            "status": "active",
        }

class GroupwareAttachmentStorage:
    """Storage abstraction for document and certificate attachments."""

    def __init__(self, conn=None):
        self.conn = conn

    def describe_backend(self) -> dict[str, Any]:
        backend = str(settings.attachment_storage_backend or "database").strip().lower() or "database"
        blob_container = str(settings.attachment_blob_container or "").strip()
        blob_base_url = str(settings.attachment_blob_base_url or "").strip()
        return {
            "backend": backend,
            "azure_blob_configured": bool(
                str(settings.attachment_blob_connection_string or "").strip() or blob_base_url
            ),
            "blob_container": blob_container or None,
            "blob_base_url": blob_base_url or None,
            "phase_1_mode": "metadata-and-abstraction",
        }

    def register_attachment_object(
        self,
        *,
        tenant_id: str,
        module_key: str,
        resource_type: str,
        resource_id: str | None,
        file_name: str,
        mime_type: str | None = None,
        byte_size: int | None = None,
        uploaded_by: str | None = None,
        sha256: str | None = None,
        storage_key: str | None = None,
        blob_url: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if self.conn is None:
            raise RuntimeError("A database connection is required to register attachment metadata.")
        attachment_id = str(uuid.uuid4())
        backend = str(settings.attachment_storage_backend or "database").strip().lower() or "database"
        normalized_name = str(file_name or "").strip()
        if not normalized_name:
            raise ValueError("file_name is required")

        file_ext = ""
        if "." in normalized_name:
            file_ext = f".{normalized_name.rsplit('.', 1)[-1].strip().lower()}"

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO groupware_attachment_objects (
                    id,
                    tenant_id,
                    module_key,
                    resource_type,
                    resource_id,
                    storage_backend,
                    storage_key,
                    blob_url,
                    file_name,
                    file_ext,
                    mime_type,
                    byte_size,
                    sha256,
                    metadata_json,
                    uploaded_by,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                    timezone('utc', now()),
                    timezone('utc', now())
                )
                """,
                (
                    attachment_id,
                    tenant_id,
                    module_key,
                    resource_type,
                    resource_id,
                    backend,
                    storage_key,
                    blob_url,
                    normalized_name,
                    file_ext or None,
                    mime_type,
                    max(int(byte_size or 0), 0),
                    sha256,
                    _normalize_json_payload(metadata),
                    uploaded_by,
                ),
            )
        return attachment_id

    @staticmethod
    def describe() -> dict[str, Any]:
        return {
            "interface": "GroupwareAttachmentStorage.register_attachment_object",
            "backed_by": ["groupware_attachment_objects"],
            "status": "active",
        }

def build_groupware_foundation_status(conn) -> dict[str, Any]:
    all_tables = sorted(
        {
            table_name
            for tables in GROUPWARE_FOUNDATION_TABLE_GROUPS.values()
            for table_name in tables
        }
    )
    existing_tables = _query_existing_tables(conn, all_tables)
    attachment_storage = GroupwareAttachmentStorage().describe_backend()

    group_status: dict[str, Any] = {}
    for group_key, table_names in GROUPWARE_FOUNDATION_TABLE_GROUPS.items():
        missing_tables = [table for table in table_names if table not in existing_tables]
        group_status[group_key] = {
            "tables": table_names,
            "missing_tables": missing_tables,
            "ready": not missing_tables,
        }

    return {
        "phase": 1,
        "track": "functional",
        "status": "foundation-ready" if all(item["ready"] for item in group_status.values()) else "partial",
        "shared_services": {
            "audit": GroupwareAuditService.describe(),
            "notifications": GroupwareNotificationDispatcher.describe(),
            "attachments": GroupwareAttachmentStorage.describe(),
        },
        "storage": {
            "attachments": attachment_storage,
        },
        "database": {
            "groups": group_status,
            "ready_group_count": sum(1 for item in group_status.values() if item["ready"]),
            "total_group_count": len(group_status),
        },
        "deployment_topology": {
            "core_api": {
                "runtime": "fastapi",
                "status": "active",
            },
        },
        "service_boundaries": GROUPWARE_SERVICE_BOUNDARIES,
        "rollout_phases": GROUPWARE_ROLLOUT_PHASES,
    }

def build_groupware_compatibility_payload(conn) -> dict[str, Any]:
    status = build_groupware_foundation_status(conn)
    return {
        "phase": 1,
        "legacy_compatibility_routes": GROUPWARE_COMPATIBILITY_ROUTES,
        "legacy_foundation": {
            "leave_requests_table": "leave_requests",
            "attendance_requests_table": "attendance_requests",
            "document_requests_table": "document_requests",
            "notification_table": "in_app_notifications",
            "audit_tables": ["integration_audit_logs", "audit_log"],
        },
        "shared_service_interfaces": status["shared_services"],
        "deployment_topology": status["deployment_topology"],
        "service_boundaries": status["service_boundaries"],
    }
