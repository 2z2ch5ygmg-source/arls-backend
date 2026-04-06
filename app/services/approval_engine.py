from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status

from .certificates_mail import queue_approval_notification_mail
from .groupware_foundation import GroupwareAuditService, GroupwareNotificationDispatcher
from .leave_ledger import sync_leave_request_ledger
from ..utils.permissions import is_super_admin, normalize_user_role, user_role_sql_variants

logger = logging.getLogger(__name__)

DOCUMENT_STATUS_DRAFT = "draft"
DOCUMENT_STATUS_SUBMITTED = "submitted"
DOCUMENT_STATUS_IN_REVIEW = "in_review"
DOCUMENT_STATUS_APPROVED = "approved"
DOCUMENT_STATUS_REJECTED = "rejected"
DOCUMENT_STATUS_RETURNED = "returned"
DOCUMENT_STATUS_CANCELLED = "cancelled"
DOCUMENT_STATUS_RECALLED = "recalled"

STEP_STATUS_QUEUED = "queued"
STEP_STATUS_PENDING = "pending"
STEP_STATUS_APPROVED = "approved"
STEP_STATUS_REJECTED = "rejected"
STEP_STATUS_RETURNED = "returned"
STEP_STATUS_SKIPPED = "skipped"
STEP_STATUS_CANCELLED = "cancelled"

ACTION_CREATE_DRAFT = "create_draft"
ACTION_SUBMIT = "submit"
ACTION_APPROVE = "approve"
ACTION_REJECT = "reject"
ACTION_RETURN = "return"
ACTION_CANCEL = "cancel"
ACTION_RECALL = "recall"
ACTION_COMMENT = "comment"

ALLOWED_DOCUMENT_STATUSES = {
    DOCUMENT_STATUS_DRAFT,
    DOCUMENT_STATUS_SUBMITTED,
    DOCUMENT_STATUS_IN_REVIEW,
    DOCUMENT_STATUS_APPROVED,
    DOCUMENT_STATUS_REJECTED,
    DOCUMENT_STATUS_RETURNED,
    DOCUMENT_STATUS_CANCELLED,
    DOCUMENT_STATUS_RECALLED,
}
ALLOWED_STEP_STATUSES = {
    STEP_STATUS_QUEUED,
    STEP_STATUS_PENDING,
    STEP_STATUS_APPROVED,
    STEP_STATUS_REJECTED,
    STEP_STATUS_RETURNED,
    STEP_STATUS_SKIPPED,
    STEP_STATUS_CANCELLED,
}
ALLOWED_ACTION_TYPES = {
    ACTION_CREATE_DRAFT,
    ACTION_SUBMIT,
    ACTION_APPROVE,
    ACTION_REJECT,
    ACTION_RETURN,
    ACTION_CANCEL,
    ACTION_RECALL,
    ACTION_COMMENT,
}

APPROVAL_FORM_DEFINITIONS: list[dict[str, Any]] = [
    {
        "form_key": "leave_request",
        "display_name": "휴가신청",
        "category": "leave",
        "schema_json": {
            "fields": ["leave_type", "half_day_slot", "start_at", "end_at", "reason", "attachment_names"]
        },
        "settings_json": {"legacy_source_type": "leave_request"},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "site_or_tenant"},
    },
    {
        "form_key": "attendance_correction",
        "display_name": "근태정정",
        "category": "attendance",
        "schema_json": {
            "fields": [
                "request_type",
                "reason_code",
                "reason_detail",
                "requested_at",
                "photo_names",
            ]
        },
        "settings_json": {"legacy_source_type": "attendance_request"},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "site_or_tenant"},
    },
    {
        "form_key": "employment_certificate",
        "display_name": "증명서발급",
        "category": "documents",
        "schema_json": {"fields": ["purpose_code", "purpose_text"]},
        "settings_json": {"legacy_source_type": "employment_certificate_request"},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "tenant"},
    },
    {
        "form_key": "certificate_request",
        "display_name": "증명서발급(공통)",
        "category": "documents",
        "schema_json": {
            "fields": [
                "certificate_type_key",
                "purpose_code",
                "purpose_text",
                "submit_to",
                "copy_count",
                "include_address",
                "include_phone",
            ]
        },
        "settings_json": {"legacy_source_type": "certificate_request"},
        "default_rules": (
            {"approver_role": "hq_admin", "scope_type": "site_or_tenant"},
            {"approver_role": "hq_admin", "scope_type": "tenant"},
        ),
    },
    {
        "form_key": "general_memo",
        "display_name": "일반품의",
        "category": "general",
        "schema_json": {"fields": ["title", "body", "attachments"]},
        "settings_json": {},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "tenant"},
    },
    {
        "form_key": "business_trip",
        "display_name": "출장신청",
        "category": "general",
        "schema_json": {"fields": ["title", "trip_start_at", "trip_end_at", "reason"]},
        "settings_json": {},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "tenant"},
    },
    {
        "form_key": "expense_resolution",
        "display_name": "지출결의",
        "category": "finance",
        "schema_json": {"fields": ["title", "amount", "currency", "reason"]},
        "settings_json": {},
        "default_rule": {"approver_role": "hq_admin", "scope_type": "tenant"},
    },
]

APPROVAL_FORM_BY_KEY = {item["form_key"]: item for item in APPROVAL_FORM_DEFINITIONS}


