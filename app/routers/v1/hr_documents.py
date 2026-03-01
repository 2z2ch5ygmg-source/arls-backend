from __future__ import annotations

import logging
from pathlib import Path
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from ...db import get_connection
from ...deps import apply_rate_limit, get_current_user, get_db_conn
from ...services.employment_certificate import (
    EMPLOYMENT_CERTIFICATE_TEMPLATE_VARIABLES,
    build_issue_number,
    build_purpose_label,
    convert_docx_template_to_html,
    generate_employment_certificate_pdf,
    render_employment_certificate_html,
    send_certificate_mail,
)
from ...utils.permissions import ROLE_BRANCH_MANAGER, ROLE_DEV, ROLE_EMPLOYEE, normalize_role
from ...utils.schema_introspection import table_column_exists
from ...utils.tenant_context import resolve_scoped_tenant

router = APIRouter(tags=["hr-documents"], dependencies=[Depends(apply_rate_limit)])
logger = logging.getLogger(__name__)

DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE = "employment_certificate"
DAILY_REQUEST_LIMIT = 3
TZ_KST = timezone(timedelta(hours=9))
PURPOSE_CODES = {"BANK", "GOV", "CARD", "OTHER"}
ALLOWED_TEMPLATE_DOCUMENT_TYPES = {DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE}
ALLOWED_TEMPLATE_EXTENSIONS = {".html", ".docx"}
MAX_TEMPLATE_UPLOAD_BYTES = 2 * 1024 * 1024


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


def _raise_api_error(status_code: int, code: str, message: str, *, fields: dict[str, str] | None = None) -> None:
    detail: dict[str, Any] = {"error": code, "message": message}
    if fields:
        detail["fields"] = fields
    raise HTTPException(status_code=status_code, detail=detail)


def _ensure_admin_role(user: dict) -> None:
    actor_role = normalize_role(user.get("role"))
    if actor_role not in (ROLE_DEV, ROLE_BRANCH_MANAGER):
        _raise_api_error(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "접근 권한이 없습니다.")


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
            return "-"
    return "-"


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
                   e.full_name,
                   e.birth_date,
                   e.hire_date,
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


def _has_template_variable(template_html: str, variable_name: str) -> bool:
    pattern = re.compile(r"\{\{\s*" + re.escape(variable_name) + r"\s*\}\}")
    return bool(pattern.search(template_html))


def _validate_template_html(template_html: str) -> list[str]:
    missing = [name for name in EMPLOYMENT_CERTIFICATE_TEMPLATE_VARIABLES if not _has_template_variable(template_html, name)]
    return missing


def _fetch_active_document_template(
    conn,
    *,
    tenant_id: str,
    document_type: str,
) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, document_type, version, file_path, template_html
            FROM document_templates
            WHERE tenant_id = %s
              AND document_type = %s
              AND is_active = TRUE
            ORDER BY version DESC
            LIMIT 1
            """,
            (tenant_id, document_type),
        )
        return cur.fetchone()


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

            issued_at = datetime.now(timezone.utc)
            issue_number = build_issue_number(request_id, issued_at=issued_at)
            purpose_label = build_purpose_label(str(row.get("purpose_code") or ""), row.get("purpose_text"))
            issue_date_local = issued_at.astimezone(TZ_KST)

            context = {
                "company_name": str(row.get("company_name") or row.get("tenant_name") or "-").strip() or "-",
                "biz_reg_no": str(row.get("biz_reg_no") or "-").strip() or "-",
                "ceo_name": str(row.get("ceo_name") or "-").strip() or "-",
                "company_phone": str(row.get("company_phone") or "-").strip() or "-",
                "company_email": str(row.get("company_email") or "-").strip() or "-",
                "company_address": str(row.get("company_address") or "-").strip() or "-",
                "employee_name": str(row.get("employee_name") or "-").strip() or "-",
                "birth_date": _format_date(row.get("birth_date")),
                "org_name": str(row.get("org_name") or "본사").strip() or "본사",
                "position_name": str(row.get("employee_role") or "사원").strip() or "사원",
                "hire_date": _format_date(row.get("hire_date")),
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
            active_template = _fetch_active_document_template(
                conn,
                tenant_id=str(row.get("tenant_id") or "").strip(),
                document_type=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE,
            )
            active_template_html = str((active_template or {}).get("template_html") or "")
            html_body = render_employment_certificate_html(context, template_html=active_template_html)
            pdf_bytes = generate_employment_certificate_pdf(
                context,
                seal_image_bytes=seal_image_bytes,
                rendered_html=html_body,
                template_html=active_template_html,
            )

            tenant_code = str(row.get("tenant_code") or "").strip().lower() or "tenant"
            file_name = f"employment_certificate_{issue_number}.pdf"
            file_path = f"documents/employment_certificate/{tenant_code}/{request_id}.pdf"

            company_email = _normalize_email(str(row.get("company_email") or ""))
            employee_email = _resolve_employee_email(
                conn,
                tenant_id=str(row.get("tenant_id") or "").strip(),
                employee_id=str(row.get("employee_id") or "").strip(),
            )

            company_mail_result = send_certificate_mail(
                to_email=company_email,
                subject=f"재직증명서 발급 - {context['employee_name']}",
                html_body=html_body,
                attachment_name=file_name,
                attachment_bytes=pdf_bytes,
            )
            employee_mail_result = send_certificate_mail(
                to_email=employee_email,
                subject=f"재직증명서 발급 - {context['employee_name']}",
                html_body=html_body,
                attachment_name=file_name,
                attachment_bytes=pdf_bytes,
            )

            mail_errors: list[str] = []
            mail_company_sent_at = None
            mail_employee_sent_at = None
            if company_mail_result.sent:
                mail_company_sent_at = issued_at
            else:
                mail_errors.append(f"company:{company_mail_result.error or 'send_failed'}")
            if employee_mail_result.sent:
                mail_employee_sent_at = issued_at
            else:
                mail_errors.append(f"employee:{employee_mail_result.error or 'send_failed'}")

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
                        updated_at = timezone('utc', now())
                    WHERE id = %s
                    """,
                    (
                        issue_number,
                        file_path,
                        file_name,
                        pdf_bytes,
                        "; ".join(mail_errors) if mail_errors else None,
                        mail_company_sent_at,
                        mail_employee_sent_at,
                        request_id,
                    ),
                )
    except Exception as exc:
        logger.exception("[HR][DOC] issue job failed request_id=%s", request_id, exc_info=exc)
        try:
            with get_connection() as conn:
                _update_request_failed(conn, request_id=request_id, error_message=str(exc))
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
    company_id = employee_row.get("company_id") or tenant_id
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
            "file_ready": bool(row.get("file_ready")),
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
        }
        for row in rows
    ]


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
            "mail_company_sent_at": row.get("mail_company_sent_at"),
            "mail_employee_sent_at": row.get("mail_employee_sent_at"),
        }
        for row in rows
    ]


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

    return {"ok": True}


