from __future__ import annotations

import base64
import json
import logging
from io import BytesIO
from pathlib import Path
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
import requests

from ...db import get_connection
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.approval_engine import (
    create_certificate_request_approval_adapter,
    ensure_default_approval_line_rules,
    sync_legacy_approval_status,
)
from ...services.certificates_mail import (
    record_certificate_mail_delivery,
    sync_legacy_employment_certificate_issue_job,
    sync_legacy_employment_certificate_request,
)
from ...services.employment_certificate import (
    build_issue_number,
    build_purpose_label,
    generate_employment_certificate_pdf,
    issue_employment_certificate_pdf_from_docx,
    send_certificate_mail,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, ROLE_EMPLOYEE, normalize_role, normalize_user_role
from ...utils.schema_introspection import table_column_exists
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(tags=["hr-documents"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)

DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE = "employment_certificate"
DOCUMENT_TYPE_CAREER_CERTIFICATE = "career_certificate"
DOCUMENT_TYPE_RETIREMENT_CERTIFICATE = "retirement_certificate"
DOCUMENT_TYPE_LEAVE_OF_ABSENCE_CERTIFICATE = "leave_of_absence_certificate"
DOCUMENT_TYPE_RESIGNATION_FORM = "resignation_form"
DAILY_REQUEST_LIMIT = 4
TZ_KST = timezone(timedelta(hours=9))
PURPOSE_CODES = {"BANK", "GOV", "CARD", "OTHER"}
ALLOWED_TEMPLATE_DOCUMENT_TYPES = {
    DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
    DOCUMENT_TYPE_CAREER_CERTIFICATE,
    DOCUMENT_TYPE_RETIREMENT_CERTIFICATE,
    DOCUMENT_TYPE_LEAVE_OF_ABSENCE_CERTIFICATE,
    DOCUMENT_TYPE_RESIGNATION_FORM,
}
ALLOWED_TEMPLATE_EXTENSIONS = {".docx"}
MAX_TEMPLATE_UPLOAD_BYTES = 2 * 1024 * 1024
APPROVAL_POLICY_RULE_FORM_KEY_PREFIX = "certificate_request:"
APPROVAL_POLICY_SUPPORTED_DOCUMENT_TYPES = {
    DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
    DOCUMENT_TYPE_CAREER_CERTIFICATE,
    DOCUMENT_TYPE_RETIREMENT_CERTIFICATE,
    DOCUMENT_TYPE_LEAVE_OF_ABSENCE_CERTIFICATE,
    "resignation_form",
}
APPROVAL_POLICY_SITE_ROLE_OPTIONS = (
    {"value": "supervisor", "label": "Supervisor"},
)
APPROVAL_POLICY_ALLOWED_USER_ROLES = ("officer", "vice_supervisor", "supervisor", "hq_admin", "developer")


class EmploymentCertificateRequestCreate(BaseModel):
    purpose_code: str = Field(min_length=1, max_length=16)
    purpose_text: str | None = Field(default=None, max_length=120)

    @field_validator("purpose_code", mode="before")
    @classmethod
    def _normalize_purpose_code(cls, value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in PURPOSE_CODES:
            raise ValueError("purpose_code must be one of BANK/GOV/CARD/OTHER")
        return normalized

    @field_validator("purpose_text", mode="before")
    @classmethod
    def _normalize_purpose_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class EmploymentCertificateRejectRequest(BaseModel):
    rejection_reason: str = Field(min_length=2, max_length=400)

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def _normalize_reason(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("rejection_reason is required")
        return normalized


class ResignationRequestCreate(BaseModel):
    resignation_type: str = Field(min_length=1, max_length=32)
    expected_last_working_date: str = Field(min_length=8, max_length=32)
    resignation_reason: str = Field(min_length=5, max_length=400)
    handover_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("resignation_type", mode="before")
    @classmethod
    def _normalize_resignation_type(cls, value: str | None) -> str:
        normalized = str(value or "").strip().upper()
        if normalized not in {"PERSONAL", "CONTRACT_END", "CAREER", "HEALTH", "OTHER"}:
            raise ValueError("resignation_type invalid")
        return normalized

    @field_validator("expected_last_working_date", mode="before")
    @classmethod
    def _normalize_expected_last_working_date(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
            raise ValueError("expected_last_working_date invalid")
        return normalized

    @field_validator("resignation_reason", mode="before")
    @classmethod
    def _normalize_resignation_reason(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if len(normalized) < 5:
            raise ValueError("resignation_reason too_short")
        return normalized

    @field_validator("handover_notes", mode="before")
    @classmethod
    def _normalize_handover_notes(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None


class DocumentApprovalPolicyStepIn(BaseModel):
    stage_order: int | None = Field(default=None, ge=1, le=7)
    step_kind: str = Field(default="site_supervisor", min_length=1, max_length=32)
    label: str = Field(default="", max_length=120)
    site_role: str = Field(default="supervisor", max_length=32)
    explicit_user_id: str | None = Field(default=None, max_length=64)
    member_user_ids: list[str] = Field(default_factory=list)
    approval_group_id: str | None = Field(default=None, max_length=64)
    approval_rank_id: str | None = Field(default=None, max_length=64)
    allow_delegate: bool = False
    is_required: bool = True

    @field_validator("step_kind", mode="before")
    @classmethod
    def _normalize_step_kind(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in {"site_supervisor", "explicit_user", "rank"}:
            raise ValueError("step_kind must be site_supervisor/explicit_user/rank")
        return normalized or "site_supervisor"

    @field_validator("site_role", mode="before")
    @classmethod
    def _normalize_site_role(cls, value: str | None) -> str:
        normalized = normalize_user_role(value)
        if normalized not in {"supervisor", "vice_supervisor", "hq_admin", "developer"}:
            return "supervisor"
        return normalized

    @field_validator("explicit_user_id", "approval_group_id", "approval_rank_id", mode="before")
    @classmethod
    def _normalize_optional_id(cls, value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @field_validator("member_user_ids", mode="before")
    @classmethod
    def _normalize_member_user_ids(cls, value) -> list[str]:
        if value is None:
            return []
        values = value if isinstance(value, list) else [value]
        normalized: list[str] = []
        for item in values:
            current = str(item or "").strip()
            if current and current not in normalized:
                normalized.append(current)
        return normalized

    @field_validator("label", mode="before")
    @classmethod
    def _normalize_label(cls, value: str | None) -> str:
        return str(value or "").strip()


class DocumentApprovalPolicyUpdateRequest(BaseModel):
    document_type: str = Field(min_length=1, max_length=64)
    items: list[DocumentApprovalPolicyStepIn] = Field(default_factory=list)

    @field_validator("document_type", mode="before")
    @classmethod
    def _normalize_document_type(cls, value: str | None) -> str:
        return str(value or "").strip().lower()


def _raise_api_error(status_code: int, code: str, message: str, *, fields: dict[str, str] | None = None) -> None:
    detail: dict[str, Any] = {"error": code, "message": message}
    if fields:
        detail["fields"] = fields
    raise HTTPException(status_code=status_code, detail=detail)


def _run_noncritical_db_step(
    conn,
    *,
    step_name: str,
    callback,
    fallback=None,
):
    savepoint = f"hr_documents_sp_{uuid.uuid4().hex}"
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {savepoint}")
    try:
        result = callback()
    except Exception:
        logger.exception("[HR][DOC] non-critical db step failed step=%s", step_name)
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
            cur.execute(f"RELEASE SAVEPOINT {savepoint}")
        return fallback
    with conn.cursor() as cur:
        cur.execute(f"RELEASE SAVEPOINT {savepoint}")
    return result


def _ensure_admin_role(user: dict) -> None:
    actor_role = normalize_role(user.get("role"))
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "접근 권한이 없습니다.")


def _ensure_template_manager_role(user: dict) -> None:
    actor_role = normalize_role(user.get("role"))
    if actor_role != ROLE_DEV:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "템플릿 관리 권한이 없습니다.")


def _ensure_employee_role(user: dict) -> str:
    actor_role = normalize_role(user.get("role"))
    if actor_role == ROLE_DEV:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "직원 계정 연결이 필요합니다.")
    employee_id = str(user.get("employee_id") or "").strip()
    if not employee_id:
        _raise_api_error(status.HTTP_403_FORBIDDEN, "EMPLOYEE_CONTEXT_REQUIRED", "직원 계정 연결이 필요합니다.")
    return employee_id


def _parse_uuid(value: str, *, field_name: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value or "").strip())
    except Exception as exc:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_INPUT",
            "입력값을 확인해주세요.",
            fields={field_name: "invalid"},
        )
        raise exc


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return ""
    return "" 


def _parse_resignation_request_payload(row: dict[str, Any] | None) -> dict[str, Any]:
    payload_raw = str((row or {}).get("purpose_text") or "").strip()
    payload: dict[str, Any] = {}
    if payload_raw:
        try:
            parsed = json.loads(payload_raw)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"resignation_reason": payload_raw}
        except Exception:
            payload = {"resignation_reason": payload_raw}
    return {
        "resignation_type": str((row or {}).get("purpose_code") or payload.get("resignation_type") or "PERSONAL").strip().upper() or "PERSONAL",
        "expected_last_working_date": str(payload.get("expected_last_working_date") or "").strip() or None,
        "resignation_reason": str(payload.get("resignation_reason") or "").strip() or "",
        "handover_notes": str(payload.get("handover_notes") or "").strip() or None,
    }


def _serialize_resignation_request_row(row: dict[str, Any] | None) -> dict[str, Any]:
    detail = _parse_resignation_request_payload(row)
    return {
        "id": str((row or {}).get("id") or "").strip(),
        "status": str((row or {}).get("status") or "").strip().lower() or "requested",
        "requested_at": (row or {}).get("requested_at"),
        "approved_at": (row or {}).get("approved_at"),
        "rejection_reason": (row or {}).get("rejection_reason"),
        "employee_code": (row or {}).get("employee_code"),
        "employee_name": (row or {}).get("employee_name"),
        "company_name": (row or {}).get("company_name"),
        "org": (row or {}).get("org_name"),
        "resignation_type": detail["resignation_type"],
        "expected_last_working_date": detail["expected_last_working_date"],
        "resignation_reason": detail["resignation_reason"],
        "handover_notes": detail["handover_notes"],
        "approval_progress": (row or {}).get("approval_progress") or {},
        "can_delegate": bool((row or {}).get("can_delegate")),
    }


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _mask_resident_registration(value: str | None) -> str:
    raw = re.sub(r"[^0-9]", "", str(value or ""))
    if len(raw) < 7:
        return ""
    front = raw[:6]
    back_first = raw[6:7]
    return f"{front}-{back_first}******"


def _resolve_masked_resident_no(conn, *, tenant_id: str, employee_id: str) -> str:
    candidate_columns = (
        "resident_no",
        "resident_number",
        "resident_registration_no",
        "rrn",
        "ssn",
    )
    for column in candidate_columns:
        if not table_column_exists(conn, "employees", column):
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {column} AS resident_value
                FROM employees
                WHERE tenant_id = %s
                  AND id = %s
                LIMIT 1
                """,
                (tenant_id, employee_id),
            )
            row = cur.fetchone()
        masked = _mask_resident_registration((row or {}).get("resident_value"))
        if masked:
            return masked
    return ""


def _resolve_termination_date(
    conn,
    *,
    tenant_id: str,
    employee_id: str,
    fallback_value: Any = None,
) -> str:
    fallback = _format_date(fallback_value)
    candidate_columns = (
        "leave_date",
        "termination_date",
        "employment_end_date",
        "retire_date",
        "retired_at",
        "end_date",
    )
    for column in candidate_columns:
        if not table_column_exists(conn, "employees", column):
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {column} AS termination_value
                FROM employees
                WHERE tenant_id = %s
                  AND id = %s
                LIMIT 1
                """,
                (tenant_id, employee_id),
            )
            row = cur.fetchone()
        resolved = _format_date((row or {}).get("termination_value"))
        if resolved:
            return resolved
    return fallback


def _validate_purpose(purpose_code: str, purpose_text: str | None) -> str | None:
    normalized_code = str(purpose_code or "").strip().upper()
    if normalized_code not in PURPOSE_CODES:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"purpose_code": "required"},
        )
    if normalized_code == "OTHER":
        text = str(purpose_text or "").strip()
        if len(text) < 2:
            _raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "입력값을 확인해주세요.",
                fields={"purpose_text": "required"},
            )
        if len(text) > 50:
            _raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "입력값을 확인해주세요.",
                fields={"purpose_text": "max_50"},
            )
        return text
    return None


