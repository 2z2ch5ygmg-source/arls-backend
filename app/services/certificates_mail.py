from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from ..config import settings
from ..services.groupware_foundation import GroupwareAuditService
from ..utils.schema_introspection import table_column_exists

EMPLOYMENT_CERTIFICATE_TYPE_KEY = "employment_certificate"
CAREER_CERTIFICATE_TYPE_KEY = "career_certificate"
RETIREMENT_CERTIFICATE_TYPE_KEY = "retirement_certificate"
LEAVE_OF_ABSENCE_CERTIFICATE_TYPE_KEY = "leave_of_absence_certificate"
DEFAULT_MAIL_ACCOUNT_KEY = "default_smtp"
DEFAULT_MAIL_PROFILE_KEY = "default_company"
ISSUE_JOB_PAYLOAD_LIMIT = 4000
MAIL_JOB_SOURCE_TYPE = "certificate_request_mail"
CERTIFICATE_DAILY_LIMIT = 4
logger = logging.getLogger(__name__)

CERTIFICATE_TYPE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "type_key": EMPLOYMENT_CERTIFICATE_TYPE_KEY,
        "display_name": "재직증명서",
        "requires_approval": False,
        "auto_mail_enabled": False,
        "meta_json": {
            "legacy_document_type": "employment_certificate",
            "rollout": "live",
            "template_scope": "company_per_type",
        },
    },
    {
        "type_key": CAREER_CERTIFICATE_TYPE_KEY,
        "display_name": "경력증명서",
        "requires_approval": False,
        "auto_mail_enabled": False,
        "meta_json": {"rollout": "live", "template_scope": "company_per_type"},
    },
    {
        "type_key": RETIREMENT_CERTIFICATE_TYPE_KEY,
        "display_name": "퇴직증명서",
        "requires_approval": True,
        "auto_mail_enabled": False,
        "meta_json": {"rollout": "live", "template_scope": "company_per_type"},
    },
    {
        "type_key": LEAVE_OF_ABSENCE_CERTIFICATE_TYPE_KEY,
        "display_name": "휴직증명서",
        "requires_approval": True,
        "auto_mail_enabled": False,
        "meta_json": {"rollout": "live", "template_scope": "company_per_type"},
    },
    {
        "type_key": "payroll_statement",
        "display_name": "급여확인서",
        "requires_approval": True,
        "auto_mail_enabled": False,
        "meta_json": {"rollout": "planned"},
    },
    {
        "type_key": "tax_withholding_statement",
        "display_name": "원천징수 관련 서류",
        "requires_approval": True,
        "auto_mail_enabled": False,
        "meta_json": {"rollout": "planned"},
    },
)

MAIL_TEMPLATE_DEFINITIONS: tuple[dict[str, str], ...] = (
    {
        "template_key": "certificate_issued_company",
        "subject_template": "{{ certificate_type_name }} 발급 - {{ employee_name }}",
        "body_template": "회사 보관용 {{ certificate_type_name }}가 발급되었습니다.",
    },
    {
        "template_key": "certificate_issued_employee",
        "subject_template": "{{ certificate_type_name }} 발급 - {{ employee_name }}",
        "body_template": "직원 전달용 {{ certificate_type_name }}가 발급되었습니다.",
    },
    {
        "template_key": "employment_certificate_issued_company",
        "subject_template": "재직증명서 발급 - {{ employee_name }}",
        "body_template": "회사 보관용 재직증명서가 발급되었습니다.",
    },
    {
        "template_key": "employment_certificate_issued_employee",
        "subject_template": "재직증명서 발급 - {{ employee_name }}",
        "body_template": "직원 전달용 재직증명서가 발급되었습니다.",
    },
    {
        "template_key": "approval_review_requested",
        "subject_template": "결재 검토 요청 - {{ title }}",
        "body_template": "새 결재 문서가 도착했습니다.",
    },
    {
        "template_key": "approval_approved",
        "subject_template": "결재 승인 완료 - {{ title }}",
        "body_template": "결재가 승인되었습니다.",
    },
    {
        "template_key": "approval_rejected",
        "subject_template": "결재 반려 - {{ title }}",
        "body_template": "결재가 반려되었습니다.",
    },
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _mail_account_active() -> bool:
    return bool(settings.mail_enabled and settings.smtp_host)


def _default_sender_name() -> str:
    raw = str(settings.mail_from or "").strip()
    local_part = raw.split("@", 1)[0].strip() if "@" in raw else raw
    return local_part or "ARLS"


def _normalize_certificate_status(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"requested", "generating", "issued", "rejected", "failed"}:
        return normalized
    if normalized == "approved":
        return "generating"
    return "requested"


def _issue_job_state_from_certificate_status(value: str | None) -> str | None:
    normalized = _normalize_certificate_status(value)
    if normalized == "generating":
        return "queued"
    if normalized == "issued":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized == "rejected":
        return "cancelled"
    return None


def _json_dumps(value: Any) -> str:
    def _default_serializer(item: Any) -> str:
        if isinstance(item, (uuid.UUID, datetime, date)):
            return str(item)
        return str(item)

    return json.dumps(value or {}, ensure_ascii=False, default=_default_serializer)


def _normalize_mail_job_state(value: str | None, *, default: str = "queued") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        return default
    return normalized


def _truncate_error(message: str | None) -> str | None:
    normalized = str(message or "").strip()
    if not normalized:
        return None
    return normalized[:ISSUE_JOB_PAYLOAD_LIMIT]


def _render_template_value(template: str, context: dict[str, Any] | None = None) -> str:
    rendered = str(template or "")
    resolved_context = {str(key): "" if value is None else str(value) for key, value in (context or {}).items()}
    for key, value in resolved_context.items():
        rendered = rendered.replace(f"{{{{ {key} }}}}", value)
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return re.sub(r"\{\{\s*[^}]+\s*\}\}", "", rendered).strip()


def _run_noncritical_db_step(
    conn,
    *,
    step_name: str,
    callback,
    fallback=None,
    error_collector: list[str] | None = None,
):
    savepoint = f"certificate_mail_sp_{uuid.uuid4().hex}"
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {savepoint}")
    try:
        result = callback()
    except Exception as exc:
        logger.exception("[CERTIFICATES][MAIL] non-critical db step failed step=%s", step_name)
        if error_collector is not None:
            error_collector.append(str(exc)[:200])
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        return fallback
    with conn.cursor() as cur:
        cur.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result


def ensure_default_certificate_types(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for definition in CERTIFICATE_TYPE_DEFINITIONS:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO certificate_types (
                    tenant_id,
                    type_key,
                    display_name,
                    requires_approval,
                    auto_mail_enabled,
                    meta_json,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()), timezone('utc', now()))
                ON CONFLICT (tenant_id, type_key) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    requires_approval = EXCLUDED.requires_approval,
                    auto_mail_enabled = EXCLUDED.auto_mail_enabled,
                    meta_json = EXCLUDED.meta_json,
                    updated_at = timezone('utc', now())
                RETURNING id, type_key, display_name, requires_approval, auto_mail_enabled, meta_json
                """,
                (
                    tenant_id,
                    definition["type_key"],
                    definition["display_name"],
                    bool(definition["requires_approval"]),
                    bool(definition["auto_mail_enabled"]),
                    _json_dumps(definition.get("meta_json")),
                ),
            )
            row = cur.fetchone() or {}
        rows.append(
            {
                "id": str(row.get("id") or ""),
                "type_key": definition["type_key"],
                "display_name": row.get("display_name") or definition["display_name"],
                "requires_approval": bool(row.get("requires_approval")),
                "auto_mail_enabled": bool(row.get("auto_mail_enabled")),
                "meta_json": row.get("meta_json") or definition.get("meta_json") or {},
            }
        )
    return rows


def ensure_default_mail_account(conn, *, tenant_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mail_accounts (
                tenant_id,
                account_key,
                provider,
                smtp_host,
                smtp_port,
                sender_email,
                sender_name,
                username,
                secret_ref,
                imap_host,
                imap_port,
                is_active,
                settings_json,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, 'smtp', %s, %s, %s, %s, %s, %s, NULL, NULL, %s, %s::jsonb,
                timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, account_key) DO UPDATE
            SET smtp_host = EXCLUDED.smtp_host,
                smtp_port = EXCLUDED.smtp_port,
                sender_email = EXCLUDED.sender_email,
                sender_name = EXCLUDED.sender_name,
                username = EXCLUDED.username,
                secret_ref = EXCLUDED.secret_ref,
                is_active = EXCLUDED.is_active,
                settings_json = EXCLUDED.settings_json,
                updated_at = timezone('utc', now())
            RETURNING id, account_key, provider, smtp_host, smtp_port, sender_email, sender_name, username, secret_ref, is_active, settings_json
            """,
            (
                tenant_id,
                DEFAULT_MAIL_ACCOUNT_KEY,
                settings.smtp_host or None,
                int(settings.smtp_port or 587),
                settings.mail_from or None,
                _default_sender_name(),
                settings.smtp_username or None,
                "env:SMTP_PASSWORD" if settings.smtp_username else None,
                _mail_account_active(),
                _json_dumps(
                    {
                        "managed_by": "phase4_seed",
                        "mail_enabled": bool(settings.mail_enabled),
                        "smtp_ssl": bool(settings.smtp_ssl),
                        "smtp_starttls": bool(settings.smtp_starttls),
                        "imap_enabled": False,
                    }
                ),
            ),
        )
        row = cur.fetchone() or {}
    return {
        "id": str(row.get("id") or ""),
        "account_key": row.get("account_key") or DEFAULT_MAIL_ACCOUNT_KEY,
        "provider": row.get("provider") or "smtp",
        "smtp_host": row.get("smtp_host"),
        "smtp_port": row.get("smtp_port"),
        "sender_email": row.get("sender_email"),
        "sender_name": row.get("sender_name"),
        "username": row.get("username"),
        "secret_ref": row.get("secret_ref"),
        "is_active": bool(row.get("is_active")),
        "settings_json": row.get("settings_json") or {},
    }