@router.get("/admin/hr/documents/templates")
def list_document_templates(
    document_type: str = Query(default=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
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
    normalized_document_type = _normalize_document_type(document_type)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   document_type,
                   version,
                   file_path,
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
            "document_type": row.get("document_type"),
            "version": int(row.get("version") or 0),
            "file_path": row.get("file_path"),
            "is_active": bool(row.get("is_active")),
            "created_by": str(row.get("created_by") or ""),
            "created_at": row.get("created_at"),
        }
        for row in rows
    ]


@router.post("/admin/hr/documents/templates/upload")
async def upload_document_template(
    document_type: str = Form(default=DOCUMENT_TYPE_EMPLOYMENT_CERTIFICATE),
    file: UploadFile = File(...),
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
    normalized_document_type = _normalize_document_type(document_type)

    original_name = str(file.filename or "").strip() or "template.html"
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_TEMPLATE_EXTENSIONS:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "입력값을 확인해주세요.",
            fields={"file": "html_or_docx_only"},
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

    if extension == ".html":
        try:
            template_html = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            _raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "입력값을 확인해주세요.",
                fields={"file": "utf8_required"},
            )
            return None
    else:
        try:
            template_html = convert_docx_template_to_html(raw_bytes)
        except Exception:
            _raise_api_error(
                status.HTTP_400_BAD_REQUEST,
                "VALIDATION_ERROR",
                "입력값을 확인해주세요.",
                fields={"file": "docx_parse_failed"},
            )
            return None

    missing_variables = _validate_template_html(template_html)
    if missing_variables:
        _raise_api_error(
            status.HTTP_400_BAD_REQUEST,
            "VALIDATION_ERROR",
            "템플릿 필수 변수가 누락되었습니다.",
            fields={"template_variables": ", ".join(missing_variables)},
        )

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
              AND is_active = TRUE
            """,
            (tenant_id, normalized_document_type),
        )

        cur.execute(
            """
            INSERT INTO document_templates (
                id,
                tenant_id,
                document_type,
                version,
                file_path,
                template_html,
                is_active,
                created_by,
                created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, timezone('utc', now()))
            RETURNING id, document_type, version, file_path, is_active, created_by, created_at
            """,
            (
                template_id,
                tenant_id,
                normalized_document_type,
                next_version,
                next_file_path,
                template_html,
                actor_id,
            ),
        )
        inserted = cur.fetchone() or {}

    return {
        "id": str(inserted.get("id") or template_id),
        "document_type": inserted.get("document_type") or normalized_document_type,
        "version": int(inserted.get("version") or next_version),
        "file_path": inserted.get("file_path") or next_file_path,
        "is_active": bool(inserted.get("is_active", True)),
        "created_by": str(inserted.get("created_by") or actor_id or ""),
        "created_at": inserted.get("created_at"),
        "missing_variables": [],
    }