def _count_today_employee_requests(conn, *, tenant_id: str, employee_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM document_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND document_type = %s
              AND status IN ('requested', 'generating', 'issued')
              AND (requested_at AT TIME ZONE 'Asia/Seoul')::date = (timezone('Asia/Seoul', now()))::date
            """,
            (tenant_id, employee_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
        )
        row = cur.fetchone()
    return int(row.get("cnt") or 0) if row else 0


def _get_employee_scope_row(conn, *, employee_id: str, tenant_id: str) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT e.id,
                   e.tenant_id,
                   COALESCE(e.company_id, s.company_id) AS company_id,
                   e.site_id,
                   e.full_name,
                   e.birth_date,
                   e.hire_date,
                   e.leave_date,
                   COALESCE(e.employment_status, 'active') AS employment_status,
                   e.loa_start_date,
                   e.loa_end_date,
                   e.address,
                   e.phone,
                   e.management_no_str,
                   COALESCE(e.soc_role, '') AS soc_role,
                   s.site_code,
                   s.site_name,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   COALESCE(c.company_code, '') AS company_code
            FROM employees e
            JOIN tenants t ON t.id = e.tenant_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(e.company_id, s.company_id)
            WHERE e.id = %s
              AND e.tenant_id = %s
            LIMIT 1
            """,
            (employee_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "EMPLOYEE_NOT_FOUND", "직원 정보를 찾을 수 없습니다.")
    return row


def _normalize_email(value: str | None) -> str:
    email = str(value or "").strip()
    if not email:
        return ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return ""
    return email


def _resolve_employee_email(conn, *, tenant_id: str, employee_id: str) -> str:
    candidate_columns = ["email", "personal_email"]
    for column in candidate_columns:
        if not table_column_exists(conn, "employees", column):
            continue
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT {column} AS email_value
                FROM employees
                WHERE id = %s
                  AND tenant_id = %s
                LIMIT 1
                """,
                (employee_id, tenant_id),
            )
            row = cur.fetchone()
        email = _normalize_email(row.get("email_value") if row else "")
        if email:
            return email

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT username
            FROM arls_users
            WHERE tenant_id = %s
              AND employee_id = %s
              AND is_active = TRUE
              AND COALESCE(is_deleted, FALSE) = FALSE
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT 1
            """,
            (tenant_id, employee_id),
        )
        row = cur.fetchone()
    return _normalize_email(str((row or {}).get("username") or ""))