def ensure_default_mail_sender_profile(
    conn,
    *,
    tenant_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    account = ensure_default_mail_account(conn, tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE mail_sender_profiles
            SET is_default = FALSE,
                updated_at = timezone('utc', now())
            WHERE tenant_id = %s
              AND profile_key <> %s
              AND is_default = TRUE
            """,
            (tenant_id, DEFAULT_MAIL_PROFILE_KEY),
        )
        cur.execute(
            """
            INSERT INTO mail_sender_profiles (
                tenant_id,
                mail_account_id,
                profile_key,
                display_name,
                reply_to_email,
                from_email,
                is_default,
                settings_json,
                created_at,
                updated_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, TRUE, %s::jsonb, timezone('utc', now()), timezone('utc', now())
            )
            ON CONFLICT (tenant_id, profile_key) DO UPDATE
            SET mail_account_id = EXCLUDED.mail_account_id,
                display_name = EXCLUDED.display_name,
                reply_to_email = EXCLUDED.reply_to_email,
                from_email = EXCLUDED.from_email,
                is_default = EXCLUDED.is_default,
                settings_json = EXCLUDED.settings_json,
                updated_at = timezone('utc', now())
            RETURNING id, profile_key, display_name, reply_to_email, from_email, is_default, settings_json, mail_account_id
            """,
            (
                tenant_id,
                account["id"] or None,
                DEFAULT_MAIL_PROFILE_KEY,
                "기본 회사 발신",
                settings.mail_from or None,
                settings.mail_from or None,
                _json_dumps(
                    {
                        "managed_by": "phase4_seed",
                        "actor_user_id": actor_user_id,
                        "sender_name": account.get("sender_name") or _default_sender_name(),
                    }
                ),
            ),
        )
        row = cur.fetchone() or {}
    return {
        "id": str(row.get("id") or ""),
        "profile_key": row.get("profile_key") or DEFAULT_MAIL_PROFILE_KEY,
        "display_name": row.get("display_name") or "기본 회사 발신",
        "reply_to_email": row.get("reply_to_email"),
        "from_email": row.get("from_email"),
        "is_default": bool(row.get("is_default")),
        "mail_account_id": str(row.get("mail_account_id") or account["id"] or ""),
        "settings_json": row.get("settings_json") or {},
    }


def ensure_default_mail_templates(
    conn,
    *,
    tenant_id: str,
    actor_user_id: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for definition in MAIL_TEMPLATE_DEFINITIONS:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mail_templates (
                    tenant_id,
                    template_key,
                    subject_template,
                    body_template,
                    channel,
                    is_active,
                    created_by,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, 'email', TRUE, %s, timezone('utc', now()), timezone('utc', now()))
                ON CONFLICT (tenant_id, template_key) DO UPDATE
                SET subject_template = EXCLUDED.subject_template,
                    body_template = EXCLUDED.body_template,
                    is_active = EXCLUDED.is_active,
                    updated_at = timezone('utc', now())
                RETURNING id, template_key, subject_template, body_template, channel, is_active
                """,
                (
                    tenant_id,
                    definition["template_key"],
                    definition["subject_template"],
                    definition["body_template"],
                    actor_user_id,
                ),
            )
            row = cur.fetchone() or {}
        rows.append(
            {
                "id": str(row.get("id") or ""),
                "template_key": row.get("template_key") or definition["template_key"],
                "subject_template": row.get("subject_template") or definition["subject_template"],
                "body_template": row.get("body_template") or definition["body_template"],
                "channel": row.get("channel") or "email",
                "is_active": bool(row.get("is_active")),
            }
        )
    return rows


def ensure_certificate_mail_foundation(
    conn,
    *,
    tenant_id: str,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    certificate_types = ensure_default_certificate_types(conn, tenant_id=tenant_id)
    mail_account = ensure_default_mail_account(conn, tenant_id=tenant_id)
    mail_profile = ensure_default_mail_sender_profile(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    mail_templates = ensure_default_mail_templates(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    return {
        "certificate_types": certificate_types,
        "mail_account": mail_account,
        "mail_profile": mail_profile,
        "mail_templates": mail_templates,
    }


def _resolve_certificate_type_row(conn, *, tenant_id: str, type_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, type_key, display_name, requires_approval, auto_mail_enabled, meta_json
            FROM certificate_types
            WHERE tenant_id = %s
              AND type_key = %s
            LIMIT 1
            """,
            (tenant_id, type_key),
        )
        return cur.fetchone()


def _fetch_mail_account_by_key(conn, *, tenant_id: str, account_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, account_key, provider, sender_email, sender_name, is_active, settings_json
            FROM mail_accounts
            WHERE tenant_id = %s
              AND account_key = %s
            LIMIT 1
            """,
            (tenant_id, account_key),
        )
        return cur.fetchone()


def _fetch_mail_profile_by_key(conn, *, tenant_id: str, profile_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, profile_key, display_name, reply_to_email, from_email, is_default, mail_account_id, settings_json
            FROM mail_sender_profiles
            WHERE tenant_id = %s
              AND profile_key = %s
            LIMIT 1
            """,
            (tenant_id, profile_key),
        )
        return cur.fetchone()


def _fetch_mail_template_by_key(conn, *, tenant_id: str, template_key: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, template_key, subject_template, body_template, channel, is_active
            FROM mail_templates
            WHERE tenant_id = %s
              AND template_key = %s
            LIMIT 1
            """,
            (tenant_id, template_key),
        )
        return cur.fetchone()


def _type_is_live(row: dict[str, Any] | None) -> bool:
    meta = dict((row or {}).get("meta_json") or {})
    return str(meta.get("rollout") or "").strip().lower() != "planned"


def _fetch_certificate_employee_row(conn, *, tenant_id: str, employee_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id,
                   e.tenant_id,
                   COALESCE(e.company_id, s.company_id) AS company_id,
                   e.site_id,
                   e.full_name,
                   e.hire_date,
                   e.leave_date,
                   COALESCE(e.employment_status, 'active') AS employment_status,
                   e.loa_start_date,
                   e.loa_end_date,
                   COALESCE(e.phone, '') AS phone,
                   COALESCE(e.address, '') AS address
            FROM employees e
            LEFT JOIN sites s ON s.id = e.site_id
            WHERE e.tenant_id = %s
              AND e.id = %s
            LIMIT 1
            """,
            (tenant_id, employee_id),
        )
        return cur.fetchone()


def _fetch_tenant_archive_email(conn, *, tenant_id: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(email, '') AS email
            FROM tenant_profiles
            WHERE tenant_id = %s
            LIMIT 1
            """,
            (tenant_id,),
        )
        row = cur.fetchone() or {}
    return str(row.get("email") or "").strip()


def _today_kst() -> date:
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=9))).date()


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def _certificate_type_eligibility(
    *,
    type_key: str,
    employee_row: dict[str, Any] | None,
    employee_email: str | None,
    company_archive_email: str | None,
) -> tuple[bool, str | None]:
    if not employee_row:
        return False, "직원 정보를 찾을 수 없습니다."

    today = _today_kst()
    status_value = str(employee_row.get("employment_status") or "active").strip().lower()
    hire_date = _coerce_date(employee_row.get("hire_date"))
    leave_date = _coerce_date(employee_row.get("leave_date"))
    loa_start_date = _coerce_date(employee_row.get("loa_start_date"))
    loa_end_date = _coerce_date(employee_row.get("loa_end_date"))

    if type_key == EMPLOYMENT_CERTIFICATE_TYPE_KEY:
        if status_value in {"terminated", "retired"} or (leave_date and leave_date <= today):
            return False, "퇴직 상태에서는 재직증명서를 신청할 수 없습니다."
        if not hire_date:
            return False, "입사일 정보가 필요합니다."
        return True, None

    if type_key == CAREER_CERTIFICATE_TYPE_KEY:
        if not hire_date:
            return False, "입사일 정보가 필요합니다."
        return True, None

    if type_key == RETIREMENT_CERTIFICATE_TYPE_KEY:
        if status_value in {"terminated", "retired"} or leave_date:
            return True, None
        return False, "퇴직 처리된 직원만 신청할 수 있습니다."

    if type_key == LEAVE_OF_ABSENCE_CERTIFICATE_TYPE_KEY:
        if status_value not in {"leave_of_absence", "loa"}:
            return False, "휴직 상태인 직원만 신청할 수 있습니다."
        if loa_start_date and loa_start_date > today:
            return False, "휴직 시작일 이후에 신청할 수 있습니다."
        if loa_end_date and loa_end_date < today:
            return False, "휴직 기간 중에만 신청할 수 있습니다."
        return True, None

    return False, "지원하지 않는 증명서 타입입니다."


def upsert_certificate_issue_job(
    conn,
    *,
    tenant_id: str,
    certificate_request_id: str,
    job_state: str,
    payload_extra: dict[str, Any] | None = None,
    increment_attempts: bool = False,
    last_error: str | None = None,
) -> dict[str, Any]:
    desired_state = str(job_state or "").strip().lower() or "queued"
    completed_at = _utcnow() if desired_state in {"completed", "failed", "cancelled"} else None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   attempts,
                   payload_json
            FROM certificate_issue_jobs
            WHERE tenant_id = %s
              AND certificate_request_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, certificate_request_id),
        )
        existing = cur.fetchone() or {}
        existing_id = str(existing.get("id") or "").strip()
        attempts = int(existing.get("attempts") or 0)
        merged_payload = dict(existing.get("payload_json") or {})
        merged_payload.update(payload_extra or {})
        if existing_id:
            cur.execute(
                """
                UPDATE certificate_issue_jobs
                SET job_state = %s,
                    attempts = %s,
                    last_error = %s,
                    payload_json = %s::jsonb,
                    locked_at = CASE WHEN %s = 'processing' THEN timezone('utc', now()) ELSE NULL END,
                    completed_at = %s
                WHERE id = %s
                RETURNING id, certificate_request_id, job_state, attempts, last_error, completed_at, payload_json
                """,
                (
                    desired_state,
                    attempts + (1 if increment_attempts else 0),
                    _truncate_error(last_error),
                    _json_dumps(merged_payload),
                    desired_state,
                    completed_at,
                    existing_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO certificate_issue_jobs (
                    tenant_id,
                    certificate_request_id,
                    job_state,
                    attempts,
                    last_error,
                    payload_json,
                    locked_at,
                    completed_at,
                    created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb,
                    CASE WHEN %s = 'processing' THEN timezone('utc', now()) ELSE NULL END,
                    %s,
                    timezone('utc', now())
                )
                RETURNING id, certificate_request_id, job_state, attempts, last_error, completed_at, payload_json
                """,
                (
                    tenant_id,
                    certificate_request_id,
                    desired_state,
                    1 if increment_attempts else 0,
                    _truncate_error(last_error),
                    _json_dumps(merged_payload),
                    desired_state,
                    completed_at,
                ),
            )
        row = cur.fetchone() or {}
    return {
        "id": str(row.get("id") or ""),
        "certificate_request_id": str(row.get("certificate_request_id") or certificate_request_id),
        "job_state": row.get("job_state") or desired_state,
        "attempts": int(row.get("attempts") or 0),
        "last_error": row.get("last_error"),
        "completed_at": row.get("completed_at"),
        "payload_json": row.get("payload_json") or merged_payload,
    }


def record_certificate_mail_delivery_for_request(
    conn,
    *,
    tenant_id: str,
    certificate_request_id: str,
    template_key: str,
    recipient_role: str,
    recipient_email: str,
    subject: str,
    body_text: str,
    attachment_name: str,
    sent: bool,
    error: str | None = None,
    sent_at: datetime | None = None,
) -> dict[str, Any] | None:
    foundation = ensure_certificate_mail_foundation(conn, tenant_id=tenant_id)
    template_row = _fetch_mail_template_by_key(conn, tenant_id=tenant_id, template_key=template_key)
    profile_row = _fetch_mail_profile_by_key(conn, tenant_id=tenant_id, profile_key=DEFAULT_MAIL_PROFILE_KEY)
    account_row = _fetch_mail_account_by_key(conn, tenant_id=tenant_id, account_key=DEFAULT_MAIL_ACCOUNT_KEY)
    state = "sent" if sent else "failed"
    occurred_at = sent_at or _utcnow()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO outbound_mail_jobs (
                tenant_id,
                mail_account_id,
                sender_profile_id,
                template_id,
                source_type,
                source_id,
                recipient_email,
                subject,
                body_text,
                state,
                attempts,
                sent_at,
                last_error,
                payload_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s::jsonb, timezone('utc', now())
            )
            RETURNING id, state, sent_at, last_error
            """,
            (
                tenant_id,
                str((account_row or {}).get("id") or foundation["mail_account"]["id"] or "") or None,
                str((profile_row or {}).get("id") or foundation["mail_profile"]["id"] or "") or None,
                str((template_row or {}).get("id") or "") or None,
                MAIL_JOB_SOURCE_TYPE,
                f"{certificate_request_id}:{recipient_role}",
                recipient_email,
                subject,
                body_text,
                state,
                occurred_at if sent else None,
                _truncate_error(error),
                _json_dumps(
                    {
                        "certificate_request_id": certificate_request_id,
                        "recipient_role": recipient_role,
                        "attachment_name": attachment_name,
                        "template_key": template_key,
                    }
                ),
            ),
        )
        job_row = cur.fetchone() or {}
        cur.execute(
            """
            INSERT INTO mail_delivery_events (
                tenant_id,
                outbound_mail_job_id,
                event_type,
                provider_message_id,
                event_payload,
                occurred_at
            )
            VALUES (%s, %s, %s, NULL, %s::jsonb, %s)
            RETURNING id
            """,
            (
                tenant_id,
                job_row.get("id"),
                "delivered" if sent else "failed",
                _json_dumps(
                    {
                        "recipient_role": recipient_role,
                        "recipient_email": recipient_email,
                        "error": _truncate_error(error),
                    }
                ),
                occurred_at,
            ),
        )
        event_row = cur.fetchone() or {}
    return {
        "job_id": str(job_row.get("id") or ""),
        "event_id": str(event_row.get("id") or ""),
        "state": job_row.get("state") or state,
        "sent_at": job_row.get("sent_at"),
        "last_error": job_row.get("last_error"),
    }


def _resolve_user_mail_target(conn, *, tenant_id: str, user_id: str) -> dict[str, Any] | None:
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, username, full_name, employee_id
            FROM arls_users
            WHERE tenant_id = %s
              AND id = %s
            LIMIT 1
            """,
            (tenant_id, normalized_user_id),
        )
        row = cur.fetchone()
    if not row:
        return None

    username = str(row.get("username") or "").strip()
    email = username if "@" in username else ""
    employee_id = str(row.get("employee_id") or "").strip()
    if not email and employee_id:
        email = _resolve_employee_email(conn, tenant_id=tenant_id, employee_id=employee_id)
    if not email:
        return None
    return {
        "user_id": normalized_user_id,
        "email": email,
        "full_name": str(row.get("full_name") or "").strip(),
        "employee_id": employee_id or None,
    }


def _queue_outbound_mail_job(
    conn,
    *,
    tenant_id: str,
    template_key: str,
    source_type: str,
    source_id: str,
    recipient_email: str,
    render_context: dict[str, Any] | None = None,
    payload_json: dict[str, Any] | None = None,
    state: str = "queued",
) -> dict[str, Any] | None:
    target_email = str(recipient_email or "").strip()
    if not target_email:
        return None

    foundation = ensure_certificate_mail_foundation(conn, tenant_id=tenant_id)
    template_row = _fetch_mail_template_by_key(conn, tenant_id=tenant_id, template_key=template_key)
    if template_row and not bool(template_row.get("is_active")):
        return None
    profile_row = _fetch_mail_profile_by_key(conn, tenant_id=tenant_id, profile_key=DEFAULT_MAIL_PROFILE_KEY)
    account_row = _fetch_mail_account_by_key(conn, tenant_id=tenant_id, account_key=DEFAULT_MAIL_ACCOUNT_KEY)
    subject = _render_template_value(
        str((template_row or {}).get("subject_template") or ""),
        render_context,
    )
    body_text = _render_template_value(
        str((template_row or {}).get("body_template") or ""),
        render_context,
    )
    normalized_state = _normalize_mail_job_state(state)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO outbound_mail_jobs (
                tenant_id,
                mail_account_id,
                sender_profile_id,
                template_id,
                source_type,
                source_id,
                recipient_email,
                subject,
                body_text,
                state,
                attempts,
                payload_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, %s::jsonb, timezone('utc', now())
            )
            RETURNING id, state, subject, recipient_email, payload_json, created_at
            """,
            (
                tenant_id,
                str((account_row or {}).get("id") or foundation["mail_account"]["id"] or "") or None,
                str((profile_row or {}).get("id") or foundation["mail_profile"]["id"] or "") or None,
                str((template_row or {}).get("id") or "") or None,
                source_type,
                source_id,
                target_email,
                subject,
                body_text,
                normalized_state,
                _json_dumps(
                    {
                        "template_key": template_key,
                        "render_context": render_context or {},
                        "payload": payload_json or {},
                        "mail_account_active": bool((account_row or {}).get("is_active")),
                    }
                ),
            ),
        )
        job_row = cur.fetchone() or {}
        cur.execute(
            """
            INSERT INTO mail_delivery_events (
                tenant_id,
                outbound_mail_job_id,
                event_type,
                provider_message_id,
                event_payload,
                occurred_at
            )
            VALUES (%s, %s, %s, NULL, %s::jsonb, timezone('utc', now()))
            RETURNING id, occurred_at
            """,
            (
                tenant_id,
                job_row.get("id"),
                "queued",
                _json_dumps(
                    {
                        "template_key": template_key,
                        "recipient_email": target_email,
                        "source_type": source_type,
                        "source_id": source_id,
                    }
                ),
            ),
        )
        event_row = cur.fetchone() or {}
    return {
        "id": str(job_row.get("id") or ""),
        "state": job_row.get("state") or normalized_state,
        "subject": job_row.get("subject") or subject,
        "recipient_email": job_row.get("recipient_email") or target_email,
        "payload_json": job_row.get("payload_json") or {},
        "created_at": job_row.get("created_at"),
        "queued_event_id": str(event_row.get("id") or ""),
        "queued_at": event_row.get("occurred_at"),
    }