def _json_dumps(value: dict[str, Any] | list[Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _build_document_no() -> str:
    stamp = _utc_now().strftime("%Y%m%d%H%M%S")
    return f"APR-{stamp}-{str(uuid.uuid4())[:8].upper()}"


def _http_error(status_code: int, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": "APPROVAL_ENGINE_ERROR", "message": message},
    )


def _normalize_status_text(value: str, *, allowed: set[str], field_name: str) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in allowed:
        raise _http_error(status.HTTP_400_BAD_REQUEST, f"{field_name} 값이 올바르지 않습니다.")
    return normalized


def ensure_default_approval_forms(conn, *, tenant_id: str, actor_user_id: str | None = None) -> None:
    with conn.cursor() as cur:
        for form in APPROVAL_FORM_DEFINITIONS:
            cur.execute(
                """
                SELECT id
                FROM approval_forms
                WHERE tenant_id = %s
                  AND form_key = %s
                LIMIT 1
                """,
                (tenant_id, form["form_key"]),
            )
            form_row = cur.fetchone() or {}
            form_id = str(form_row.get("id") or "").strip()
            if form_id:
                cur.execute(
                    """
                    UPDATE approval_forms
                    SET display_name = %s,
                        category = %s,
                        status = 'active',
                        description = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        form["display_name"],
                        form["category"],
                        form["display_name"],
                        form_id,
                    ),
                )
            else:
                form_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO approval_forms (
                        id,
                        tenant_id,
                        form_key,
                        display_name,
                        category,
                        status,
                        description,
                        created_by,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active', %s, %s, timezone('utc', now()), timezone('utc', now()))
                    """,
                    (
                        form_id,
                        tenant_id,
                        form["form_key"],
                        form["display_name"],
                        form["category"],
                        form["display_name"],
                        actor_user_id,
                    ),
                )

            cur.execute(
                """
                SELECT id
                FROM approval_form_versions
                WHERE form_id = %s
                  AND version_no = 1
                LIMIT 1
                """,
                (form_id,),
            )
            version_row = cur.fetchone() or {}
            version_id = str(version_row.get("id") or "").strip()
            if version_id:
                cur.execute(
                    """
                    UPDATE approval_form_versions
                    SET schema_json = %s::jsonb,
                        settings_json = %s::jsonb,
                        is_active = TRUE
                    WHERE id = %s
                    """,
                    (
                        _json_dumps(form.get("schema_json")),
                        _json_dumps(form.get("settings_json")),
                        version_id,
                    ),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO approval_form_versions (
                        id,
                        tenant_id,
                        form_id,
                        version_no,
                        schema_json,
                        settings_json,
                        is_active,
                        created_by,
                        created_at
                    )
                    VALUES (%s, %s, %s, 1, %s::jsonb, %s::jsonb, TRUE, %s, timezone('utc', now()))
                    """,
                    (
                        str(uuid.uuid4()),
                        tenant_id,
                        form_id,
                        _json_dumps(form.get("schema_json")),
                        _json_dumps(form.get("settings_json")),
                        actor_user_id,
                    ),
                )


def ensure_default_approval_line_rules(conn, *, tenant_id: str, actor_user_id: str | None = None) -> None:
    with conn.cursor() as cur:
        for index, form in enumerate(APPROVAL_FORM_DEFINITIONS, start=1):
            configured_rules = form.get("default_rules")
            if configured_rules:
                rules = [dict(rule or {}) for rule in configured_rules]
            else:
                rules = [dict(form.get("default_rule") or {})]
            for rule_order, rule in enumerate(rules, start=1):
                cur.execute(
                    """
                    SELECT id
                    FROM approval_line_rules
                    WHERE tenant_id = %s
                      AND form_key = %s
                      AND rule_order = %s
                    LIMIT 1
                    """,
                    (tenant_id, form["form_key"], rule_order),
                )
                existing = cur.fetchone() or {}
                existing_id = str(existing.get("id") or "").strip()
                if existing_id:
                    cur.execute(
                        """
                        UPDATE approval_line_rules
                        SET rule_name = %s,
                            approver_role = %s,
                            scope_type = %s,
                            is_active = TRUE,
                            updated_at = timezone('utc', now())
                        WHERE id = %s
                        """,
                        (
                            f"{form['display_name']} 기본 결재선 {rule_order}",
                            rule.get("approver_role"),
                            rule.get("scope_type") or "tenant",
                            existing_id,
                        ),
                    )
                    continue
                cur.execute(
                    """
                    INSERT INTO approval_line_rules (
                        id,
                        tenant_id,
                        form_key,
                        rule_order,
                        rule_name,
                        approver_role,
                        approver_user_id,
                        scope_type,
                        site_id,
                        is_active,
                        conditions_json,
                        created_by,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, NULL, %s, NULL, TRUE, '{}'::jsonb, %s,
                        timezone('utc', now()),
                        timezone('utc', now())
                    )
                    """,
                    (
                        str(uuid.uuid4()),
                        tenant_id,
                        form["form_key"],
                        rule_order,
                        f"{form['display_name']} 기본 결재선 {rule_order}",
                        rule.get("approver_role"),
                        rule.get("scope_type") or "tenant",
                        actor_user_id,
                    ),
                )


def _fetch_form_bundle(conn, *, tenant_id: str, form_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id AS form_id,
                   f.form_key,
                   f.display_name,
                   f.category,
                   v.id AS form_version_id,
                   v.version_no,
                   v.schema_json,
                   v.settings_json
            FROM approval_forms f
            LEFT JOIN approval_form_versions v
              ON v.form_id = f.id
             AND v.is_active = TRUE
            WHERE f.tenant_id = %s
              AND f.form_key = %s
            LIMIT 1
            """,
            (tenant_id, form_key),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _resolve_approver_from_rule(
    conn,
    *,
    tenant_id: str,
    site_id: str | None,
    approver_user_id: str | None,
    approver_role: str | None,
    scope_type: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        if approver_user_id:
            cur.execute(
                """
                SELECT id, employee_id, site_id, username, full_name, role
                FROM arls_users
                WHERE tenant_id = %s
                  AND id = %s
                  AND is_active = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                LIMIT 1
                """,
                (tenant_id, approver_user_id),
            )
            row = cur.fetchone()
            return dict(row) if row else None

        if not approver_role:
            return None

        role_variants = list(user_role_sql_variants(approver_role))
        if not role_variants:
            return None

        if site_id and scope_type == "site_or_tenant":
            cur.execute(
                """
                SELECT id, employee_id, site_id, username, full_name, role
                FROM arls_users
                WHERE tenant_id = %s
                  AND is_active = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                  AND lower(role) = ANY(%s)
                  AND (site_id = %s OR site_id IS NULL)
                ORDER BY
                    CASE WHEN site_id = %s THEN 0 ELSE 1 END,
                    created_at ASC
                LIMIT 1
                """,
                (tenant_id, role_variants, site_id, site_id),
            )
        elif site_id and scope_type == "site":
            cur.execute(
                """
                SELECT id, employee_id, site_id, username, full_name, role
                FROM arls_users
                WHERE tenant_id = %s
                  AND is_active = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                  AND lower(role) = ANY(%s)
                  AND site_id = %s
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (tenant_id, role_variants, site_id),
            )
        else:
            cur.execute(
                """
                SELECT id, employee_id, site_id, username, full_name, role
                FROM arls_users
                WHERE tenant_id = %s
                  AND is_active = TRUE
                  AND COALESCE(is_deleted, FALSE) = FALSE
                  AND lower(role) = ANY(%s)
                ORDER BY
                    CASE WHEN site_id IS NULL THEN 0 ELSE 1 END,
                    created_at ASC
                LIMIT 1
                """,
                (tenant_id, role_variants),
            )
        row = cur.fetchone()
    return dict(row) if row else None


def _resolve_approval_rule_form_keys(
    *,
    form_key: str,
    payload: dict[str, Any] | None = None,
) -> list[str]:
    normalized_form_key = str(form_key or "").strip().lower()
    if not normalized_form_key:
        return []

    keys: list[str] = [normalized_form_key]
    if normalized_form_key == "certificate_request":
        document_type = str((payload or {}).get("document_type") or (payload or {}).get("certificate_type_key") or "").strip().lower()
        if document_type:
            keys.insert(0, f"{normalized_form_key}:{document_type}")
    return keys


def _resolve_auto_approval_steps(
    conn,
    *,
    tenant_id: str,
    form_key: str,
    site_id: str | None,
    payload: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for candidate_form_key in _resolve_approval_rule_form_keys(form_key=form_key, payload=payload):
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,
                       rule_order,
                       rule_name,
                       approver_role,
                       approver_user_id,
                       scope_type,
                       site_id,
                       conditions_json
                FROM approval_line_rules
                WHERE tenant_id = %s
                  AND form_key = %s
                  AND is_active = TRUE
                ORDER BY rule_order ASC, created_at ASC
                """,
                (tenant_id, candidate_form_key),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
        if rows:
            rules = rows
            break

    resolved_steps: list[dict[str, Any]] = []
    for rule in rules:
        rule_site_id = str(rule.get("site_id") or "").strip() or None
        approver = _resolve_approver_from_rule(
            conn,
            tenant_id=tenant_id,
            site_id=rule_site_id or site_id,
            approver_user_id=str(rule.get("approver_user_id") or "").strip() or None,
            approver_role=str(rule.get("approver_role") or "").strip() or None,
            scope_type=str(rule.get("scope_type") or "tenant").strip().lower(),
        )
        if not approver:
            continue
        resolved_steps.append(
            {
                "rule_name": str(rule.get("rule_name") or "").strip() or f"{form_key}-{rule.get('rule_order')}",
                "step_order": int(rule.get("rule_order") or len(resolved_steps) + 1),
                "approver_user_id": str(approver.get("id") or "").strip() or None,
                "approver_employee_id": str(approver.get("employee_id") or "").strip() or None,
                "meta_json": {
                    "scope_type": str(rule.get("scope_type") or "tenant"),
                    "approver_role": str(rule.get("approver_role") or "").strip() or None,
                    "resolved_username": approver.get("username"),
                    "resolved_full_name": approver.get("full_name"),
                },
            }
        )
    return resolved_steps


def _insert_document_action(
    conn,
    *,
    tenant_id: str,
    document_id: str,
    step_id: str | None,
    actor_user_id: str | None,
    action_type: str,
    comment_text: str | None = None,
    payload: dict[str, Any] | None = None,
) -> str:
    action_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO approval_actions (
                id,
                tenant_id,
                document_id,
                step_id,
                actor_user_id,
                action_type,
                comment_text,
                payload_json,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()))
            """,
            (
                action_id,
                tenant_id,
                document_id,
                step_id,
                actor_user_id,
                action_type,
                comment_text,
                _json_dumps(payload),
            ),
        )
    return action_id


def _insert_document_comment(
    conn,
    *,
    tenant_id: str,
    document_id: str,
    actor_user_id: str | None,
    body: str,
    visibility: str = "internal",
) -> str:
    comment_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO approval_comments (
                id,
                tenant_id,
                document_id,
                actor_user_id,
                body,
                visibility,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, timezone('utc', now()))
            """,
            (
                comment_id,
                tenant_id,
                document_id,
                actor_user_id,
                body,
                visibility,
            ),
        )
    return comment_id


def _insert_watchers(conn, *, tenant_id: str, document_id: str, watcher_user_ids: list[str] | None) -> None:
    if not watcher_user_ids:
        return
    with conn.cursor() as cur:
        for watcher_user_id in watcher_user_ids:
            normalized_id = str(watcher_user_id or "").strip()
            if not normalized_id:
                continue
            cur.execute(
                """
                SELECT id
                FROM approval_watchers
                WHERE document_id = %s
                  AND watcher_user_id = %s
                LIMIT 1
                """,
                (document_id, normalized_id),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO approval_watchers (
                    id,
                    tenant_id,
                    document_id,
                    watcher_user_id,
                    created_at
                )
                VALUES (%s, %s, %s, %s, timezone('utc', now()))
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    document_id,
                    normalized_id,
                ),
            )


def _run_noncritical_side_effect(conn, *, log_message: str, callback) -> None:
    savepoint_name = f"sp_{uuid.uuid4().hex[:12]}"
    try:
        with conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {savepoint_name}")
        try:
            callback()
        except Exception as exc:  # pragma: no cover - protects main transaction from optional side-effects
            with conn.cursor() as cur:
                cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
                cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
            logger.exception(log_message, exc_info=exc)
            return
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {savepoint_name}")
    except Exception as exc:  # pragma: no cover - if savepoint ops fail, keep request alive and log only
        logger.exception(log_message, exc_info=exc)


def _fetch_first_pending_step(conn, *, document_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   tenant_id,
                   document_id,
                   step_order,
                   status,
                   approver_user_id,
                   approver_employee_id
            FROM approval_steps
            WHERE document_id = %s
              AND status = %s
            ORDER BY step_order ASC
            LIMIT 1
            """,
            (document_id, STEP_STATUS_PENDING),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_next_queued_step(conn, *, document_id: str, after_step_order: int) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   tenant_id,
                   document_id,
                   step_order,
                   status,
                   approver_user_id,
                   approver_employee_id
            FROM approval_steps
            WHERE document_id = %s
              AND status = %s
              AND step_order > %s
            ORDER BY step_order ASC
            LIMIT 1
            """,
            (document_id, STEP_STATUS_QUEUED, after_step_order),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_document_row(conn, *, tenant_id: str, document_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id,
                   d.tenant_id,
                   d.form_id,
                   d.form_version_id,
                   d.company_id,
                   d.site_id,
                   d.employee_id,
                   d.requester_user_id,
                   d.document_no,
                   d.title,
                   d.status,
                   d.payload_json,
                   d.legacy_source_type,
                   d.legacy_source_id,
                   d.submitted_at,
                   d.completed_at,
                   d.cancelled_at,
                   d.created_at,
                   d.updated_at,
                   f.form_key,
                   f.display_name AS form_display_name,
                   f.category AS form_category,
                   requester.username AS requester_username,
                   requester.full_name AS requester_name
            FROM approval_documents d
            LEFT JOIN approval_forms f ON f.id = d.form_id
            LEFT JOIN arls_users requester ON requester.id = d.requester_user_id
            WHERE d.tenant_id = %s
              AND d.id = %s
            LIMIT 1
            """,
            (tenant_id, document_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _fetch_legacy_leave_row(conn, *, tenant_id: str, leave_request_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lr.id,
                   lr.tenant_id,
                   lr.employee_id,
                   e.employee_code,
                   e.full_name AS employee_name,
                   e.site_id,
                   lr.leave_type,
                   lr.half_day_slot,
                   lr.start_at,
                   lr.end_at,
                   lr.reason,
                   lr.attachment_names,
                   lr.status,
                   lr.requested_at,
                   lr.review_note,
                   lr.reviewed_by,
                   lr.reviewed_at,
                   lr.cancelled_at
            FROM leave_requests lr
            JOIN employees e ON e.id = lr.employee_id
            WHERE lr.tenant_id = %s
              AND lr.id = %s
            LIMIT 1
            """,
            (tenant_id, leave_request_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _sync_legacy_leave_request_from_approval(
    conn,
    *,
    document: dict[str, Any],
    actor_user_id: str,
    actor_role: str | None,
    action_type: str,
    comment_text: str | None = None,
) -> None:
    if str(document.get("legacy_source_type") or "").strip().lower() != "leave_request":
        return

    legacy_source_id = str(document.get("legacy_source_id") or "").strip()
    tenant_id = str(document.get("tenant_id") or "").strip()
    if not legacy_source_id or not tenant_id:
        return

    if action_type == ACTION_RETURN:
        raise _http_error(status.HTTP_409_CONFLICT, "휴가 요청은 return 상태를 지원하지 않습니다.")

    next_status = None
    if action_type == ACTION_APPROVE:
        next_status = "approved"
    elif action_type == ACTION_REJECT:
        next_status = "rejected"
    elif action_type in {ACTION_CANCEL, ACTION_RECALL}:
        next_status = "cancelled"

    if not next_status:
        return

    with conn.cursor() as cur:
        if next_status == "cancelled":
            cur.execute(
                """
                UPDATE leave_requests
                SET status = %s,
                    review_note = COALESCE(%s, review_note),
                    cancelled_at = timezone('utc', now()),
                    reviewed_by = COALESCE(reviewed_by, %s),
                    reviewed_at = COALESCE(reviewed_at, timezone('utc', now()))
                WHERE tenant_id = %s
                  AND id = %s
                """,
                (next_status, comment_text, actor_user_id, tenant_id, legacy_source_id),
            )
        else:
            cur.execute(
                """
                UPDATE leave_requests
                SET status = %s,
                    review_note = %s,
                    reviewed_by = %s,
                    reviewed_at = timezone('utc', now())
                WHERE tenant_id = %s
                  AND id = %s
                """,
                (next_status, comment_text, actor_user_id, tenant_id, legacy_source_id),
            )

    leave_row = _fetch_legacy_leave_row(conn, tenant_id=tenant_id, leave_request_id=legacy_source_id)
    if leave_row:
        sync_leave_request_ledger(
            conn,
            leave_row=leave_row,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )


def fetch_approval_document_detail(conn, *, tenant_id: str, document_id: str) -> dict[str, Any]:
    document = _fetch_document_row(conn, tenant_id=tenant_id, document_id=document_id)
    if not document:
        raise _http_error(status.HTTP_404_NOT_FOUND, "결재 문서를 찾을 수 없습니다.")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   step_order,
                   step_type,
                   status,
                   approver_user_id,
                   approver_employee_id,
                   delegated_from_user_id,
                   acted_at,
                   due_at,
                   meta_json
            FROM approval_steps
            WHERE document_id = %s
            ORDER BY step_order ASC, created_at ASC
            """,
            (document_id,),
        )
        steps = [dict(row) for row in (cur.fetchall() or [])]

        cur.execute(
            """
            SELECT id,
                   step_id,
                   actor_user_id,
                   action_type,
                   comment_text,
                   payload_json,
                   created_at
            FROM approval_actions
            WHERE document_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (document_id,),
        )
        actions = [dict(row) for row in (cur.fetchall() or [])]

        cur.execute(
            """
            SELECT id,
                   actor_user_id,
                   body,
                   visibility,
                   created_at
            FROM approval_comments
            WHERE document_id = %s
            ORDER BY created_at ASC, id ASC
            """,
            (document_id,),
        )
        comments = [dict(row) for row in (cur.fetchall() or [])]

        cur.execute(
            """
            SELECT id,
                   watcher_user_id,
                   watcher_employee_id,
                   created_at
            FROM approval_watchers
            WHERE document_id = %s
            ORDER BY created_at ASC
            """,
            (document_id,),
        )
        watchers = [dict(row) for row in (cur.fetchall() or [])]

        cur.execute(
            """
            SELECT aa.id,
                   aa.attachment_object_id,
                   ao.file_name,
                   ao.mime_type,
                   ao.byte_size,
                   ao.storage_backend,
                   ao.blob_url
            FROM approval_attachments aa
            JOIN groupware_attachment_objects ao
              ON ao.id = aa.attachment_object_id
            WHERE aa.document_id = %s
            ORDER BY aa.created_at ASC
            """,
            (document_id,),
        )
        attachments = [dict(row) for row in (cur.fetchall() or [])]

    document["steps"] = steps
    document["actions"] = actions
    document["comments"] = comments
    document["watchers"] = watchers
    document["attachments"] = attachments
    return document


def list_approval_forms(conn, *, tenant_id: str, actor_user_id: str | None = None) -> list[dict[str, Any]]:
    ensure_default_approval_forms(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    ensure_default_approval_line_rules(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT f.id,
                   f.form_key,
                   f.display_name,
                   f.category,
                   f.status,
                   v.id AS active_version_id,
                   v.version_no,
                   v.schema_json,
                   v.settings_json
            FROM approval_forms f
            LEFT JOIN approval_form_versions v
              ON v.form_id = f.id
             AND v.is_active = TRUE
            WHERE f.tenant_id = %s
            ORDER BY f.category ASC, f.display_name ASC
            """,
            (tenant_id,),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows


def create_approval_document(
    conn,
    *,
    tenant_id: str,
    form_key: str,
    title: str,
    requester_user_id: str | None,
    requester_role: str | None,
    employee_id: str | None = None,
    site_id: str | None = None,
    company_id: str | None = None,
    payload: dict[str, Any] | None = None,
    watcher_user_ids: list[str] | None = None,
    submit: bool = True,
    legacy_source_type: str | None = None,
    legacy_source_id: str | None = None,
    comment_text: str | None = None,
) -> dict[str, Any]:
    normalized_form_key = str(form_key or "").strip().lower()
    if normalized_form_key not in APPROVAL_FORM_BY_KEY:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "지원하지 않는 결재 양식입니다.")

    ensure_default_approval_forms(conn, tenant_id=tenant_id, actor_user_id=requester_user_id)
    ensure_default_approval_line_rules(conn, tenant_id=tenant_id, actor_user_id=requester_user_id)
    bundle = _fetch_form_bundle(conn, tenant_id=tenant_id, form_key=normalized_form_key)
    if not bundle:
        raise _http_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "결재 양식 초기화에 실패했습니다.")

    steps = _resolve_auto_approval_steps(
        conn,
        tenant_id=tenant_id,
        form_key=normalized_form_key,
        site_id=site_id,
        payload=payload,
    )

    document_id = str(uuid.uuid4())
    document_status = DOCUMENT_STATUS_DRAFT
    submitted_at: datetime | None = None
    if submit:
        document_status = DOCUMENT_STATUS_IN_REVIEW if steps else DOCUMENT_STATUS_SUBMITTED
        submitted_at = _utc_now()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO approval_documents (
                id,
                tenant_id,
                form_id,
                form_version_id,
                company_id,
                site_id,
                employee_id,
                requester_user_id,
                document_no,
                title,
                status,
                payload_json,
                legacy_source_type,
                legacy_source_id,
                submitted_at,
                completed_at,
                cancelled_at,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, NULL, NULL,
                timezone('utc', now()),
                timezone('utc', now())
            )
            """,
            (
                document_id,
                tenant_id,
                bundle.get("form_id"),
                bundle.get("form_version_id"),
                company_id,
                site_id,
                employee_id,
                requester_user_id,
                _build_document_no(),
                str(title or "").strip() or bundle.get("display_name") or normalized_form_key,
                document_status,
                _json_dumps(payload),
                legacy_source_type,
                legacy_source_id,
                submitted_at,
            ),
        )

        for idx, step in enumerate(steps):
            cur.execute(
                """
                INSERT INTO approval_steps (
                    id,
                    tenant_id,
                    document_id,
                    step_order,
                    step_type,
                    status,
                    approver_user_id,
                    approver_employee_id,
                    delegated_from_user_id,
                    acted_at,
                    due_at,
                    meta_json,
                    created_at
                )
                VALUES (
                    %s, %s, %s, %s, 'approver', %s, %s, %s, NULL, NULL, NULL, %s::jsonb,
                    timezone('utc', now())
                )
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    document_id,
                    step["step_order"],
                    STEP_STATUS_PENDING if submit and idx == 0 else STEP_STATUS_QUEUED,
                    step.get("approver_user_id"),
                    step.get("approver_employee_id"),
                    _json_dumps(step.get("meta_json")),
                ),
            )

    _insert_watchers(conn, tenant_id=tenant_id, document_id=document_id, watcher_user_ids=watcher_user_ids)

    if comment_text:
        _insert_document_comment(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            actor_user_id=requester_user_id,
            body=comment_text,
        )

    _insert_document_action(
        conn,
        tenant_id=tenant_id,
        document_id=document_id,
        step_id=None,
        actor_user_id=requester_user_id,
        action_type=ACTION_SUBMIT if submit else ACTION_CREATE_DRAFT,
        comment_text=comment_text,
        payload={"legacy_source_type": legacy_source_type, "legacy_source_id": legacy_source_id},
    )

    if submit:
        first_step = _fetch_first_pending_step(conn, document_id=document_id)
        if first_step and first_step.get("approver_user_id"):
            _run_noncritical_side_effect(
                conn,
                log_message=f"[APPROVAL][NOTIFY] failed to dispatch review request doc={document_id}",
                callback=lambda: GroupwareNotificationDispatcher(conn).dispatch_in_app(
                    tenant_id=tenant_id,
                    user_id=str(first_step["approver_user_id"]),
                    message=f"결재 요청이 도착했습니다: {title}",
                    category="approval",
                    dedupe_key=f"approval:doc:{document_id}:pending:{first_step['step_order']}",
                    payload={"document_id": document_id, "form_key": normalized_form_key},
                ),
            )
            _run_noncritical_side_effect(
                conn,
                log_message=f"[APPROVAL][MAIL] failed to queue review request doc={document_id}",
                callback=lambda: queue_approval_notification_mail(
                    conn,
                    tenant_id=tenant_id,
                    template_key="approval_review_requested",
                    document_id=document_id,
                    recipient_user_id=str(first_step["approver_user_id"]),
                    render_context={
                        "title": str(title or "").strip() or bundle.get("display_name") or normalized_form_key,
                        "form_display_name": bundle.get("display_name") or normalized_form_key,
                    },
                ),
            )
    _run_noncritical_side_effect(
        conn,
        log_message=f"[APPROVAL][AUDIT] failed to write document_created doc={document_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="approvals",
            action_type="document_created",
            actor_user_id=requester_user_id,
            actor_role=requester_role,
            target_type="approval_document",
            target_id=document_id,
            detail={
                "form_key": normalized_form_key,
                "document_status": document_status,
                "legacy_source_type": legacy_source_type,
                "legacy_source_id": legacy_source_id,
            },
        ),
    )

    return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=document_id)


def list_approval_documents(
    conn,
    *,
    tenant_id: str,
    current_user: dict,
    scope: str = "mine",
    limit: int = 100,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    normalized_scope = str(scope or "mine").strip().lower()
    allowed_scopes = {"mine", "review", "all"}
    if normalized_scope not in allowed_scopes:
        raise _http_error(status.HTTP_400_BAD_REQUEST, "scope 값이 올바르지 않습니다.")

    user_id = str(current_user.get("id") or "").strip()
    user_role = str(current_user.get("role") or "").strip()
    normalized_status = str(status_filter or "").strip().lower()

    clauses = ["d.tenant_id = %s"]
    params: list[Any] = [tenant_id]

    if normalized_scope == "mine":
        clauses.append("d.requester_user_id = %s")
        params.append(user_id)
    elif normalized_scope == "review":
        clauses.append("EXISTS (SELECT 1 FROM approval_steps s WHERE s.document_id = d.id AND s.approver_user_id = %s)")
        params.append(user_id)
    elif normalized_scope == "all" and not is_super_admin(user_role) and normalize_user_role(user_role) != "hq_admin":
        clauses.append("d.requester_user_id = %s")
        params.append(user_id)

    if normalized_status:
        normalized_status = _normalize_status_text(
            normalized_status,
            allowed=ALLOWED_DOCUMENT_STATUSES,
            field_name="status",
        )
        clauses.append("d.status = %s")
        params.append(normalized_status)

    params.append(max(int(limit or 100), 1))

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT d.id,
                   d.document_no,
                   d.title,
                   d.status,
                   d.legacy_source_type,
                   d.legacy_source_id,
                   d.submitted_at,
                   d.completed_at,
                   d.created_at,
                   f.form_key,
                   f.display_name AS form_display_name,
                   requester.full_name AS requester_name
            FROM approval_documents d
            LEFT JOIN approval_forms f ON f.id = d.form_id
            LEFT JOIN arls_users requester ON requester.id = d.requester_user_id
            WHERE {' AND '.join(clauses)}
            ORDER BY COALESCE(d.submitted_at, d.created_at) DESC, d.id DESC
            LIMIT %s
            """,
            tuple(params),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows


def list_approval_review_queue(
    conn,
    *,
    tenant_id: str,
    reviewer_user_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT d.id,
                   d.document_no,
                   d.title,
                   d.status,
                   d.legacy_source_type,
                   d.legacy_source_id,
                   d.submitted_at,
                   s.id AS step_id,
                   s.step_order,
                   f.form_key,
                   f.display_name AS form_display_name,
                   requester.full_name AS requester_name
            FROM approval_steps s
            JOIN approval_documents d
              ON d.id = s.document_id
            LEFT JOIN approval_forms f
              ON f.id = d.form_id
            LEFT JOIN arls_users requester
              ON requester.id = d.requester_user_id
            WHERE s.tenant_id = %s
              AND s.approver_user_id = %s
              AND s.status = %s
            ORDER BY COALESCE(d.submitted_at, d.created_at) DESC, s.step_order ASC
            LIMIT %s
            """,
            (tenant_id, reviewer_user_id, STEP_STATUS_PENDING, max(int(limit or 100), 1)),
        )
        rows = [dict(row) for row in (cur.fetchall() or [])]
    return rows


def record_approval_action(
    conn,
    *,
    tenant_id: str,
    document_id: str,
    actor_user_id: str,
    actor_role: str | None,
    action_type: str,
    comment_text: str | None = None,
) -> dict[str, Any]:
    normalized_action = _normalize_status_text(
        str(action_type or "").strip().lower(),
        allowed=ALLOWED_ACTION_TYPES,
        field_name="action_type",
    )
    document = _fetch_document_row(conn, tenant_id=tenant_id, document_id=document_id)
    if not document:
        raise _http_error(status.HTTP_404_NOT_FOUND, "결재 문서를 찾을 수 없습니다.")

    current_step = _fetch_first_pending_step(conn, document_id=document_id)

    if normalized_action == ACTION_COMMENT:
        if comment_text:
            _insert_document_comment(
                conn,
                tenant_id=tenant_id,
                document_id=document_id,
                actor_user_id=actor_user_id,
                body=comment_text,
            )
        _insert_document_action(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            step_id=None,
            actor_user_id=actor_user_id,
            action_type=ACTION_COMMENT,
            comment_text=comment_text,
        )
        return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=document_id)

    if not current_step:
        raise _http_error(status.HTTP_409_CONFLICT, "현재 처리할 결재 단계가 없습니다.")

    actor_is_super_admin = is_super_admin(actor_role)
    if not actor_is_super_admin and str(current_step.get("approver_user_id") or "") != str(actor_user_id):
        raise _http_error(status.HTTP_403_FORBIDDEN, "현재 결재 단계의 담당자가 아닙니다.")

    with conn.cursor() as cur:
        if normalized_action == ACTION_APPROVE:
            cur.execute(
                """
                UPDATE approval_steps
                SET status = %s,
                    acted_at = timezone('utc', now())
                WHERE id = %s
                """,
                (STEP_STATUS_APPROVED, current_step["id"]),
            )
            next_step = _fetch_next_queued_step(conn, document_id=document_id, after_step_order=int(current_step["step_order"]))
            if next_step:
                cur.execute(
                    """
                    UPDATE approval_steps
                    SET status = %s
                    WHERE id = %s
                    """,
                    (STEP_STATUS_PENDING, next_step["id"]),
                )
                cur.execute(
                    """
                    UPDATE approval_documents
                    SET status = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (DOCUMENT_STATUS_IN_REVIEW, document_id),
                )
            else:
                cur.execute(
                    """
                    UPDATE approval_documents
                    SET status = %s,
                        completed_at = timezone('utc', now()),
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (DOCUMENT_STATUS_APPROVED, document_id),
                )
        elif normalized_action in {ACTION_REJECT, ACTION_RETURN}:
            step_status = STEP_STATUS_REJECTED if normalized_action == ACTION_REJECT else STEP_STATUS_RETURNED
            document_status = DOCUMENT_STATUS_REJECTED if normalized_action == ACTION_REJECT else DOCUMENT_STATUS_RETURNED
            cur.execute(
                """
                UPDATE approval_steps
                SET status = %s,
                    acted_at = timezone('utc', now())
                WHERE id = %s
                """,
                (step_status, current_step["id"]),
            )
            cur.execute(
                """
                UPDATE approval_steps
                SET status = %s
                WHERE document_id = %s
                  AND status IN (%s, %s)
                  AND id <> %s
                """,
                (STEP_STATUS_SKIPPED, document_id, STEP_STATUS_PENDING, STEP_STATUS_QUEUED, current_step["id"]),
            )
            cur.execute(
                """
                UPDATE approval_documents
                SET status = %s,
                    completed_at = timezone('utc', now()),
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (document_status, document_id),
            )
        elif normalized_action in {ACTION_CANCEL, ACTION_RECALL}:
            document_status = DOCUMENT_STATUS_CANCELLED if normalized_action == ACTION_CANCEL else DOCUMENT_STATUS_RECALLED
            cur.execute(
                """
                UPDATE approval_steps
                SET status = %s
                WHERE document_id = %s
                  AND status IN (%s, %s)
                """,
                (STEP_STATUS_CANCELLED, document_id, STEP_STATUS_PENDING, STEP_STATUS_QUEUED),
            )
            cur.execute(
                """
                UPDATE approval_documents
                SET status = %s,
                    cancelled_at = timezone('utc', now()),
                    updated_at = timezone('utc', now())
                WHERE id = %s
                """,
                (document_status, document_id),
            )

    if comment_text:
        _insert_document_comment(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            actor_user_id=actor_user_id,
            body=comment_text,
        )

        _insert_document_action(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            step_id=str(current_step.get("id") or "").strip() or None,
        actor_user_id=actor_user_id,
        action_type=normalized_action,
            comment_text=comment_text,
        )

    _sync_legacy_leave_request_from_approval(
        conn,
        document=document,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action_type=normalized_action,
        comment_text=comment_text,
    )

    updated = fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=document_id)
    next_pending = _fetch_first_pending_step(conn, document_id=document_id)
    if normalized_action == ACTION_APPROVE and next_pending and next_pending.get("approver_user_id"):
        _run_noncritical_side_effect(
            conn,
            log_message=f"[APPROVAL][NOTIFY] failed to dispatch next review request doc={document_id}",
            callback=lambda: GroupwareNotificationDispatcher(conn).dispatch_in_app(
                tenant_id=tenant_id,
                user_id=str(next_pending["approver_user_id"]),
                message=f"결재 요청이 도착했습니다: {updated.get('title')}",
                category="approval",
                dedupe_key=f"approval:doc:{document_id}:pending:{next_pending['step_order']}",
                payload={"document_id": document_id, "form_key": updated.get("form_key")},
            ),
        )
        _run_noncritical_side_effect(
            conn,
            log_message=f"[APPROVAL][MAIL] failed to queue next review request doc={document_id}",
            callback=lambda: queue_approval_notification_mail(
                conn,
                tenant_id=tenant_id,
                template_key="approval_review_requested",
                document_id=document_id,
                recipient_user_id=str(next_pending["approver_user_id"]),
                render_context={
                    "title": str(updated.get("title") or ""),
                    "form_display_name": str(updated.get("form_display_name") or updated.get("form_key") or ""),
                },
            ),
        )

    if normalized_action == ACTION_APPROVE and str(updated.get("status") or "").strip().lower() == DOCUMENT_STATUS_APPROVED:
        requester_user_id = str(document.get("requester_user_id") or "").strip()
        if requester_user_id:
            _run_noncritical_side_effect(
                conn,
                log_message=f"[APPROVAL][MAIL] failed to queue approval-complete doc={document_id}",
                callback=lambda: queue_approval_notification_mail(
                    conn,
                    tenant_id=tenant_id,
                    template_key="approval_approved",
                    document_id=document_id,
                    recipient_user_id=requester_user_id,
                    render_context={
                        "title": str(updated.get("title") or ""),
                        "form_display_name": str(updated.get("form_display_name") or updated.get("form_key") or ""),
                    },
                ),
            )

    if normalized_action in {ACTION_REJECT, ACTION_RETURN}:
        requester_user_id = str(document.get("requester_user_id") or "").strip()
        if requester_user_id:
            _run_noncritical_side_effect(
                conn,
                log_message=f"[APPROVAL][MAIL] failed to queue approval-rejected doc={document_id}",
                callback=lambda: queue_approval_notification_mail(
                    conn,
                    tenant_id=tenant_id,
                    template_key="approval_rejected",
                    document_id=document_id,
                    recipient_user_id=requester_user_id,
                    render_context={
                        "title": str(updated.get("title") or ""),
                        "form_display_name": str(updated.get("form_display_name") or updated.get("form_key") or ""),
                    },
                ),
            )

    _run_noncritical_side_effect(
        conn,
        log_message=f"[APPROVAL][AUDIT] failed to write document_{normalized_action} doc={document_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="approvals",
            action_type=f"document_{normalized_action}",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="approval_document",
            target_id=document_id,
            detail={"document_status": updated.get("status"), "step_id": current_step.get("id")},
        ),
    )
    return updated


def _find_legacy_document(
    conn,
    *,
    tenant_id: str,
    legacy_source_type: str,
    legacy_source_id: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   status
            FROM approval_documents
            WHERE tenant_id = %s
              AND legacy_source_type = %s
              AND legacy_source_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, legacy_source_type, legacy_source_id),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def _sync_document_terminal_state(
    conn,
    *,
    tenant_id: str,
    document_id: str,
    actor_user_id: str | None,
    actor_role: str | None,
    document_status: str,
    comment_text: str | None = None,
) -> None:
    normalized_status = _normalize_status_text(
        document_status,
        allowed=ALLOWED_DOCUMENT_STATUSES,
        field_name="status",
    )
    step_status = None
    action_type = None
    if normalized_status == DOCUMENT_STATUS_APPROVED:
        step_status = STEP_STATUS_APPROVED
        action_type = ACTION_APPROVE
    elif normalized_status == DOCUMENT_STATUS_REJECTED:
        step_status = STEP_STATUS_REJECTED
        action_type = ACTION_REJECT
    elif normalized_status == DOCUMENT_STATUS_RETURNED:
        step_status = STEP_STATUS_RETURNED
        action_type = ACTION_RETURN
    elif normalized_status == DOCUMENT_STATUS_CANCELLED:
        step_status = STEP_STATUS_CANCELLED
        action_type = ACTION_CANCEL
    elif normalized_status == DOCUMENT_STATUS_RECALLED:
        step_status = STEP_STATUS_CANCELLED
        action_type = ACTION_RECALL
    elif normalized_status in {DOCUMENT_STATUS_SUBMITTED, DOCUMENT_STATUS_IN_REVIEW, DOCUMENT_STATUS_DRAFT}:
        return

    pending_step = _fetch_first_pending_step(conn, document_id=document_id)
    with conn.cursor() as cur:
        if pending_step and step_status:
            cur.execute(
                """
                UPDATE approval_steps
                SET status = %s,
                    acted_at = timezone('utc', now())
                WHERE id = %s
                """,
                (step_status, pending_step["id"]),
            )
        cur.execute(
            """
            UPDATE approval_steps
            SET status = %s
            WHERE document_id = %s
              AND status IN (%s, %s)
              AND (%s IS NULL OR id <> %s)
            """,
            (STEP_STATUS_SKIPPED if normalized_status in {DOCUMENT_STATUS_APPROVED, DOCUMENT_STATUS_REJECTED, DOCUMENT_STATUS_RETURNED} else STEP_STATUS_CANCELLED,
             document_id,
             STEP_STATUS_PENDING,
             STEP_STATUS_QUEUED,
             pending_step.get("id") if pending_step else None,
             pending_step.get("id") if pending_step else None),
        )
        cur.execute(
            """
            UPDATE approval_documents
            SET status = %s,
                completed_at = CASE
                    WHEN %s IN (%s, %s, %s) THEN timezone('utc', now())
                    ELSE completed_at
                END,
                cancelled_at = CASE
                    WHEN %s IN (%s, %s) THEN timezone('utc', now())
                    ELSE cancelled_at
                END,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (
                normalized_status,
                normalized_status,
                DOCUMENT_STATUS_APPROVED,
                DOCUMENT_STATUS_REJECTED,
                DOCUMENT_STATUS_RETURNED,
                normalized_status,
                DOCUMENT_STATUS_CANCELLED,
                DOCUMENT_STATUS_RECALLED,
                document_id,
            ),
        )

    if comment_text:
        _insert_document_comment(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            actor_user_id=actor_user_id,
            body=comment_text,
        )
    if action_type:
        _insert_document_action(
            conn,
            tenant_id=tenant_id,
            document_id=document_id,
            step_id=pending_step.get("id") if pending_step else None,
            actor_user_id=actor_user_id,
            action_type=action_type,
            comment_text=comment_text,
        )
        _run_noncritical_side_effect(
            conn,
            log_message=f"[APPROVAL][AUDIT] failed to write legacy_sync_{action_type} doc={document_id}",
            callback=lambda: GroupwareAuditService(conn).write_event(
                tenant_id=tenant_id,
                module_key="approvals",
                action_type=f"legacy_sync_{action_type}",
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                target_type="approval_document",
                target_id=document_id,
                detail={"document_status": normalized_status},
            ),
        )


def create_leave_request_approval_adapter(conn, *, leave_row: dict[str, Any], actor_user: dict) -> dict[str, Any] | None:
    tenant_id = str(leave_row.get("tenant_id") or "").strip()
    legacy_source_id = str(leave_row.get("id") or "").strip()
    if not tenant_id or not legacy_source_id:
        return None
    existing = _find_legacy_document(
        conn,
        tenant_id=tenant_id,
        legacy_source_type="leave_request",
        legacy_source_id=legacy_source_id,
    )
    if existing:
        return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=str(existing["id"]))
    title = f"휴가신청 · {leave_row.get('employee_name') or leave_row.get('employee_code') or ''}".strip(" ·")
    return create_approval_document(
        conn,
        tenant_id=tenant_id,
        form_key="leave_request",
        title=title,
        requester_user_id=str(actor_user.get("id") or "").strip() or None,
        requester_role=str(actor_user.get("role") or "").strip() or None,
        employee_id=str(leave_row.get("employee_id") or "").strip() or None,
        site_id=str(leave_row.get("site_id") or "").strip() or None,
        payload={
            "employee_code": leave_row.get("employee_code"),
            "employee_name": leave_row.get("employee_name"),
            "leave_type": leave_row.get("leave_type"),
            "half_day_slot": leave_row.get("half_day_slot"),
            "start_at": leave_row.get("start_at"),
            "end_at": leave_row.get("end_at"),
            "reason": leave_row.get("reason"),
            "attachment_names": leave_row.get("attachment_names") or [],
        },
        submit=True,
        legacy_source_type="leave_request",
        legacy_source_id=legacy_source_id,
    )


def create_attendance_request_approval_adapter(conn, *, request_row: dict[str, Any], actor_user: dict) -> dict[str, Any] | None:
    tenant_id = str(request_row.get("tenant_id") or "").strip()
    legacy_source_id = str(request_row.get("id") or "").strip()
    if not tenant_id or not legacy_source_id:
        return None
    existing = _find_legacy_document(
        conn,
        tenant_id=tenant_id,
        legacy_source_type="attendance_request",
        legacy_source_id=legacy_source_id,
    )
    if existing:
        return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=str(existing["id"]))
    title = f"근태정정 · {request_row.get('employee_name') or request_row.get('employee_code') or ''}".strip(" ·")
    return create_approval_document(
        conn,
        tenant_id=tenant_id,
        form_key="attendance_correction",
        title=title,
        requester_user_id=str(actor_user.get("id") or "").strip() or None,
        requester_role=str(actor_user.get("role") or "").strip() or None,
        employee_id=str(request_row.get("employee_id") or "").strip() or None,
        site_id=str(request_row.get("site_id") or "").strip() or None,
        payload={
            "employee_code": request_row.get("employee_code"),
            "employee_name": request_row.get("employee_name"),
            "request_type": request_row.get("request_type"),
            "reason_code": request_row.get("reason_code"),
            "reason_detail": request_row.get("reason_detail"),
            "requested_at": request_row.get("requested_at"),
            "photo_names": request_row.get("photo_names") or [],
        },
        submit=True,
        legacy_source_type="attendance_request",
        legacy_source_id=legacy_source_id,
    )


def create_certificate_request_approval_adapter(
    conn,
    *,
    tenant_id: str,
    document_request_id: str,
    employee_id: str,
    company_id: str | None,
    actor_user: dict,
    certificate_type_key: str = "employment_certificate",
    certificate_type_name: str | None = None,
    purpose_code: str,
    purpose_text: str | None,
    submit_to: str | None = None,
    copy_count: int | None = None,
    include_address: bool | None = None,
    include_phone: bool | None = None,
    site_id: str | None = None,
    legacy_source_type: str = "certificate_request",
) -> dict[str, Any] | None:
    existing = _find_legacy_document(
        conn,
        tenant_id=tenant_id,
        legacy_source_type=legacy_source_type,
        legacy_source_id=document_request_id,
    )
    if existing:
        return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=str(existing["id"]))
    return create_approval_document(
        conn,
        tenant_id=tenant_id,
        form_key="employment_certificate" if certificate_type_key == "employment_certificate" and legacy_source_type == "employment_certificate_request" else "certificate_request",
        title=f"{certificate_type_name or '증명서'} 발급",
        requester_user_id=str(actor_user.get("id") or "").strip() or None,
        requester_role=str(actor_user.get("role") or "").strip() or None,
        employee_id=employee_id,
        company_id=company_id,
        site_id=site_id,
        payload={
            "purpose_code": purpose_code,
            "purpose_text": purpose_text,
            "document_type": certificate_type_key,
            "certificate_type_key": certificate_type_key,
            "certificate_type_name": certificate_type_name,
            "submit_to": submit_to,
            "copy_count": int(copy_count or 1),
            "include_address": bool(include_address),
            "include_phone": bool(include_phone),
        },
        submit=True,
        legacy_source_type=legacy_source_type,
        legacy_source_id=document_request_id,
    )


def sync_legacy_approval_status(
    conn,
    *,
    tenant_id: str,
    legacy_source_type: str,
    legacy_source_id: str,
    status_value: str,
    actor_user_id: str | None,
    actor_role: str | None,
    comment_text: str | None = None,
) -> dict[str, Any] | None:
    existing = _find_legacy_document(
        conn,
        tenant_id=tenant_id,
        legacy_source_type=legacy_source_type,
        legacy_source_id=legacy_source_id,
    )
    if not existing:
        return None
    _sync_document_terminal_state(
        conn,
        tenant_id=tenant_id,
        document_id=str(existing["id"]),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        document_status=status_value,
        comment_text=comment_text,
    )
    return fetch_approval_document_detail(conn, tenant_id=tenant_id, document_id=str(existing["id"]))