def _load_seal_image_bytes(conn, *, tenant_id: str, seal_attachment_id: str | None) -> bytes | None:
    attachment_id = str(seal_attachment_id or "").strip()
    if not attachment_id:
        return None

    if attachment_id.startswith("data:image/"):
        try:
            _, payload = attachment_id.split(",", 1)
            return base64.b64decode(payload)
        except Exception:
            return None

    if re.match(r"^https?://", attachment_id, flags=re.IGNORECASE):
        try:
            response = requests.get(attachment_id, timeout=8)
            if response.status_code == 200:
                content_type = str(response.headers.get("content-type") or "").lower()
                if content_type.startswith("image/"):
                    return bytes(response.content or b"")
        except Exception:
            return None
        return None

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT file_bytes
            FROM tenant_profile_attachments
            WHERE tenant_id = %s
              AND id::text = %s
            LIMIT 1
            """,
            (tenant_id, attachment_id),
        )
        row = cur.fetchone()
    if not row:
        return None
    file_bytes = row.get("file_bytes")
    if isinstance(file_bytes, memoryview):
        return file_bytes.tobytes()
    if isinstance(file_bytes, bytes):
        return file_bytes
    return bytes(file_bytes or b"")


def _normalize_document_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in ALLOWED_TEMPLATE_DOCUMENT_TYPES:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"document_type": "invalid"},
        )
    return normalized


def _normalize_approval_policy_document_type(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized not in {
        DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
        DOCUMENT_TYPE_CAREER_CERTIFICATE,
        DOCUMENT_TYPE_RETIREMENT_CERTIFICATE,
        DOCUMENT_TYPE_LEAVE_OF_ABSENCE_CERTIFICATE,
        "resignation_form",
    }:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"document_type": "invalid"},
        )
    return normalized


def _resolve_document_approval_policy_state(document_type: str) -> dict[str, Any]:
    normalized_document_type = _normalize_approval_policy_document_type(document_type)
    if normalized_document_type not in APPROVAL_POLICY_SUPPORTED_DOCUMENT_TYPES:
        return {
            "document_type": normalized_document_type,
            "editable": False,
            "unsupported_reason": "현재 이 문서 타입은 문서 관리 화면에서 승인 절차를 편집할 수 없습니다.",
            "rule_form_key": None,
            "fallback_form_key": None,
        }
    return {
        "document_type": normalized_document_type,
        "editable": True,
        "unsupported_reason": "",
        "rule_form_key": f"{APPROVAL_POLICY_RULE_FORM_KEY_PREFIX}{normalized_document_type}",
        "fallback_form_key": "certificate_request",
    }


def _fetch_document_approval_policy_rows(
    conn,
    *,
    tenant_id: str,
    document_type: str,
) -> tuple[list[dict[str, Any]], str | None]:
    policy_state = _resolve_document_approval_policy_state(document_type)
    if not policy_state["editable"]:
        return [], None

    for form_key in (policy_state["rule_form_key"], policy_state["fallback_form_key"]):
        if not form_key:
            continue
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
                (tenant_id, form_key),
            )
            rows = [dict(row) for row in (cur.fetchall() or [])]
        if rows:
            return rows, form_key
    return [], policy_state["rule_form_key"]


def _serialize_document_approval_policy_row(row: dict[str, Any]) -> dict[str, Any]:
    conditions = row.get("conditions_json") if isinstance(row.get("conditions_json"), dict) else {}
    step_kind = str(conditions.get("step_kind") or "").strip().lower()
    if step_kind not in {"site_supervisor", "explicit_user", "rank"}:
        step_kind = "explicit_user" if str(row.get("approver_user_id") or "").strip() else "site_supervisor"
    approver_user_id = str(row.get("approver_user_id") or "").strip()
    member_user_ids = [
        str(value or "").strip()
        for value in (conditions.get("member_user_ids") or [])
        if str(value or "").strip()
    ]
    if step_kind == "explicit_user" and approver_user_id and approver_user_id not in member_user_ids:
        member_user_ids.insert(0, approver_user_id)
    raw_approver_role = str(conditions.get("site_role") or row.get("approver_role") or "").strip()
    approver_role = normalize_user_role(raw_approver_role) if raw_approver_role else "supervisor"
    return {
        "id": str(row.get("id") or "").strip(),
        "stage_order": int(row.get("rule_order") or 0) or None,
        "step_kind": step_kind,
        "label": str(row.get("rule_name") or "").strip(),
        "site_role": approver_role or "supervisor",
        "approval_group_id": str(conditions.get("approval_group_id") or "").strip(),
        "approval_rank_id": str(conditions.get("approval_rank_id") or "").strip(),
        "explicit_user_id": approver_user_id,
        "member_user_ids": member_user_ids,
        "allow_delegate": bool(conditions.get("allow_delegate")),
        "is_required": conditions.get("is_required") is not False,
    }


def _list_document_approval_policy_user_options(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT au.id,
                   au.username,
                   au.full_name,
                   au.role,
                   COALESCE(e.employee_code, '') AS employee_code
            FROM arls_users au
            LEFT JOIN employees e ON e.id = au.employee_id
            WHERE au.tenant_id = %s
              AND au.is_active = TRUE
              AND COALESCE(au.is_deleted, FALSE) = FALSE
              AND lower(au.role) = ANY(%s)
            ORDER BY au.created_at ASC, au.username ASC
            """,
            (tenant_id, list(APPROVAL_POLICY_ALLOWED_USER_ROLES)),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or "").strip(),
            "username": str(row.get("username") or "").strip(),
            "full_name": str(row.get("full_name") or "").strip(),
            "employee_code": str(row.get("employee_code") or "").strip(),
            "role": normalize_user_role(row.get("role")),
        }
        for row in rows
    ]


def _list_document_approval_policy_site_options(conn, *, tenant_id: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, site_code, site_name
            FROM sites
            WHERE tenant_id = %s
              AND COALESCE(is_active, TRUE) = TRUE
            ORDER BY created_at ASC, site_name ASC
            """,
            (tenant_id,),
        )
        rows = cur.fetchall() or []
    return [
        {
            "id": str(row.get("id") or "").strip(),
            "site_code": str(row.get("site_code") or "").strip(),
            "site_name": str(row.get("site_name") or "").strip(),
        }
        for row in rows
    ]


def _build_document_approval_policy_response(
    conn,
    *,
    tenant_id: str,
    document_type: str,
) -> dict[str, Any]:
    policy_state = _resolve_document_approval_policy_state(document_type)
    items: list[dict[str, Any]] = []
    matched_form_key = None
    if policy_state["editable"]:
        ensure_default_approval_line_rules(conn, tenant_id=tenant_id)
        rows, matched_form_key = _fetch_document_approval_policy_rows(
            conn,
            tenant_id=tenant_id,
            document_type=document_type,
        )
        items = [_serialize_document_approval_policy_row(row) for row in rows]
    return {
        "document_type": policy_state["document_type"],
        "editable": bool(policy_state["editable"]),
        "unsupported_reason": str(policy_state["unsupported_reason"] or "").strip(),
        "items": items,
        "resolved_form_key": matched_form_key,
        "uses_fallback_policy": bool(
            policy_state["editable"]
            and matched_form_key
            and matched_form_key == policy_state["fallback_form_key"]
        ),
        "user_options": _list_document_approval_policy_user_options(conn, tenant_id=tenant_id),
        "site_options": _list_document_approval_policy_site_options(conn, tenant_id=tenant_id),
        "group_options": [],
        "rank_options": [],
        "site_role_options": list(APPROVAL_POLICY_SITE_ROLE_OPTIONS),
    }


def _has_document_custom_approval_policy(
    conn,
    *,
    tenant_id: str,
    document_type: str,
) -> bool:
    policy_state = _resolve_document_approval_policy_state(document_type)
    if not policy_state["editable"]:
        return False
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1
            FROM approval_line_rules
            WHERE tenant_id = %s
              AND form_key = %s
              AND is_active = TRUE
            LIMIT 1
            """,
            (tenant_id, policy_state["rule_form_key"]),
        )
        row = cur.fetchone()
    return bool(row)


@router.get("/hr/documents/request-approval-guard")
def get_document_request_approval_guard(
    document_type: str = Query(default=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=False,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    normalized_document_type = _normalize_approval_policy_document_type(document_type)
    has_custom_policy = _has_document_custom_approval_policy(
        conn,
        tenant_id=tenant_id,
        document_type=normalized_document_type,
    )
    return {
        "document_type": normalized_document_type,
        "approval_required": True,
        "has_custom_policy": has_custom_policy,
        "uses_fallback_policy": not has_custom_policy,
        "warning_message": "현재 별도의 승인 단계가 없어 기본 승인단계로 진행됩니다. 필요할 경우 승인단계를 설정 해 주세요",
        "accept_label": "다음",
        "cancel_label": "취소",
    }


def _normalize_company_scope_id(raw_value: str | None) -> str | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except Exception:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"company_id": "invalid_uuid"},
        )
    return None


def _validate_company_scope(
    conn,
    *,
    tenant_id: str,
    company_id: str | None,
) -> str | None:
    normalized_company_id = _normalize_company_scope_id(company_id)
    if not normalized_company_id:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM companies
            WHERE id = %s
              AND tenant_id = %s
            LIMIT 1
            """,
            (normalized_company_id, tenant_id),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(
            status.HTTP_404_NOT_FOUND,
            "COMPANY_NOT_FOUND",
            "회사 정보를 찾을 수 없습니다.",
        )
    return normalized_company_id


def _fetch_document_template_for_issue(
    conn,
    *,
    tenant_id: str,
    company_id: str | None,
    document_type: str,
) -> tuple[dict[str, Any] | None, str]:
    normalized_company_id = _normalize_company_scope_id(company_id)
    with conn.cursor() as cur:
        if normalized_company_id:
            cur.execute(
                """
                SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                  AND company_id = %s
                  AND is_active = TRUE
                  AND lower(COALESCE(file_ext, '')) = '.docx'
                  AND file_bytes IS NOT NULL
                ORDER BY version DESC
                LIMIT 1
                """,
                (tenant_id, document_type, normalized_company_id),
            )
            company_scoped = cur.fetchone()
            if company_scoped:
                return company_scoped, "company_active"

        cur.execute(
            """
            SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
            FROM document_templates
            WHERE tenant_id = %s
              AND document_type = %s
              AND company_id IS NULL
              AND is_active = TRUE
              AND lower(COALESCE(file_ext, '')) = '.docx'
              AND file_bytes IS NOT NULL
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant_id, document_type),
        )
        global_active = cur.fetchone()
        if global_active:
            return global_active, "global_active"

        # Fallback: use latest globally active DOCX template across tenants.
        # This keeps issuance working when developer uploaded a single shared template
        # under a different tenant scope.
        cur.execute(
            """
            SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
            FROM document_templates
            WHERE document_type = %s
              AND company_id IS NULL
              AND is_active = TRUE
              AND lower(COALESCE(file_ext, '')) = '.docx'
              AND file_bytes IS NOT NULL
            ORDER BY created_at DESC, version DESC
            LIMIT 1
            """,
            (document_type,),
        )
        cross_tenant_global = cur.fetchone()
        if cross_tenant_global:
            return cross_tenant_global, "cross_tenant_global_active"
    return None, "not_found"