def queue_approval_notification_mail(
    conn,
    *,
    tenant_id: str,
    template_key: str,
    document_id: str,
    recipient_user_id: str,
    render_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    target = _resolve_user_mail_target(conn, tenant_id=tenant_id, user_id=recipient_user_id)
    if not target:
        return None
    return _queue_outbound_mail_job(
        conn,
        tenant_id=tenant_id,
        template_key=template_key,
        source_type="approval_notification",
        source_id=f"{document_id}:{template_key}:{recipient_user_id}",
        recipient_email=target["email"],
        render_context={
            "recipient_name": target.get("full_name") or "",
            **(render_context or {}),
        },
        payload_json={
            "document_id": document_id,
            "recipient_user_id": recipient_user_id,
            "template_key": template_key,
        },
    )


def list_certificate_types(
    conn,
    *,
    tenant_id: str,
    employee_id: str | None = None,
) -> list[dict[str, Any]]:
    ensure_default_certificate_types(conn, tenant_id=tenant_id)
    employee_row = _fetch_certificate_employee_row(conn, tenant_id=tenant_id, employee_id=employee_id) if employee_id else None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, type_key, display_name, requires_approval, auto_mail_enabled, meta_json, created_at, updated_at
            FROM certificate_types
            WHERE tenant_id = %s
            ORDER BY display_name ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "type_key": row.get("type_key"),
            "display_name": row.get("display_name"),
            "requires_approval": bool(row.get("requires_approval")),
            "auto_mail_enabled": bool(row.get("auto_mail_enabled")),
            "meta_json": row.get("meta_json") or {},
            "available": (
                _certificate_type_eligibility(
                    type_key=str(row.get("type_key") or "").strip(),
                    employee_row=employee_row,
                    employee_email=None,
                    company_archive_email=None,
                )[0]
                if employee_id and _type_is_live(row)
                else _type_is_live(row)
            ),
            "eligibility_reason": (
                _certificate_type_eligibility(
                    type_key=str(row.get("type_key") or "").strip(),
                    employee_row=employee_row,
                    employee_email=None,
                    company_archive_email=None,
                )[1]
                if employee_id and _type_is_live(row)
                else ("준비 중인 타입입니다." if not _type_is_live(row) else None)
            ),
            "daily_limit": CERTIFICATE_DAILY_LIMIT if _type_is_live(row) else None,
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def list_certificate_requests(
    conn,
    *,
    tenant_id: str,
    employee_id: str | None = None,
    requester_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses = ["cr.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    if employee_id:
        clauses.append("cr.employee_id = %s")
        params.append(employee_id)
    if requester_user_id:
        clauses.append("cr.requester_user_id = %s")
        params.append(requester_user_id)
    where_sql = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT cr.id,
                   cr.status,
                   cr.purpose_code,
                   cr.purpose_text,
                   cr.submit_to,
                   cr.copy_count,
                   cr.include_address,
                   cr.include_phone,
                   cr.rejection_reason,
                   cr.mail_company_sent_at,
                   cr.mail_employee_sent_at,
                   cr.mail_error,
                   cr.requested_at,
                   cr.issued_at,
                   cr.issue_number,
                   cr.file_name,
                   cr.file_mime_type,
                   CASE WHEN cr.file_bytes IS NOT NULL THEN TRUE ELSE FALSE END AS file_ready,
                   cr.legacy_source_type,
                   cr.legacy_source_id,
                   ct.type_key,
                   ct.display_name AS certificate_type_name,
                   ad.status AS approval_status,
                   COALESCE(job.job_state, '') AS issue_job_state,
                   COALESCE(job.last_error, '') AS issue_job_error
            FROM certificate_requests cr
            LEFT JOIN certificate_types ct ON ct.id = cr.certificate_type_id
            LEFT JOIN approval_documents ad ON ad.id = cr.approval_document_id
            LEFT JOIN certificate_issue_jobs job ON job.certificate_request_id = cr.id
            WHERE {where_sql}
            ORDER BY cr.requested_at DESC
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "status": row.get("status"),
            "purpose_code": row.get("purpose_code"),
            "purpose_text": row.get("purpose_text"),
            "submit_to": row.get("submit_to"),
            "copy_count": int(row.get("copy_count") or 1),
            "include_address": bool(row.get("include_address")),
            "include_phone": bool(row.get("include_phone")),
            "rejection_reason": row.get("rejection_reason"),
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
            "mail_error": row.get("mail_error"),
            "requested_at": row.get("requested_at"),
            "issued_at": row.get("issued_at"),
            "issue_number": row.get("issue_number"),
            "file_name": row.get("file_name"),
            "file_mime_type": row.get("file_mime_type"),
            "file_ready": bool(row.get("file_ready")),
            "legacy_source_type": row.get("legacy_source_type"),
            "legacy_source_id": row.get("legacy_source_id"),
            "certificate_type_key": row.get("type_key"),
            "certificate_type_name": row.get("certificate_type_name"),
            "approval_status": row.get("approval_status"),
            "issue_job_state": row.get("issue_job_state") or None,
            "issue_job_error": row.get("issue_job_error") or None,
        }
        for row in rows
    ]


def list_admin_certificate_requests(
    conn,
    *,
    tenant_id: str,
    limit: int = 100,
    status_filter: str | None = None,
    query: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["cr.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    normalized_status = str(status_filter or "").strip().lower()
    normalized_query = str(query or "").strip()
    if normalized_status and normalized_status != "all":
        clauses.append("lower(cr.status) = %s")
        params.append(normalized_status)
    if normalized_query:
        like = f"%{normalized_query}%"
        clauses.append(
            """
            (
                COALESCE(e.full_name, '') ILIKE %s
                OR COALESCE(e.employee_code, '') ILIKE %s
                OR COALESCE(ct.display_name, '') ILIKE %s
                OR COALESCE(cr.issue_number, '') ILIKE %s
            )
            """
        )
        params.extend([like, like, like, like])
    where_sql = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT cr.id,
                   cr.status,
                   cr.purpose_code,
                   cr.purpose_text,
                   cr.submit_to,
                   cr.copy_count,
                   cr.include_address,
                   cr.include_phone,
                   cr.rejection_reason,
                   cr.mail_company_sent_at,
                   cr.mail_employee_sent_at,
                   cr.mail_error,
                   cr.requested_at,
                   cr.issued_at,
                   cr.issue_number,
                   cr.file_name,
                   cr.file_mime_type,
                   CASE WHEN cr.file_bytes IS NOT NULL THEN TRUE ELSE FALSE END AS file_ready,
                   cr.legacy_source_type,
                   cr.legacy_source_id,
                   ct.type_key,
                   ct.display_name AS certificate_type_name,
                   e.id AS employee_id,
                   e.full_name AS employee_name,
                   e.employee_code,
                   COALESCE(c.company_name, t.tenant_name, '') AS company_name,
                   COALESCE(s.site_name, '본사') AS org_name,
                   ad.status AS approval_status,
                   COALESCE(job.job_state, '') AS issue_job_state,
                   COALESCE(job.last_error, '') AS issue_job_error
            FROM certificate_requests cr
            LEFT JOIN certificate_types ct ON ct.id = cr.certificate_type_id
            LEFT JOIN employees e ON e.id = cr.employee_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(cr.company_id, e.company_id, s.company_id)
            LEFT JOIN tenants t ON t.id = cr.tenant_id
            LEFT JOIN approval_documents ad ON ad.id = cr.approval_document_id
            LEFT JOIN certificate_issue_jobs job ON job.certificate_request_id = cr.id
            WHERE {where_sql}
            ORDER BY cr.requested_at DESC
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "status": row.get("status"),
            "purpose_code": row.get("purpose_code"),
            "purpose_text": row.get("purpose_text"),
            "submit_to": row.get("submit_to"),
            "copy_count": int(row.get("copy_count") or 1),
            "include_address": bool(row.get("include_address")),
            "include_phone": bool(row.get("include_phone")),
            "rejection_reason": row.get("rejection_reason"),
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
            "mail_error": row.get("mail_error"),
            "requested_at": row.get("requested_at"),
            "issued_at": row.get("issued_at"),
            "issue_number": row.get("issue_number"),
            "file_name": row.get("file_name"),
            "file_mime_type": row.get("file_mime_type"),
            "file_ready": bool(row.get("file_ready")),
            "legacy_source_type": row.get("legacy_source_type"),
            "legacy_source_id": row.get("legacy_source_id"),
            "certificate_type_key": row.get("type_key"),
            "certificate_type_name": row.get("certificate_type_name"),
            "employee_id": str(row.get("employee_id") or ""),
            "employee_name": row.get("employee_name"),
            "employee_code": row.get("employee_code"),
            "company_name": row.get("company_name"),
            "org": row.get("org_name"),
            "approval_status": row.get("approval_status"),
            "issue_job_state": row.get("issue_job_state") or None,
            "issue_job_error": row.get("issue_job_error") or None,
        }
        for row in rows
    ]


def list_certificate_issue_jobs(
    conn,
    *,
    tenant_id: str,
    limit: int = 100,
    state_filter: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["job.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    normalized_state = str(state_filter or "").strip().lower()
    if normalized_state and normalized_state != "all":
        clauses.append("lower(job.job_state) = %s")
        params.append(normalized_state)
    where_sql = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT job.id,
                   job.certificate_request_id,
                   job.job_state,
                   job.attempts,
                   job.last_error,
                   job.payload_json,
                   job.locked_at,
                   job.completed_at,
                   job.created_at,
                   cr.status AS certificate_status,
                   cr.issue_number,
                   ct.display_name AS certificate_type_name,
                   e.full_name AS employee_name
            FROM certificate_issue_jobs job
            JOIN certificate_requests cr ON cr.id = job.certificate_request_id
            LEFT JOIN certificate_types ct ON ct.id = cr.certificate_type_id
            LEFT JOIN employees e ON e.id = cr.employee_id
            WHERE {where_sql}
            ORDER BY job.created_at DESC
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "certificate_request_id": str(row.get("certificate_request_id") or ""),
            "job_state": row.get("job_state"),
            "attempts": int(row.get("attempts") or 0),
            "last_error": row.get("last_error"),
            "payload_json": row.get("payload_json") or {},
            "locked_at": row.get("locked_at"),
            "completed_at": row.get("completed_at"),
            "created_at": row.get("created_at"),
            "certificate_status": row.get("certificate_status"),
            "issue_number": row.get("issue_number"),
            "certificate_type_name": row.get("certificate_type_name"),
            "employee_name": row.get("employee_name"),
        }
        for row in rows
    ]


def list_mail_accounts(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    ensure_default_mail_account(conn, tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, account_key, provider, smtp_host, smtp_port, sender_email, sender_name, username, secret_ref, is_active, settings_json, created_at, updated_at
            FROM mail_accounts
            WHERE tenant_id = %s
            ORDER BY account_key ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "account_key": row.get("account_key"),
            "provider": row.get("provider"),
            "smtp_host": row.get("smtp_host"),
            "smtp_port": row.get("smtp_port"),
            "sender_email": row.get("sender_email"),
            "sender_name": row.get("sender_name"),
            "username": row.get("username"),
            "secret_ref": row.get("secret_ref"),
            "is_active": bool(row.get("is_active")),
            "settings_json": row.get("settings_json") or {},
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def list_mail_sender_profiles(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    ensure_default_mail_sender_profile(conn, tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT p.id,
                   p.profile_key,
                   p.display_name,
                   p.reply_to_email,
                   p.from_email,
                   p.is_default,
                   p.settings_json,
                   p.created_at,
                   p.updated_at,
                   a.account_key,
                   a.sender_email
            FROM mail_sender_profiles p
            LEFT JOIN mail_accounts a ON a.id = p.mail_account_id
            WHERE p.tenant_id = %s
            ORDER BY p.is_default DESC, p.profile_key ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "profile_key": row.get("profile_key"),
            "display_name": row.get("display_name"),
            "reply_to_email": row.get("reply_to_email"),
            "from_email": row.get("from_email"),
            "is_default": bool(row.get("is_default")),
            "settings_json": row.get("settings_json") or {},
            "mail_account_key": row.get("account_key"),
            "mail_account_sender_email": row.get("sender_email"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def upsert_mail_sender_profile(
    conn,
    *,
    tenant_id: str,
    profile_key: str,
    display_name: str,
    reply_to_email: str | None,
    from_email: str | None,
    is_default: bool,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    ensure_default_mail_account(conn, tenant_id=tenant_id)
    account = _fetch_mail_account_by_key(conn, tenant_id=tenant_id, account_key=DEFAULT_MAIL_ACCOUNT_KEY)
    if is_default:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mail_sender_profiles
                SET is_default = FALSE,
                    updated_at = timezone('utc', now())
                WHERE tenant_id = %s
                """,
                (tenant_id,),
            )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mail_sender_profiles (
                tenant_id,
                mail_account_id,
                profile_key,
                display_name,
                reply_to_email,
                from_email,
                is_default,
                settings_json,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, timezone('utc', now()), timezone('utc', now()))
            ON CONFLICT (tenant_id, profile_key) DO UPDATE
            SET mail_account_id = EXCLUDED.mail_account_id,
                display_name = EXCLUDED.display_name,
                reply_to_email = EXCLUDED.reply_to_email,
                from_email = EXCLUDED.from_email,
                is_default = EXCLUDED.is_default,
                settings_json = EXCLUDED.settings_json,
                updated_at = timezone('utc', now())
            RETURNING id, profile_key, display_name, reply_to_email, from_email, is_default, settings_json
            """,
            (
                tenant_id,
                str((account or {}).get("id") or "") or None,
                profile_key,
                display_name,
                reply_to_email,
                from_email,
                is_default,
                _json_dumps({"updated_by": actor_user_id, "managed_by": "mail-profile-api"}),
            ),
        )
        row = cur.fetchone() or {}
    return {
        "id": str(row.get("id") or ""),
        "profile_key": row.get("profile_key") or profile_key,
        "display_name": row.get("display_name") or display_name,
        "reply_to_email": row.get("reply_to_email"),
        "from_email": row.get("from_email"),
        "is_default": bool(row.get("is_default")),
        "settings_json": row.get("settings_json") or {},
    }


def list_mail_templates(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    ensure_default_mail_templates(conn, tenant_id=tenant_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, template_key, subject_template, body_template, channel, is_active, created_at, updated_at
            FROM mail_templates
            WHERE tenant_id = %s
            ORDER BY template_key ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "template_key": row.get("template_key"),
            "subject_template": row.get("subject_template"),
            "body_template": row.get("body_template"),
            "channel": row.get("channel"),
            "is_active": bool(row.get("is_active")),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        for row in rows
    ]


def upsert_mail_template(
    conn,
    *,
    tenant_id: str,
    template_key: str,
    subject_template: str,
    body_template: str,
    is_active: bool,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO mail_templates (
                tenant_id,
                template_key,
                subject_template,
                body_template,
                channel,
                is_active,
                created_by,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, 'email', %s, %s, timezone('utc', now()), timezone('utc', now()))
            ON CONFLICT (tenant_id, template_key) DO UPDATE
            SET subject_template = EXCLUDED.subject_template,
                body_template = EXCLUDED.body_template,
                is_active = EXCLUDED.is_active,
                updated_at = timezone('utc', now())
            RETURNING id, template_key, subject_template, body_template, channel, is_active
            """,
            (
                tenant_id,
                template_key,
                subject_template,
                body_template,
                is_active,
                actor_user_id,
            ),
        )
        row = cur.fetchone() or {}
    return {
        "id": str(row.get("id") or ""),
        "template_key": row.get("template_key") or template_key,
        "subject_template": row.get("subject_template") or subject_template,
        "body_template": row.get("body_template") or body_template,
        "channel": row.get("channel") or "email",
        "is_active": bool(row.get("is_active")),
    }


def list_outbound_mail_jobs(
    conn,
    *,
    tenant_id: str,
    limit: int = 100,
    state_filter: str | None = None,
    source_type: str | None = None,
) -> list[dict[str, Any]]:
    clauses = ["j.tenant_id = %s"]
    params: list[Any] = [tenant_id]
    normalized_state = str(state_filter or "").strip().lower()
    normalized_source_type = str(source_type or "").strip()
    if normalized_state and normalized_state != "all":
        clauses.append("lower(j.state) = %s")
        params.append(normalized_state)
    if normalized_source_type:
        clauses.append("j.source_type = %s")
        params.append(normalized_source_type)
    where_sql = " AND ".join(clauses)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT j.id,
                   j.source_type,
                   j.source_id,
                   j.recipient_email,
                   j.subject,
                   j.state,
                   j.attempts,
                   j.scheduled_for,
                   j.sent_at,
                   j.last_error,
                   j.payload_json,
                   p.profile_key,
                   t.template_key
            FROM outbound_mail_jobs j
            LEFT JOIN mail_sender_profiles p ON p.id = j.sender_profile_id
            LEFT JOIN mail_templates t ON t.id = j.template_id
            WHERE {where_sql}
            ORDER BY j.created_at DESC
            LIMIT %s
            """,
            tuple(params + [int(limit)]),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "source_type": row.get("source_type"),
            "source_id": row.get("source_id"),
            "recipient_email": row.get("recipient_email"),
            "subject": row.get("subject"),
            "state": row.get("state"),
            "attempts": int(row.get("attempts") or 0),
            "scheduled_for": row.get("scheduled_for"),
            "sent_at": row.get("sent_at"),
            "last_error": row.get("last_error"),
            "payload_json": row.get("payload_json") or {},
            "profile_key": row.get("profile_key"),
            "template_key": row.get("template_key"),
        }
        for row in rows
    ]


def list_mail_delivery_events(
    conn,
    *,
    tenant_id: str,
    job_id: str,
) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.event_type, e.provider_message_id, e.event_payload, e.occurred_at
            FROM mail_delivery_events e
            JOIN outbound_mail_jobs j ON j.id = e.outbound_mail_job_id
            WHERE j.tenant_id = %s
              AND e.outbound_mail_job_id = %s
            ORDER BY e.occurred_at DESC
            """,
            (tenant_id, job_id),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or ""),
            "event_type": row.get("event_type"),
            "provider_message_id": row.get("provider_message_id"),
            "event_payload": row.get("event_payload") or {},
            "occurred_at": row.get("occurred_at"),
        }
        for row in rows
    ]


def _fetch_approval_document_id_for_legacy_request(conn, *, tenant_id: str, legacy_source_id: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM approval_documents
            WHERE tenant_id = %s
              AND legacy_source_type = 'employment_certificate_request'
              AND legacy_source_id = %s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant_id, legacy_source_id),
        )
        row = cur.fetchone()
    return str((row or {}).get("id") or "").strip() or None


def _resolve_employee_email(conn, *, tenant_id: str, employee_id: str) -> str:
    candidate_columns = ("email", "company_email", "work_email", "employee_email")
    for column in candidate_columns:
        if not table_column_exists(conn, "employees", column):
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {column} AS email_value
                FROM employees
                WHERE tenant_id = %s
                  AND id = %s
                LIMIT 1
                """,
                (tenant_id, employee_id),
            )
            row = cur.fetchone()
        email = str((row or {}).get("email_value") or "").strip()
        if email:
            return email
    return ""


def _fetch_legacy_document_request_row(conn, *, tenant_id: str, legacy_request_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dr.id,
                   dr.tenant_id,
                   dr.company_id,
                   dr.employee_id,
                   dr.document_type,
                   dr.status,
                   dr.purpose_code,
                   dr.purpose_text,
                   dr.requested_at,
                   dr.approved_at,
                   dr.rejection_reason,
                   dr.issue_number,
                   dr.file_path,
                   dr.file_url,
                   dr.file_name,
                   dr.file_mime_type,
                   dr.file_bytes,
                   dr.generated_at,
                   dr.generation_error,
                   dr.mail_error,
                   dr.mail_company_sent_at,
                   dr.mail_employee_sent_at,
                   dr.template_id,
                   dr.template_version,
                   dr.template_file_path,
                   e.full_name AS employee_name,
                   e.employee_code,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   COALESCE(tp.email, '') AS company_email,
                   t.tenant_code
            FROM document_requests dr
            LEFT JOIN employees e ON e.id = dr.employee_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(dr.company_id, e.company_id, s.company_id)
            LEFT JOIN tenants t ON t.id = dr.tenant_id
            LEFT JOIN tenant_profiles tp ON tp.tenant_id = dr.tenant_id
            WHERE dr.tenant_id = %s
              AND dr.id = %s
              AND dr.document_type = 'employment_certificate'
            LIMIT 1
            """,
            (tenant_id, legacy_request_id),
        )
        return cur.fetchone()


def _ensure_certificate_attachment_object(conn, *, row: dict[str, Any]) -> str | None:
    has_inline_bytes = bool(row.get("file_bytes"))
    has_external_ref = bool(str(row.get("file_path") or "").strip() or str(row.get("file_url") or "").strip())
    if not has_inline_bytes and not has_external_ref:
        return None

    tenant_id = str(row.get("tenant_id") or "").strip()
    request_id = str(row.get("id") or "").strip()
    if not tenant_id or not request_id:
        return None

    resource_type = "legacy_employment_certificate_pdf"
    file_name = str(row.get("file_name") or f"employment_certificate_{request_id}.pdf").strip()
    mime_type = str(row.get("file_mime_type") or "application/pdf").strip() or "application/pdf"
    payload_bytes = row.get("file_bytes")
    if isinstance(payload_bytes, memoryview):
        byte_size = len(payload_bytes.tobytes())
    elif isinstance(payload_bytes, bytes):
        byte_size = len(payload_bytes)
    else:
        byte_size = len(bytes(payload_bytes or b"")) if payload_bytes else 0
    metadata = {
        "legacy_table": "document_requests",
        "legacy_document_type": row.get("document_type"),
        "issue_number": row.get("issue_number"),
        "template_version": row.get("template_version"),
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM groupware_attachment_objects
            WHERE tenant_id = %s
              AND module_key = 'certificates'
              AND resource_type = %s
              AND resource_id = %s
            LIMIT 1
            """,
            (tenant_id, resource_type, request_id),
        )
        existing = cur.fetchone()
        if existing:
            cur.execute(
                """
                UPDATE groupware_attachment_objects
                SET storage_backend = %s,
                    storage_key = %s,
                    blob_url = %s,
                    file_name = %s,
                    file_ext = '.pdf',
                    mime_type = %s,
                    byte_size = %s,
                    metadata_json = %s::jsonb,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                RETURNING id
                """,
                (
                    "database" if has_inline_bytes else "legacy_reference",
                    str(row.get("file_path") or "").strip() or f"document_requests/{request_id}/file_bytes",
                    str(row.get("file_url") or "").strip() or None,
                    file_name,
                    mime_type,
                    byte_size,
                    _json_dumps(metadata),
                    existing["id"],
                ),
            )
            updated = cur.fetchone() or existing
            return str(updated.get("id") or existing.get("id") or "")

        cur.execute(
            """
            INSERT INTO groupware_attachment_objects (
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
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (
                %s, 'certificates', %s, %s, %s, %s, %s, %s, '.pdf', %s, %s, %s::jsonb,
                timezone('utc', now()), timezone('utc', now())
            )
            RETURNING id
            """,
            (
                tenant_id,
                resource_type,
                request_id,
                "database" if has_inline_bytes else "legacy_reference",
                str(row.get("file_path") or "").strip() or f"document_requests/{request_id}/file_bytes",
                str(row.get("file_url") or "").strip() or None,
                file_name,
                mime_type,
                byte_size,
                _json_dumps(metadata),
            ),
        )
        inserted = cur.fetchone() or {}
    return str(inserted.get("id") or "") or None


def sync_legacy_employment_certificate_request(
    conn,
    *,
    tenant_id: str,
    legacy_request_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, Any] | None:
    ensure_certificate_mail_foundation(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    row = _fetch_legacy_document_request_row(conn, tenant_id=tenant_id, legacy_request_id=legacy_request_id)
    if not row:
        return None

    certificate_type = _resolve_certificate_type_row(conn, tenant_id=tenant_id, type_key=EMPLOYMENT_CERTIFICATE_TYPE_KEY)
    if not certificate_type:
        return None

    approval_document_id = _fetch_approval_document_id_for_legacy_request(
        conn,
        tenant_id=tenant_id,
        legacy_source_id=str(row.get("id") or ""),
    )
    issued_attachment_object_id = _ensure_certificate_attachment_object(conn, row=row)
    normalized_status = _normalize_certificate_status(row.get("status"))
    existing_request_id: str | None = None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM certificate_requests
            WHERE tenant_id = %s
              AND legacy_source_type = 'employment_certificate_request'
              AND legacy_source_id = %s
            LIMIT 1
            """,
            (tenant_id, str(row.get("id") or "")),
        )
        existing = cur.fetchone() or {}
        existing_request_id = str(existing.get("id") or "").strip() or None
        if existing_request_id:
            cur.execute(
                """
                UPDATE certificate_requests
                SET certificate_type_id = %s,
                    employee_id = %s,
                    approval_document_id = %s,
                    purpose_code = %s,
                    purpose_text = %s,
                    status = %s,
                    issued_attachment_object_id = %s,
                    requested_at = %s,
                    issued_at = %s,
                    issue_number = %s,
                    updated_at = timezone('utc', now())
                WHERE id = %s
                RETURNING id, status, issue_number, requested_at, issued_at, approval_document_id
                """,
                (
                    certificate_type.get("id"),
                    row.get("employee_id"),
                    approval_document_id,
                    row.get("purpose_code"),
                    row.get("purpose_text"),
                    normalized_status,
                    issued_attachment_object_id,
                    row.get("requested_at") or _utcnow(),
                    row.get("generated_at") or row.get("approved_at"),
                    row.get("issue_number"),
                    existing_request_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO certificate_requests (
                    tenant_id,
                    certificate_type_id,
                    employee_id,
                    requester_user_id,
                    approval_document_id,
                    purpose_code,
                    purpose_text,
                    status,
                    issued_attachment_object_id,
                    requested_at,
                    issued_at,
                    issue_number,
                    legacy_source_type,
                    legacy_source_id,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s, %s, %s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, 'employment_certificate_request', %s,
                    timezone('utc', now()), timezone('utc', now())
                )
                RETURNING id, status, issue_number, requested_at, issued_at, approval_document_id
                """,
                (
                    tenant_id,
                    certificate_type.get("id"),
                    row.get("employee_id"),
                    approval_document_id,
                    row.get("purpose_code"),
                    row.get("purpose_text"),
                    normalized_status,
                    issued_attachment_object_id,
                    row.get("requested_at") or _utcnow(),
                    row.get("generated_at") or row.get("approved_at"),
                    row.get("issue_number"),
                    str(row.get("id") or ""),
                ),
            )
        synced = cur.fetchone() or {}

    _run_noncritical_db_step(
        conn,
        step_name=f"certificate_request_synced_audit:{tenant_id}:{legacy_request_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="certificates",
            event_type="certificate_request_synced",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            resource_type="certificate_request",
            resource_id=str(synced.get("id") or ""),
            payload={
                "legacy_source_type": "employment_certificate_request",
                "legacy_source_id": str(row.get("id") or ""),
                "status": normalized_status,
                "issue_number": row.get("issue_number"),
            },
        ),
    )

    return {
        "id": str(synced.get("id") or ""),
        "status": synced.get("status") or normalized_status,
        "issue_number": synced.get("issue_number"),
        "requested_at": synced.get("requested_at"),
        "issued_at": synced.get("issued_at"),
        "approval_document_id": str(synced.get("approval_document_id") or approval_document_id or ""),
    }


def sync_legacy_employment_certificate_issue_job(
    conn,
    *,
    tenant_id: str,
    legacy_request_id: str,
    job_state: str | None = None,
    last_error: str | None = None,
    payload_extra: dict[str, Any] | None = None,
    increment_attempts: bool = False,
) -> dict[str, Any] | None:
    request_row = sync_legacy_employment_certificate_request(
        conn,
        tenant_id=tenant_id,
        legacy_request_id=legacy_request_id,
    )
    if not request_row:
        return None

    desired_state = str(job_state or "").strip().lower() or _issue_job_state_from_certificate_status(request_row.get("status"))
    if not desired_state:
        return None

    payload = {
        "legacy_source_type": "employment_certificate_request",
        "legacy_source_id": legacy_request_id,
        "certificate_status": request_row.get("status"),
        "issue_number": request_row.get("issue_number"),
    }
    if payload_extra:
        payload.update(payload_extra)

    last_error_value = _truncate_error(last_error)
    completed_at = _utcnow() if desired_state in {"completed", "failed", "cancelled"} else None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, attempts
            FROM certificate_issue_jobs
            WHERE certificate_request_id = %s
            LIMIT 1
            """,
            (request_row["id"],),
        )
        existing = cur.fetchone() or {}
        existing_job_id = str(existing.get("id") or "").strip() or None
        if existing_job_id:
            next_attempts = int(existing.get("attempts") or 0) + 1 if increment_attempts else max(int(existing.get("attempts") or 0), 0)
            cur.execute(
                """
                UPDATE certificate_issue_jobs
                SET job_state = %s,
                    attempts = %s,
                    last_error = %s,
                    payload_json = %s::jsonb,
                    locked_at = CASE
                        WHEN %s = 'processing' THEN timezone('utc', now())
                        ELSE locked_at
                    END,
                    completed_at = %s
                WHERE id = %s
                RETURNING id, certificate_request_id, job_state, attempts, last_error, completed_at
                """,
                (
                    desired_state,
                    next_attempts,
                    last_error_value,
                    _json_dumps(payload),
                    desired_state,
                    completed_at,
                    existing_job_id,
                ),
            )
        else:
            cur.execute(
                """
                INSERT INTO certificate_issue_jobs (
                    tenant_id,
                    certificate_request_id,
                    job_state,
                    attempts,
                    last_error,
                    payload_json,
                    locked_at,
                    completed_at,
                    created_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s::jsonb,
                    CASE WHEN %s = 'processing' THEN timezone('utc', now()) ELSE NULL END,
                    %s,
                    timezone('utc', now())
                )
                RETURNING id, certificate_request_id, job_state, attempts, last_error, completed_at
                """,
                (
                    tenant_id,
                    request_row["id"],
                    desired_state,
                    1 if increment_attempts else 0,
                    last_error_value,
                    _json_dumps(payload),
                    desired_state,
                    completed_at,
                ),
            )
        job_row = cur.fetchone() or {}
    return {
        "id": str(job_row.get("id") or ""),
        "certificate_request_id": str(job_row.get("certificate_request_id") or request_row["id"]),
        "job_state": job_row.get("job_state") or desired_state,
        "attempts": int(job_row.get("attempts") or 0),
        "last_error": job_row.get("last_error"),
        "completed_at": job_row.get("completed_at"),
    }


def record_certificate_mail_delivery(
    conn,
    *,
    tenant_id: str,
    legacy_request_id: str,
    recipient_role: str,
    recipient_email: str,
    subject: str,
    body_text: str,
    attachment_name: str,
    sent: bool,
    error: str | None = None,
    sent_at: datetime | None = None,
) -> dict[str, Any] | None:
    request_row = sync_legacy_employment_certificate_request(
        conn,
        tenant_id=tenant_id,
        legacy_request_id=legacy_request_id,
    )
    if not request_row:
        return None

    foundation = ensure_certificate_mail_foundation(conn, tenant_id=tenant_id)
    template_key = (
        "employment_certificate_issued_company"
        if str(recipient_role or "").strip().lower() == "company"
        else "employment_certificate_issued_employee"
    )
    template_row = _fetch_mail_template_by_key(conn, tenant_id=tenant_id, template_key=template_key)
    profile_row = _fetch_mail_profile_by_key(conn, tenant_id=tenant_id, profile_key=DEFAULT_MAIL_PROFILE_KEY)
    account_row = _fetch_mail_account_by_key(conn, tenant_id=tenant_id, account_key=DEFAULT_MAIL_ACCOUNT_KEY)
    state = "sent" if sent else "failed"
    occurred_at = sent_at or _utcnow()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO outbound_mail_jobs (
                tenant_id,
                mail_account_id,
                sender_profile_id,
                template_id,
                source_type,
                source_id,
                recipient_email,
                subject,
                body_text,
                state,
                attempts,
                sent_at,
                last_error,
                payload_json,
                created_at
            )
            VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s, %s::jsonb, timezone('utc', now())
            )
            RETURNING id, state, sent_at, last_error
            """,
            (
                tenant_id,
                str((account_row or {}).get("id") or foundation["mail_account"]["id"] or "") or None,
                str((profile_row or {}).get("id") or foundation["mail_profile"]["id"] or "") or None,
                str((template_row or {}).get("id") or "") or None,
                MAIL_JOB_SOURCE_TYPE,
                f"{legacy_request_id}:{recipient_role}",
                recipient_email,
                subject,
                body_text,
                state,
                occurred_at if sent else None,
                _truncate_error(error),
                _json_dumps(
                    {
                        "certificate_request_id": request_row["id"],
                        "legacy_request_id": legacy_request_id,
                        "recipient_role": recipient_role,
                        "attachment_name": attachment_name,
                    }
                ),
            ),
        )
        job_row = cur.fetchone() or {}
        cur.execute(
            """
            INSERT INTO mail_delivery_events (
                tenant_id,
                outbound_mail_job_id,
                event_type,
                provider_message_id,
                event_payload,
                occurred_at
            )
            VALUES (%s, %s, %s, NULL, %s::jsonb, %s)
            RETURNING id
            """,
            (
                tenant_id,
                job_row.get("id"),
                "delivered" if sent else "failed",
                _json_dumps(
                    {
                        "recipient_role": recipient_role,
                        "recipient_email": recipient_email,
                        "error": _truncate_error(error),
                    }
                ),
                occurred_at,
            ),
        )
        event_row = cur.fetchone() or {}

    return {
        "job_id": str(job_row.get("id") or ""),
        "event_id": str(event_row.get("id") or ""),
        "state": job_row.get("state") or state,
        "sent_at": job_row.get("sent_at"),
        "last_error": job_row.get("last_error"),
    }


def _fetch_legacy_document_request_ids_for_backfill(
    conn,
    *,
    tenant_id: str,
    limit: int,
    status_filter: str | None = None,
) -> list[str]:
    clauses = ["tenant_id = %s", "document_type = 'employment_certificate'"]
    params: list[Any] = [tenant_id]
    normalized_status = str(status_filter or "").strip().lower()
    if normalized_status and normalized_status != "all":
        clauses.append("lower(status) = %s")
        params.append(normalized_status)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT id
            FROM document_requests
            WHERE {' AND '.join(clauses)}
            ORDER BY requested_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params + [max(int(limit or 100), 1)]),
        )
        rows = cur.fetchall() or []
    return [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]


def backfill_legacy_employment_certificate_requests(
    conn,
    *,
    tenant_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
    limit: int = 200,
    status_filter: str | None = None,
) -> dict[str, Any]:
    ensure_certificate_mail_foundation(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    legacy_ids = _fetch_legacy_document_request_ids_for_backfill(
        conn,
        tenant_id=tenant_id,
        limit=limit,
        status_filter=status_filter,
    )
    synced_requests = 0
    synced_jobs = 0
    skipped_ids: list[str] = []
    failed_ids: list[dict[str, str]] = []
    for legacy_id in legacy_ids:
        request_errors: list[str] = []
        request_row = _run_noncritical_db_step(
            conn,
            step_name=f"backfill_request_sync:{tenant_id}:{legacy_id}",
            callback=lambda: sync_legacy_employment_certificate_request(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=legacy_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
            ),
            fallback=None,
            error_collector=request_errors,
        )
        if request_errors:
            failed_ids.append({"legacy_request_id": legacy_id, "error": request_errors[0]})
            continue
        if not request_row:
            skipped_ids.append(legacy_id)
            continue
        synced_requests += 1

        issue_job_errors: list[str] = []
        issue_job = _run_noncritical_db_step(
            conn,
            step_name=f"backfill_issue_job_sync:{tenant_id}:{legacy_id}",
            callback=lambda: sync_legacy_employment_certificate_issue_job(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=legacy_id,
            ),
            fallback=None,
            error_collector=issue_job_errors,
        )
        if issue_job_errors:
            failed_ids.append({"legacy_request_id": legacy_id, "error": issue_job_errors[0]})
            continue
        if issue_job:
            synced_jobs += 1

    _run_noncritical_db_step(
        conn,
        step_name=f"legacy_backfill_audit:{tenant_id}:{len(legacy_ids)}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="certificates",
            action_type="legacy_backfill_requested",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="certificate_requests",
            target_id=None,
            detail={
                "requested_count": len(legacy_ids),
                "synced_requests": synced_requests,
                "synced_jobs": synced_jobs,
                "skipped_count": len(skipped_ids),
                "failed_count": len(failed_ids),
                "status_filter": status_filter or "all",
            },
        ),
    )
    return {
        "requested_count": len(legacy_ids),
        "synced_requests": synced_requests,
        "synced_jobs": synced_jobs,
        "skipped_ids": skipped_ids,
        "failed": failed_ids,
    }


def retry_certificate_issue_job(
    conn,
    *,
    tenant_id: str,
    issue_job_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT job.id,
                   job.certificate_request_id,
                   job.job_state,
                   cr.legacy_source_type,
                   cr.legacy_source_id,
                   cr.status AS certificate_status
            FROM certificate_issue_jobs job
            JOIN certificate_requests cr ON cr.id = job.certificate_request_id
            WHERE job.tenant_id = %s
              AND job.id = %s
            LIMIT 1
            """,
            (tenant_id, issue_job_id),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("CERTIFICATE_ISSUE_JOB_NOT_FOUND")

    legacy_source_type = str(row.get("legacy_source_type") or "").strip().lower()
    legacy_source_id = str(row.get("legacy_source_id") or "").strip()
    certificate_request_id = str(row.get("certificate_request_id") or "").strip()
    if legacy_source_type == "employment_certificate_request" and legacy_source_id:
        retried = sync_legacy_employment_certificate_issue_job(
            conn,
            tenant_id=tenant_id,
            legacy_request_id=legacy_source_id,
            job_state="queued",
            last_error=None,
            payload_extra={"stage": "retry_requested"},
            increment_attempts=False,
        )
    elif certificate_request_id:
        retried = upsert_certificate_issue_job(
            conn,
            tenant_id=tenant_id,
            certificate_request_id=certificate_request_id,
            job_state="queued",
            last_error=None,
            payload_extra={"stage": "retry_requested"},
            increment_attempts=False,
        )
    else:
        raise ValueError("CERTIFICATE_REQUEST_NOT_FOUND")
    _run_noncritical_db_step(
        conn,
        step_name=f"issue_job_retried_audit:{tenant_id}:{issue_job_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="certificates",
            action_type="issue_job_retried",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="certificate_issue_job",
            target_id=issue_job_id,
            detail={"legacy_source_id": legacy_source_id, "certificate_request_id": certificate_request_id},
        ),
    )
    return {
        "issue_job_id": issue_job_id,
        "legacy_source_id": legacy_source_id,
        "legacy_source_type": legacy_source_type or None,
        "certificate_request_id": certificate_request_id,
        "job_state": (retried or {}).get("job_state") or "queued",
        "certificate_status": row.get("certificate_status"),
    }


def retry_outbound_mail_job(
    conn,
    *,
    tenant_id: str,
    job_id: str,
    actor_user_id: str | None = None,
    actor_role: str | None = None,
) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE outbound_mail_jobs
            SET state = 'queued',
                sent_at = NULL,
                last_error = NULL,
                scheduled_for = timezone('utc', now())
            WHERE tenant_id = %s
              AND id = %s
            RETURNING id, source_type, source_id, recipient_email, state, attempts
            """,
            (tenant_id, job_id),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("OUTBOUND_MAIL_JOB_NOT_FOUND")
        cur.execute(
            """
            INSERT INTO mail_delivery_events (
                tenant_id,
                outbound_mail_job_id,
                event_type,
                provider_message_id,
                event_payload,
                occurred_at
            )
            VALUES (%s, %s, 'retry_requested', NULL, %s::jsonb, timezone('utc', now()))
            RETURNING id, occurred_at
            """,
            (
                tenant_id,
                job_id,
                _json_dumps(
                    {
                        "source_type": row.get("source_type"),
                        "source_id": row.get("source_id"),
                        "recipient_email": row.get("recipient_email"),
                    }
                ),
            ),
        )
        event = cur.fetchone() or {}
    _run_noncritical_db_step(
        conn,
        step_name=f"outbound_mail_retried_audit:{tenant_id}:{job_id}",
        callback=lambda: GroupwareAuditService(conn).write_event(
            tenant_id=tenant_id,
            module_key="mail",
            action_type="outbound_mail_retried",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            target_type="outbound_mail_job",
            target_id=job_id,
            detail={"source_type": row.get("source_type"), "source_id": row.get("source_id")},
        ),
    )
    return {
        "job_id": str(row.get("id") or ""),
        "state": row.get("state") or "queued",
        "recipient_email": row.get("recipient_email"),
        "source_type": row.get("source_type"),
        "source_id": row.get("source_id"),
        "event_id": str(event.get("id") or ""),
        "occurred_at": event.get("occurred_at"),
    }