def _fetch_legacy_html_template_for_issue(
    conn,
    *,
    tenant_id: str,
    company_id: str | None,
    document_type: str,
) -> tuple[dict[str, Any] | None, str]:
    normalized_company_id = _normalize_company_scope_id(company_id)
    with conn.cursor() as cur:
        if normalized_company_id:
            cur.execute(
                """
                SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                  AND company_id = %s
                  AND is_active = TRUE
                  AND COALESCE(trim(template_html), '') <> ''
                ORDER BY version DESC
                LIMIT 1
                """,
                (tenant_id, document_type, normalized_company_id),
            )
            company_scoped = cur.fetchone()
            if company_scoped:
                return company_scoped, "company_active_html_fallback"

        cur.execute(
            """
            SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
            FROM document_templates
            WHERE tenant_id = %s
              AND document_type = %s
              AND company_id IS NULL
              AND is_active = TRUE
              AND COALESCE(trim(template_html), '') <> ''
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant_id, document_type),
        )
        global_scoped = cur.fetchone()
        if global_scoped:
            return global_scoped, "global_active_html_fallback"

        cur.execute(
            """
            SELECT id, document_type, version, file_path, template_html, file_bytes, file_mime_type, file_ext, company_id
            FROM document_templates
            WHERE document_type = %s
              AND company_id IS NULL
              AND is_active = TRUE
              AND COALESCE(trim(template_html), '') <> ''
            ORDER BY created_at DESC, version DESC
            LIMIT 1
            """,
            (document_type,),
        )
        cross_tenant_global = cur.fetchone()
        if cross_tenant_global:
            return cross_tenant_global, "cross_tenant_global_html_fallback"
    return None, "not_found"


def _fetch_document_request_for_issue(conn, *, request_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dr.id,
                   dr.tenant_id,
                   dr.company_id,
                   dr.employee_id,
                   dr.status,
                   dr.purpose_code,
                   dr.purpose_text,
                   dr.requested_at,
                   t.tenant_code,
                   t.tenant_name,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   e.full_name AS employee_name,
                   e.birth_date,
                   e.hire_date,
                   e.leave_date,
                   e.address AS employee_address,
                   e.phone AS employee_phone,
                   COALESCE(e.soc_role, '') AS employee_role,
                   COALESCE(s.site_name, '본사') AS org_name,
                   tp.ceo_name,
                   tp.biz_reg_no,
                   tp.address AS company_address,
                   tp.phone AS company_phone,
                   tp.email AS company_email,
                   tp.seal_attachment_id
            FROM document_requests dr
            JOIN tenants t ON t.id = dr.tenant_id
            JOIN employees e ON e.id = dr.employee_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(dr.company_id, e.company_id, s.company_id)
            LEFT JOIN tenant_profiles tp ON tp.tenant_id = dr.tenant_id
            WHERE dr.id = %s
              AND dr.document_type = %s
            LIMIT 1
            """,
            (request_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
        )
        return cur.fetchone()


def _update_request_failed(conn, *, request_id: str, error_message: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document_requests
            SET status = 'failed',
                generation_error = %s,
                updated_at = timezone('utc', now())
            WHERE id = %s
            """,
            (str(error_message or "").strip()[:2000], request_id),
        )


def _build_employment_certificate_mail_html(context: dict[str, Any]) -> str:
    employee_name = str(context.get("employee_name") or "직원").strip() or "직원"
    company_name = str(context.get("company_name") or "회사").strip() or "회사"
    issue_number = str(context.get("issue_number") or "-").strip() or "-"
    issue_date = str(context.get("issue_date") or "-").strip() or "-"
    purpose_label = str(context.get("purpose_label") or "-").strip() or "-"
    return (
        "<div style=\"font-family:Arial,'Noto Sans KR',sans-serif;font-size:14px;line-height:1.6;color:#111;\">"
        f"<p>{employee_name}님의 재직증명서가 발급되었습니다.</p>"
        f"<p>회사: {company_name}<br/>"
        f"발급번호: {issue_number}<br/>"
        f"발급일: {issue_date}<br/>"
        f"발급용도: {purpose_label}</p>"
        "<p>첨부된 PDF를 확인해 주세요.</p>"
        "</div>"
    )


def _process_employment_certificate_issue_job(request_id: str) -> None:
    try:
        with get_connection() as conn:
            row = _fetch_document_request_for_issue(conn, request_id=request_id)
            if not row:
                logger.warning("[HR][DOC] request not found for issue job: %s", request_id)
                return
            if str(row.get("status") or "").strip().lower() != "generating":
                logger.info("[HR][DOC] skip issue job because status is not generating: %s", row.get("status"))
                return

            _run_noncritical_db_step(
                conn,
                step_name="certificate_issue_job_processing_sync",
                callback=lambda: sync_legacy_employment_certificate_issue_job(
                    conn,
                    tenant_id=str(row.get("tenant_id") or "").strip(),
                    legacy_request_id=request_id,
                    job_state="processing",
                    payload_extra={
                        "stage": "pdf_generation",
                        "template_source": "pending",
                        "template_mode": "pending",
                        "seal_attached": False,
                    },
                    increment_attempts=True,
                ),
            )

            issued_at = datetime.now(timezone.utc)
            issue_number = build_issue_number(request_id, issued_at=issued_at)
            purpose_label = build_purpose_label(str(row.get("purpose_code") or ""), row.get("purpose_text"))
            issue_date_local = issued_at.astimezone(TZ_KST)
            hire_date = _format_date(row.get("hire_date"))
            leave_date = _resolve_termination_date(
                conn,
                tenant_id=str(row.get("tenant_id") or "").strip(),
                employee_id=str(row.get("employee_id") or "").strip(),
                fallback_value=row.get("leave_date"),
            )
            if hire_date and leave_date:
                employment_period = f"{hire_date} ~ {leave_date}"
            elif hire_date:
                employment_period = f"{hire_date} ~"
            else:
                employment_period = ""

            context = {
                "company_name": str(row.get("company_name") or row.get("tenant_name") or "").strip(),
                "biz_reg_no": str(row.get("biz_reg_no") or "").strip(),
                "ceo_name": str(row.get("ceo_name") or "").strip(),
                "company_phone": str(row.get("company_phone") or "").strip(),
                "company_email": str(row.get("company_email") or "").strip(),
                "company_address": str(row.get("company_address") or "").strip(),
                "employee_name": str(row.get("employee_name") or "").strip(),
                "birth_date": _format_date(row.get("birth_date")),
                "resident_no_masked": _resolve_masked_resident_no(
                    conn,
                    tenant_id=str(row.get("tenant_id") or "").strip(),
                    employee_id=str(row.get("employee_id") or "").strip(),
                ),
                "employee_address": str(row.get("employee_address") or "").strip(),
                "employee_phone": str(row.get("employee_phone") or "").strip(),
                "org_name": str(row.get("org_name") or "본사").strip(),
                "position_name": str(row.get("employee_role") or "").strip(),
                "hire_date": hire_date,
                "leave_date": leave_date,
                "employment_period": employment_period,
                "issue_number": issue_number,
                "issue_date": issue_date_local.strftime("%Y-%m-%d"),
                "issue_date_long": issue_date_local.strftime("%Y년 %m월 %d일"),
                "purpose_label": purpose_label,
            }

            seal_image_bytes = _load_seal_image_bytes(
                conn,
                tenant_id=str(row.get("tenant_id") or "").strip(),
                seal_attachment_id=str(row.get("seal_attachment_id") or "").strip(),
            )
            active_template, template_source = _fetch_document_template_for_issue(
                conn,
                tenant_id=str(row.get("tenant_id") or "").strip(),
                company_id=str(row.get("company_id") or "").strip(),
                document_type=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
            )
            template_docx_bytes: bytes = b""
            use_html_fallback = False
            fallback_html = ""
            if active_template:
                template_bytes = (active_template or {}).get("file_bytes")
                if isinstance(template_bytes, memoryview):
                    template_docx_bytes = template_bytes.tobytes()
                elif isinstance(template_bytes, bytes):
                    template_docx_bytes = template_bytes
                else:
                    template_docx_bytes = bytes(template_bytes or b"")
                template_ext = str((active_template or {}).get("file_ext") or "").strip().lower()
                if template_ext != ".docx" or not template_docx_bytes:
                    active_template = None
                    template_source = "not_found"

            if not active_template:
                legacy_template, legacy_source = _fetch_legacy_html_template_for_issue(
                    conn,
                    tenant_id=str(row.get("tenant_id") or "").strip(),
                    company_id=str(row.get("company_id") or "").strip(),
                    document_type=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
                )
                fallback_html = str((legacy_template or {}).get("template_html") or "").strip()
                if legacy_template and fallback_html:
                    active_template = legacy_template
                    template_source = legacy_source
                    use_html_fallback = True
                else:
                    raise RuntimeError("ACTIVE_DOCX_TEMPLATE_NOT_FOUND")

            logger.info(
                "[HR][DOC] issue template selection request_id=%s tenant_id=%s source=%s template_id=%s template_version=%s",
                request_id,
                str(row.get("tenant_id") or "").strip(),
                template_source,
                str((active_template or {}).get("id") or ""),
                str((active_template or {}).get("version") or ""),
            )

            if use_html_fallback:
                pdf_bytes = generate_employment_certificate_pdf(context, template_html=fallback_html)
            else:
                pdf_bytes = issue_employment_certificate_pdf_from_docx(
                    template_docx_bytes,
                    context,
                    seal_image_bytes=seal_image_bytes,
                )

            tenant_code = str(row.get("tenant_code") or "").strip().lower() or "tenant"
            file_name = f"employment_certificate_{issue_number}.pdf"
            file_path = f"documents/employment_certificate/{tenant_code}/{request_id}.pdf"

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE document_requests
                    SET status = 'issued',
                        issue_number = %s,
                        file_path = %s,
                        file_name = %s,
                        file_mime_type = 'application/pdf',
                        file_bytes = %s,
                        generated_at = timezone('utc', now()),
                        generation_error = NULL,
                        mail_error = %s,
                        mail_company_sent_at = %s,
                        mail_employee_sent_at = %s,
                        template_id = %s,
                        template_version = %s,
                        template_file_path = %s,
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        issue_number,
                        file_path,
                        file_name,
                        pdf_bytes,
                        None,
                        None,
                        None,
                        (active_template or {}).get("id"),
                        (active_template or {}).get("version"),
                        (active_template or {}).get("file_path"),
                        request_id,
                    ),
                )

            _run_noncritical_db_step(
                conn,
                step_name="certificate_issue_job_finalize_sync",
                callback=lambda: (
                    sync_legacy_employment_certificate_request(
                        conn,
                        tenant_id=str(row.get("tenant_id") or "").strip(),
                        legacy_request_id=request_id,
                    ),
                    sync_legacy_employment_certificate_issue_job(
                        conn,
                        tenant_id=str(row.get("tenant_id") or "").strip(),
                        legacy_request_id=request_id,
                        job_state="completed",
                        payload_extra={
                            "stage": "issued",
                            "issue_number": issue_number,
                            "template_source": template_source,
                            "template_mode": "html_fallback" if use_html_fallback else "docx",
                            "template_id": str((active_template or {}).get("id") or ""),
                            "template_version": (active_template or {}).get("version"),
                            "template_file_path": str((active_template or {}).get("file_path") or "").strip() or None,
                            "seal_attached": bool(seal_image_bytes),
                            "download_ready": True,
                            "autofill_field_count": sum(1 for value in context.values() if str(value or "").strip()),
                            "autofill_keys": sorted([key for key, value in context.items() if str(value or "").strip()]),
                            "autofill_preview": {
                                "employee_name": str(context.get("employee_name") or "").strip(),
                                "company_name": str(context.get("company_name") or "").strip(),
                                "purpose_label": str(context.get("purpose_label") or "").strip(),
                                "employment_period": str(context.get("employment_period") or "").strip(),
                            },
                        },
                    ),
                ),
            )
    except Exception as exc:
        logger.exception("[HR][DOC] issue job failed request_id=%s", request_id, exc_info=exc)
        try:
            with get_connection() as conn:
                _update_request_failed(conn, request_id=request_id, error_message=str(exc))
                row = _fetch_document_request_for_issue(conn, request_id=request_id)
                tenant_id = str((row or {}).get("tenant_id") or "").strip()
                if tenant_id:
                    _run_noncritical_db_step(
                        conn,
                        step_name="certificate_issue_job_failed_sync",
                        callback=lambda: (
                            sync_legacy_employment_certificate_request(
                                conn,
                                tenant_id=tenant_id,
                                legacy_request_id=request_id,
                            ),
                            sync_legacy_employment_certificate_issue_job(
                                conn,
                                tenant_id=tenant_id,
                                legacy_request_id=request_id,
                                job_state="failed",
                                last_error=str(exc),
                                payload_extra={"stage": "failed"},
                            ),
                        ),
                    )
        except Exception:
            logger.exception("[HR][DOC] failed to mark request failed request_id=%s", request_id)


@router.post("/hr/documents/employment-certificate/requests")
def create_employment_certificate_request(
    payload: EmploymentCertificateRequestCreate,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    employee_row = _get_employee_scope_row(conn, employee_id=employee_id, tenant_id=tenant_id)

    purpose_text = _validate_purpose(payload.purpose_code, payload.purpose_text)
    today_count = _count_today_employee_requests(conn, tenant_id=tenant_id, employee_id=employee_id)
    if today_count >= DAILY_REQUEST_LIMIT:
        _raise_api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "DAILY_LIMIT_EXCEEDED",
            "오늘은 재직증명서 발급 요청을 최대 3회까지 할 수 있습니다.",
        )

    request_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    # company_id가 없으면 NULL로 유지해 글로벌 템플릿(company_id IS NULL) fallback이 정확히 동작하도록 한다.
    company_id = employee_row.get("company_id")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_requests (
                id, tenant_id, company_id, employee_id, document_type, status,
                purpose_code, purpose_text, requested_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'requested', %s, %s, %s, %s, %s)
            RETURNING id, status, requested_at
            """,
            (
                request_id,
                tenant_id,
                company_id,
                employee_row.get("id"),
                DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
                payload.purpose_code,
                purpose_text,
                now_utc,
                now_utc,
                now_utc,
            ),
        )
        row = cur.fetchone()

    remaining = max(0, DAILY_REQUEST_LIMIT - (today_count + 1))
    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_request_approval_adapter",
        callback=lambda: create_certificate_request_approval_adapter(
            conn,
            tenant_id=tenant_id,
            document_request_id=str((row or {}).get("id") or request_id),
            employee_id=str(employee_row.get("id") or "").strip(),
            company_id=str(company_id or "").strip() or None,
            actor_user=user,
            purpose_code=payload.purpose_code,
            purpose_text=purpose_text,
        ),
    )
    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_request_sync",
        callback=lambda: sync_legacy_employment_certificate_request(
            conn,
            tenant_id=tenant_id,
            legacy_request_id=str((row or {}).get("id") or request_id),
            actor_user_id=str(user.get("id") or "").strip() or None,
            actor_role=str(user.get("role") or "").strip() or None,
        ),
    )
    return {
        "request_id": str(row.get("id") if row else request_id),
        "status": (row or {}).get("status") or "requested",
        "requested_at": (row or {}).get("requested_at") or now_utc,
        "today_requested_count": today_count + 1,
        "today_remaining": remaining,
    }


@router.get("/hr/documents/employment-certificate/quota")
def get_employment_certificate_quota(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    # Ensure employee belongs to scoped tenant.
    _get_employee_scope_row(conn, employee_id=employee_id, tenant_id=tenant_id)

    today_count = _count_today_employee_requests(conn, tenant_id=tenant_id, employee_id=employee_id)
    return {
        "daily_limit": DAILY_REQUEST_LIMIT,
        "today_requested_count": today_count,
        "today_remaining": max(0, DAILY_REQUEST_LIMIT - today_count),
    }


@router.get("/hr/documents/employment-certificate/requests")
def list_my_employment_certificate_requests(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    me: int = Query(default=1),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ = me  # UI 호환을 위한 파라미터 유지
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    _get_employee_scope_row(conn, employee_id=employee_id, tenant_id=tenant_id)

    limit = int(pageSize)
    offset = (int(page) - 1) * limit

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   status,
                   purpose_code,
                   purpose_text,
                   requested_at,
                   approved_at,
                   rejection_reason,
                   issue_number,
                   template_id,
                   template_version,
                   template_file_path,
                   COALESCE(file_path, '') AS file_path,
                   COALESCE(file_url, '') AS file_url,
                   (file_bytes IS NOT NULL OR COALESCE(file_path, '') <> '' OR COALESCE(file_url, '') <> '') AS file_ready,
                   mail_company_sent_at,
                   mail_employee_sent_at
            FROM document_requests
            WHERE tenant_id = %s
              AND employee_id = %s
              AND document_type = %s
            ORDER BY requested_at DESC
            LIMIT %s OFFSET %s
            """,
            (
                tenant_id,
                employee_id,
                DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
                limit,
                offset,
            ),
        )
        rows = cur.fetchall() or []

    return [
        {
            "id": str(row.get("id")),
            "requested_at": row.get("requested_at"),
            "approved_at": row.get("approved_at"),
            "purpose_code": row.get("purpose_code"),
            "purpose_text": row.get("purpose_text"),
            "status": row.get("status"),
            "rejection_reason": row.get("rejection_reason"),
            "issue_number": row.get("issue_number"),
            "template_id": str(row.get("template_id") or ""),
            "template_version": row.get("template_version"),
            "template_file_path": row.get("template_file_path"),
            "file_ready": bool(row.get("file_ready")),
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
        }
        for row in rows
    ]


@router.post("/hr/documents/resignation-requests")
def create_resignation_request(
    payload: ResignationRequestCreate,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    employee_row = _get_employee_scope_row(conn, employee_id=employee_id, tenant_id=tenant_id)

    request_id = uuid.uuid4()
    now_utc = datetime.now(timezone.utc)
    company_id = employee_row.get("company_id")
    payload_json = _json_dumps(
        {
            "resignation_type": payload.resignation_type,
            "expected_last_working_date": payload.expected_last_working_date,
            "resignation_reason": payload.resignation_reason,
            "handover_notes": payload.handover_notes,
        }
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO document_requests (
                id, tenant_id, company_id, employee_id, document_type, status,
                purpose_code, purpose_text, requested_at, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'requested', %s, %s, %s, %s, %s)
            RETURNING id, status, requested_at, approved_at, rejection_reason
            """,
            (
                request_id,
                tenant_id,
                company_id,
                employee_row.get("id"),
                DOCUMENT_TYPE_RESIGNATION_FORM,
                payload.resignation_type,
                payload_json,
                now_utc,
                now_utc,
                now_utc,
            ),
        )
        row = cur.fetchone() or {}

    serialized = _serialize_resignation_request_row(
        {
            **row,
            "purpose_code": payload.resignation_type,
            "purpose_text": payload_json,
            "employee_code": str(user.get("employee_code") or "").strip() or None,
            "employee_name": employee_row.get("full_name"),
            "company_name": employee_row.get("company_name"),
            "org_name": employee_row.get("site_name") or "본사",
        }
    )
    _run_noncritical_db_step(
        conn,
        step_name="resignation_request_approval_adapter",
        callback=lambda: create_certificate_request_approval_adapter(
            conn,
            tenant_id=tenant_id,
            document_request_id=str(request_id),
            employee_id=str(employee_row.get("id") or "").strip(),
            company_id=str(company_id or "").strip() or None,
            actor_user=user,
            certificate_type_key=DOCUMENT_TYPE_RESIGNATION_FORM,
            certificate_type_name="사직서",
            purpose_code=payload.resignation_type,
            purpose_text=payload_json,
            site_id=str(employee_row.get("site_id") or "").strip() or None,
            legacy_source_type="certificate_request",
        ),
    )
    return {"item": serialized}


@router.get("/hr/documents/resignation-requests")
def list_my_resignation_requests(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    _get_employee_scope_row(conn, employee_id=employee_id, tenant_id=tenant_id)
    limit = int(pageSize)
    offset = (int(page) - 1) * limit

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT dr.id,
                   dr.status,
                   dr.purpose_code,
                   dr.purpose_text,
                   dr.requested_at,
                   dr.approved_at,
                   dr.rejection_reason
            FROM document_requests dr
            WHERE dr.tenant_id = %s
              AND dr.employee_id = %s
              AND dr.document_type = %s
            ORDER BY dr.requested_at DESC
            LIMIT %s OFFSET %s
            """,
            (tenant_id, employee_id, DOCUMENT_TYPE_RESIGNATION_FORM, limit, offset),
        )
        rows = cur.fetchall() or []

    items = [
        _serialize_resignation_request_row(
            {
                **row,
                "employee_code": str(user.get("employee_code") or "").strip() or None,
                "employee_name": str(user.get("full_name") or "").strip() or None,
            }
        )
        for row in rows
    ]
    return {"items": items}


@router.get("/hr/documents/requests/{request_id}/download")
def download_employment_certificate_pdf(
    request_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    employee_id = _ensure_employee_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    request_uuid = _parse_uuid(request_id, field_name="request_id")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, status, file_name, file_mime_type, file_bytes
            FROM document_requests
            WHERE id = %s
              AND tenant_id = %s
              AND employee_id = %s
              AND document_type = %s
            LIMIT 1
            """,
            (request_uuid, tenant_id, employee_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
        )
        row = cur.fetchone()

    if not row:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "문서 요청을 찾을 수 없습니다.")

    if str(row.get("status") or "").strip().lower() != "issued":
        _raise_api_error(status.HTTP_409_CONFLICT, "NOT_READY", "아직 발급이 완료되지 않았습니다.")

    raw_bytes = row.get("file_bytes")
    if isinstance(raw_bytes, memoryview):
        payload = raw_bytes.tobytes()
    elif isinstance(raw_bytes, bytes):
        payload = raw_bytes
    else:
        payload = bytes(raw_bytes or b"")

    if not payload:
        _raise_api_error(status.HTTP_404_NOT_FOUND, "FILE_NOT_FOUND", "발급 파일을 찾을 수 없습니다.")

    file_name = str(row.get("file_name") or f"employment_certificate_{request_id}.pdf").strip()
    mime_type = str(row.get("file_mime_type") or "application/pdf").strip() or "application/pdf"

    return Response(
        content=payload,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.get("/admin/hr/documents/employment-certificate/requests")
def list_admin_employment_certificate_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=30, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    normalized_status = str(status_filter or "").strip().lower()
    normalized_q = str(q or "").strip()

    clauses = ["dr.tenant_id = %s", "dr.document_type = %s"]
    params: list[Any] = [tenant_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE]

    if normalized_status and normalized_status != "all":
        clauses.append("lower(dr.status) = %s")
        params.append(normalized_status)

    if normalized_q:
        clauses.append(
            """
            (
              e.full_name ILIKE %s
              OR COALESCE(c.company_name, t.tenant_name, '') ILIKE %s
              OR COALESCE(e.employee_code, '') ILIKE %s
              OR COALESCE(dr.issue_number, '') ILIKE %s
            )
            """
        )
        like = f"%{normalized_q}%"
        params.extend([like, like, like, like])

    where_sql = " AND ".join(clauses)
    limit = int(pageSize)
    offset = (int(page) - 1) * limit

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT dr.id,
                   dr.status,
                   dr.requested_at,
                   dr.approved_at,
                   dr.rejection_reason,
                   dr.purpose_code,
                   dr.purpose_text,
                   dr.issue_number,
                   dr.template_id,
                   dr.template_version,
                   dr.template_file_path,
                   dr.mail_company_sent_at,
                   dr.mail_employee_sent_at,
                   e.employee_code,
                   e.full_name AS employee_name,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   COALESCE(s.site_name, '본사') AS org_name
            FROM document_requests dr
            JOIN employees e ON e.id = dr.employee_id
            JOIN tenants t ON t.id = dr.tenant_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(dr.company_id, e.company_id, s.company_id)
            WHERE {where_sql}
            ORDER BY dr.requested_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [limit, offset]),
        )
        rows = cur.fetchall() or []

    return [
        {
            "id": str(row.get("id")),
            "employee_name": row.get("employee_name"),
            "employee_code": row.get("employee_code"),
            "company_name": row.get("company_name"),
            "org": row.get("org_name"),
            "purpose_code": row.get("purpose_code"),
            "purpose_text": row.get("purpose_text"),
            "status": row.get("status"),
            "requested_at": row.get("requested_at"),
            "approved_at": row.get("approved_at"),
            "rejection_reason": row.get("rejection_reason"),
            "issue_number": row.get("issue_number"),
            "template_id": str(row.get("template_id") or ""),
            "template_version": row.get("template_version"),
            "template_file_path": row.get("template_file_path"),
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
        }
        for row in rows
    ]


@router.get("/admin/hr/documents/resignation-requests")
def list_admin_resignation_requests(
    status_filter: str | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=120),
    limit: int | None = Query(default=None, ge=1, le=200),
    page: int = Query(default=1, ge=1),
    pageSize: int | None = Query(default=None, ge=1, le=200),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    normalized_status = str(status_filter or "").strip().lower()
    normalized_q = str(q or "").strip()
    effective_limit = int(limit or pageSize or 30)
    effective_offset = (int(page) - 1) * effective_limit if pageSize else 0

    clauses = ["dr.tenant_id = %s", "dr.document_type = %s"]
    params: list[Any] = [tenant_id, DOCUMENT_TYPE_RESIGNATION_FORM]

    if normalized_status and normalized_status != "all":
        clauses.append("lower(dr.status) = %s")
        params.append(normalized_status)

    if normalized_q:
        clauses.append(
            """
            (
              e.full_name ILIKE %s
              OR COALESCE(e.employee_code, '') ILIKE %s
              OR COALESCE(c.company_name, t.tenant_name, '') ILIKE %s
              OR COALESCE(s.site_name, '') ILIKE %s
            )
            """
        )
        like = f"%{normalized_q}%"
        params.extend([like, like, like, like])

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT dr.id,
                   dr.status,
                   dr.purpose_code,
                   dr.purpose_text,
                   dr.requested_at,
                   dr.approved_at,
                   dr.rejection_reason,
                   e.employee_code,
                   e.full_name AS employee_name,
                   COALESCE(c.company_name, t.tenant_name) AS company_name,
                   COALESCE(s.site_name, '본사') AS org_name
            FROM document_requests dr
            JOIN employees e ON e.id = dr.employee_id
            JOIN tenants t ON t.id = dr.tenant_id
            LEFT JOIN sites s ON s.id = e.site_id
            LEFT JOIN companies c ON c.id = COALESCE(dr.company_id, e.company_id, s.company_id)
            WHERE {' AND '.join(clauses)}
            ORDER BY dr.requested_at DESC
            LIMIT %s OFFSET %s
            """,
            tuple(params + [effective_limit, effective_offset]),
        )
        rows = cur.fetchall() or []

    return {"items": [_serialize_resignation_request_row(row) for row in rows]}


@router.post("/admin/hr/documents/requests/{request_id}/approve")
def approve_employment_certificate_request(
    request_id: str,
    background_tasks: BackgroundTasks,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()

    request_uuid = _parse_uuid(request_id, field_name="request_id")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document_requests
            SET status = 'generating',
                approved_at = timezone('utc', now()),
                approved_by = %s,
                rejection_reason = NULL,
                generation_error = NULL,
                mail_error = NULL,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND document_type = %s
              AND status = 'requested'
            RETURNING id
            """,
            (user.get("id"), request_uuid, tenant_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
        )
        row = cur.fetchone()

    if not row:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status
                FROM document_requests
                WHERE id = %s
                  AND tenant_id = %s
                  AND document_type = %s
                LIMIT 1
                """,
                (request_uuid, tenant_id, DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
            )
            existing = cur.fetchone()
        if not existing:
            _raise_api_error(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "문서 요청을 찾을 수 없습니다.")
        _raise_api_error(
            status.HTTP_409_CONFLICT,
            "INVALID_STATUS",
            f"현재 상태에서는 승인할 수 없습니다. (status={existing.get('status')})",
        )

    background_tasks.add_task(_process_employment_certificate_issue_job, str(request_uuid))
    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_approval_status_sync",
        callback=lambda: sync_legacy_approval_status(
            conn,
            tenant_id=tenant_id,
            legacy_source_type="employment_certificate_request",
            legacy_source_id=str(request_uuid),
            status_value="approved",
            actor_user_id=str(user.get("id") or "").strip() or None,
            actor_role=str(user.get("role") or "").strip() or None,
        ),
    )
    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_approval_queue_sync",
        callback=lambda: (
            sync_legacy_employment_certificate_request(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=str(request_uuid),
                actor_user_id=str(user.get("id") or "").strip() or None,
                actor_role=str(user.get("role") or "").strip() or None,
            ),
            sync_legacy_employment_certificate_issue_job(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=str(request_uuid),
                job_state="queued",
                payload_extra={"stage": "approved"},
            ),
        ),
    )
    return {"ok": True}


@router.post("/admin/hr/documents/resignation-requests/{request_id}/approve")
def approve_resignation_request(
    request_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    request_uuid = _parse_uuid(request_id, field_name="request_id")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document_requests
            SET status = 'approved',
                approved_at = timezone('utc', now()),
                approved_by = %s,
                rejection_reason = NULL,
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND document_type = %s
              AND status = 'requested'
            RETURNING id
            """,
            (user.get("id"), request_uuid, tenant_id, DOCUMENT_TYPE_RESIGNATION_FORM),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_409_CONFLICT, "INVALID_STATUS", "현재 상태에서는 승인할 수 없습니다.")
    _run_noncritical_db_step(
        conn,
        step_name="resignation_request_status_sync",
        callback=lambda: sync_legacy_approval_status(
            conn,
            tenant_id=tenant_id,
            legacy_source_type="certificate_request",
            legacy_source_id=str(request_uuid),
            status_value="approved",
            actor_user_id=str(user.get("id") or "").strip() or None,
            actor_role=str(user.get("role") or "").strip() or None,
        ),
    )
    return {"ok": True}


@router.post("/admin/hr/documents/requests/{request_id}/reject")
def reject_employment_certificate_request(
    request_id: str,
    payload: EmploymentCertificateRejectRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    request_uuid = _parse_uuid(request_id, field_name="request_id")

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document_requests
            SET status = 'rejected',
                rejection_reason = %s,
                approved_by = %s,
                approved_at = timezone('utc', now()),
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND document_type = %s
              AND status = 'requested'
            RETURNING id
            """,
            (
                payload.rejection_reason,
                user.get("id"),
                request_uuid,
                tenant_id,
                DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
            ),
        )
        row = cur.fetchone()

    if not row:
        _raise_api_error(status.HTTP_409_CONFLICT, "INVALID_STATUS", "현재 상태에서는 반려할 수 없습니다.")

    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_rejection_status_sync",
        callback=lambda: sync_legacy_approval_status(
            conn,
            tenant_id=tenant_id,
            legacy_source_type="employment_certificate_request",
            legacy_source_id=str(request_uuid),
            status_value="rejected",
            actor_user_id=str(user.get("id") or "").strip() or None,
            actor_role=str(user.get("role") or "").strip() or None,
            comment_text=payload.rejection_reason,
        ),
    )
    _run_noncritical_db_step(
        conn,
        step_name="employment_certificate_rejection_queue_sync",
        callback=lambda: (
            sync_legacy_employment_certificate_request(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=str(request_uuid),
                actor_user_id=str(user.get("id") or "").strip() or None,
                actor_role=str(user.get("role") or "").strip() or None,
            ),
            sync_legacy_employment_certificate_issue_job(
                conn,
                tenant_id=tenant_id,
                legacy_request_id=str(request_uuid),
                job_state="cancelled",
                last_error=payload.rejection_reason,
                payload_extra={"stage": "rejected"},
            ),
        ),
    )
    return {"ok": True}


@router.post("/admin/hr/documents/resignation-requests/{request_id}/reject")
def reject_resignation_request(
    request_id: str,
    payload: EmploymentCertificateRejectRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    request_uuid = _parse_uuid(request_id, field_name="request_id")
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE document_requests
            SET status = 'rejected',
                rejection_reason = %s,
                approved_by = %s,
                approved_at = timezone('utc', now()),
                updated_at = timezone('utc', now())
            WHERE id = %s
              AND tenant_id = %s
              AND document_type = %s
              AND status = 'requested'
            RETURNING id
            """,
            (
                payload.rejection_reason,
                user.get("id"),
                request_uuid,
                tenant_id,
                DOCUMENT_TYPE_RESIGNATION_FORM,
            ),
        )
        row = cur.fetchone()
    if not row:
        _raise_api_error(status.HTTP_409_CONFLICT, "INVALID_STATUS", "현재 상태에서는 반려할 수 없습니다.")
    _run_noncritical_db_step(
        conn,
        step_name="resignation_request_rejection_sync",
        callback=lambda: sync_legacy_approval_status(
            conn,
            tenant_id=tenant_id,
            legacy_source_type="certificate_request",
            legacy_source_id=str(request_uuid),
            status_value="rejected",
            actor_user_id=str(user.get("id") or "").strip() or None,
            actor_role=str(user.get("role") or "").strip() or None,
            comment_text=payload.rejection_reason,
        ),
    )
    return {"ok": True}


@router.post("/admin/hr/documents/resignation-requests/{request_id}/delegate-approve")
def delegate_approve_resignation_request(
    request_id: str,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    return approve_resignation_request(
        request_id=request_id,
        x_tenant_id=x_tenant_id,
        conn=conn,
        user=user,
    )


@router.get("/admin/hr/documents/templates")
def list_document_templates(
    document_type: str = Query(default=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
    company_id: str | None = Query(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_template_manager_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    normalized_document_type = _normalize_document_type(document_type)
    scoped_company_id = _normalize_company_scope_id(company_id)

    with conn.cursor() as cur:
        if scoped_company_id:
            cur.execute(
                """
                SELECT id,
                       company_id,
                       document_type,
                       version,
                       file_path,
                       file_ext,
                       is_active,
                       created_by,
                       created_at
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                  AND company_id = %s
                ORDER BY version DESC
                """,
                (tenant_id, normalized_document_type, scoped_company_id),
            )
        else:
            cur.execute(
                """
                SELECT id,
                       company_id,
                       document_type,
                       version,
                       file_path,
                       file_ext,
                       is_active,
                       created_by,
                       created_at
                FROM document_templates
                WHERE tenant_id = %s
                  AND document_type = %s
                ORDER BY version DESC
                """,
                (tenant_id, normalized_document_type),
            )
        rows = cur.fetchall() or []

    return [
        {
            "id": str(row.get("id")),
            "company_id": str(row.get("company_id") or ""),
            "document_type": row.get("document_type"),
            "version": int(row.get("version") or 0),
            "file_path": row.get("file_path"),
            "file_ext": row.get("file_ext"),
            "is_active": bool(row.get("is_active")),
            "created_by": str(row.get("created_by") or ""),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


@router.get("/admin/hr/documents/approval-policy")
def get_document_approval_policy(
    document_type: str = Query(default=DOCUMENT_TYPE_RETIREMENT_CERTIFICATE),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=False,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    normalized_document_type = _normalize_approval_policy_document_type(document_type)
    return _build_document_approval_policy_response(
        conn,
        tenant_id=tenant_id,
        document_type=normalized_document_type,
    )


@router.put("/admin/hr/documents/approval-policy")
def update_document_approval_policy(
    payload: DocumentApprovalPolicyUpdateRequest,
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_admin_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=False,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    actor_user_id = str(user.get("id") or "").strip() or None
    normalized_document_type = _normalize_approval_policy_document_type(payload.document_type)
    policy_state = _resolve_document_approval_policy_state(normalized_document_type)
    if not policy_state["editable"]:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            str(policy_state["unsupported_reason"] or "지원하지 않는 문서 타입입니다."),
            fields={"document_type": "unsupported"},
        )
    items = list(payload.items or [])
    if not items:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "최소 1개의 승인 단계를 저장해야 합니다.",
            fields={"items": "min_1"},
        )
    if len(items) > 7:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"items": "max_7"},
        )

    for index, item in enumerate(items, start=1):
        if item.step_kind == "rank":
            _raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "HQ 직급 기반 단계는 아직 지원하지 않습니다.",
                fields={f"items[{index - 1}].step_kind": "unsupported"},
            )
        if item.step_kind == "explicit_user":
            member_user_ids = item.member_user_ids or ([item.explicit_user_id] if item.explicit_user_id else [])
            if not member_user_ids:
                _raise_api_error(
                    status.HTTP_400_BAD_REQUEST,
                    "VALIDATION_ERROR",
                    "입력값을 확인해주세요.",
                    fields={f"items[{index - 1}].explicit_user_id": "required"},
                )
            for member_index, member_user_id in enumerate(member_user_ids):
                _parse_uuid(member_user_id, field_name=f"items[{index - 1}].member_user_ids[{member_index}]")

    ensure_default_approval_line_rules(conn, tenant_id=tenant_id, actor_user_id=actor_user_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM approval_line_rules
            WHERE tenant_id = %s
              AND form_key = %s
            """,
            (tenant_id, policy_state["rule_form_key"]),
        )
        for index, item in enumerate(items, start=1):
            stage_order = max(1, min(7, int(item.stage_order or index)))
            approver_role = item.site_role if item.step_kind == "site_supervisor" else None
            member_user_ids = item.member_user_ids or ([item.explicit_user_id] if item.explicit_user_id else [])
            approver_user_id = member_user_ids[0] if item.step_kind == "explicit_user" and member_user_ids else None
            scope_type = "site_or_tenant" if item.step_kind == "site_supervisor" else "tenant"
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
                    %s, %s, %s, %s, %s, %s, %s::uuid, %s, NULL, TRUE, %s::jsonb, %s,
                    timezone('utc', now()), timezone('utc', now())
                )
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    policy_state["rule_form_key"],
                    stage_order,
                    item.label or f"승인 {stage_order}",
                    approver_role,
                    approver_user_id,
                    scope_type,
                    _json_dumps(
                        {
                            "step_kind": item.step_kind,
                            "site_role": item.site_role,
                            "member_user_ids": member_user_ids,
                            "approval_group_id": item.approval_group_id,
                            "approval_rank_id": item.approval_rank_id,
                            "allow_delegate": bool(item.allow_delegate),
                            "is_required": bool(item.is_required),
                            "document_type": normalized_document_type,
                            "stage_order": stage_order,
                        }
                    ),
                    actor_user_id,
                ),
            )

    return _build_document_approval_policy_response(
        conn,
        tenant_id=tenant_id,
        document_type=normalized_document_type,
    )


@router.post("/admin/hr/documents/templates/upload")
async def upload_document_template(
    document_type: str = Form(default=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
    company_id: str | None = Form(default=None),
    file: UploadFile = File(...),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    conn=Depends(get_db_conn),
    user=Depends(get_current_user),
):
    _ensure_template_manager_role(user)
    tenant = resolve_scoped_tenant(
        conn,
        user,
        header_tenant_id=x_tenant_id,
        require_dev_context=True,
    )
    tenant_id = str(tenant.get("id") or "").strip()
    normalized_document_type = _normalize_document_type(document_type)
    scoped_company_id = _validate_company_scope(
        conn,
        tenant_id=tenant_id,
        company_id=company_id,
    )

    original_name = str(file.filename or "").strip() or "template.docx"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_TEMPLATE_EXTENSIONS:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"file": "docx_only"},
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"file": "empty"},
        )
    if len(raw_bytes) > MAX_TEMPLATE_UPLOAD_BYTES:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"file": "max_2mb"},
        )

    try:
        from docx import Document as _DocxDocument

        _DocxDocument(BytesIO(raw_bytes))
    except Exception:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"file": "docx_parse_failed"},
        )
        return None

    template_id = uuid.uuid4()
    actor_id = user.get("id")

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(MAX(version), 0) + 1 AS next_version
            FROM document_templates
            WHERE tenant_id = %s
              AND document_type = %s
            """,
            (tenant_id, normalized_document_type),
        )
        row = cur.fetchone() or {}
        next_version = int(row.get("next_version") or 1)
        next_file_path = f"templates/{normalized_document_type}/v{next_version}{extension}"

        cur.execute(
            """
            UPDATE document_templates
            SET is_active = FALSE
            WHERE tenant_id = %s
              AND document_type = %s
              AND (
                    (%s::uuid IS NULL AND company_id IS NULL)
                 OR (company_id = %s::uuid)
              )
              AND is_active = TRUE
            """,
            (tenant_id, normalized_document_type, scoped_company_id, scoped_company_id),
        )

        cur.execute(
            """
            INSERT INTO document_templates (
                id,
                tenant_id,
                company_id,
                document_type,
                version,
                file_path,
                template_html,
                file_bytes,
                file_mime_type,
                file_ext,
                is_active,
                created_by,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, timezone('utc', now()))
            RETURNING id, company_id, document_type, version, file_path, file_ext, is_active, created_by, created_at
            """,
            (
                template_id,
                tenant_id,
                scoped_company_id,
                normalized_document_type,
                next_version,
                next_file_path,
                "",
                raw_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                extension,
                actor_id,
            ),
        )
        inserted = cur.fetchone() or {}

    return {
        "id": str(inserted.get("id") or template_id),
        "company_id": str(inserted.get("company_id") or scoped_company_id or ""),
        "document_type": inserted.get("document_type") or normalized_document_type,
        "version": int(inserted.get("version") or next_version),
        "file_path": inserted.get("file_path") or next_file_path,
        "file_ext": inserted.get("file_ext") or extension,
        "is_active": bool(inserted.get("is_active", True)),
        "created_by": str(inserted.get("created_by") or actor_id or ""),
        "created_at": inserted.get("created_at"),
    }
